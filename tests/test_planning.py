"""Focused tests for core planning, ffmpeg command construction, and services."""

import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from audiofix.core.planning import (
    build_output_plan,
    calculate_step_count,
)

from audiofix.core.config import ENCODER_MODE_BITRATE, ENCODER_MODE_QUALITY
from audiofix.core.analysis import PeakAnalysisRequest, analyze_peak
from audiofix.core.conversion import ConversionRequest, run_conversion_request
from audiofix.core.ffmpeg import (
    AudioInfo,
    BinaryStatus,
    FfmpegOptions,
    build_audio_filter,
    build_ffmpeg_command,
    check_ffmpeg_tools,
    convert_plan_item,
    gain_to_peak_headroom_db,
    measure_max_volume_db,
    validate_output_file,
)
from audiofix.core.logging import (
    ConversionLogItem,
    ConversionLogSettings,
    build_conversion_log_lines,
)
from audiofix.core.tasks import start_background_task


class BuildOutputPlanTests(unittest.TestCase):
    def test_calculates_step_count_from_min_db_and_interval(self) -> None:
        self.assertEqual(calculate_step_count(min_db=-60.0, interval_db=3.0), 21)
        self.assertEqual(calculate_step_count(min_db=-60.0, interval_db=1.5), 41)

    def test_rejects_invalid_step_count_inputs(self) -> None:
        with self.assertRaises(ValueError):
            calculate_step_count(min_db=0.0, interval_db=3.0)
        with self.assertRaises(ValueError):
            calculate_step_count(min_db=-60.0, interval_db=0.0)

    def test_builds_numbered_outputs_with_db_steps(self) -> None:
        plan = build_output_plan(
            source_path=Path("levelup2.ogg"),
            output_dir=Path("out"),
            db_offset=-3.0,
            step_count=3,
            interval_db=-3.0,
        )

        self.assertEqual([item.index for item in plan], [0, 1, 2])
        self.assertEqual([item.gain_db for item in plan], [-3.0, -6.0, -9.0])
        self.assertEqual(
            [item.output_path for item in plan],
            [
                Path("out/levelup2_0.ogg"),
                Path("out/levelup2_1.ogg"),
                Path("out/levelup2_2.ogg"),
            ],
        )

    def test_rejects_zero_steps(self) -> None:
        with self.assertRaises(ValueError):
            build_output_plan(
                source_path=Path("source.ogg"),
                output_dir=Path("out"),
                db_offset=0.0,
                step_count=0,
                interval_db=-3.0,
            )


class FfmpegCommandTests(unittest.TestCase):
    def test_measures_max_volume_from_ffmpeg_astats_output(self) -> None:
        completed = mock.Mock()
        completed.returncode = 0
        completed.stdout = ""
        completed.stderr = """
        [Parsed_astats_0] Channel: 1
        [Parsed_astats_0] Peak level dB: 0.813331
        [Parsed_astats_0] Channel: 2
        [Parsed_astats_0] Peak level dB: 0.449314
        [Parsed_astats_0] Overall
        [Parsed_astats_0] Peak level dB: 0.813331
        [Parsed_astats_0] Some later non-overall section
        [Parsed_astats_0] Peak level dB: -12.000000
        """

        with mock.patch("audiofix.core.ffmpeg.subprocess.run", return_value=completed):
            measured = measure_max_volume_db(Path("ffmpeg"), Path("source.ogg"))

        self.assertEqual(measured, 0.813331)

    def test_calculates_gain_to_peak_headroom(self) -> None:
        self.assertAlmostEqual(gain_to_peak_headroom_db(0.813331, 0.05), -0.863331)

    def test_builds_volume_filter_from_gain_db(self) -> None:
        plan = build_output_plan(
            source_path=Path("source.ogg"),
            output_dir=Path("out"),
            db_offset=-12.39,
            step_count=1,
            interval_db=-3.0,
        )

        audio_filter = build_audio_filter(plan[0])

        self.assertEqual(audio_filter, "volume=-12.39dB")

    def test_binary_status_display_text(self) -> None:
        available = BinaryStatus(
            name="ffmpeg",
            path=Path("ffmpeg.exe"),
            source="bundled",
            version="ffmpeg version 8.1.1",
            error=None,
        )
        missing = BinaryStatus(
            name="ffprobe",
            path=None,
            source="missing",
            version=None,
            error="ffprobe not found",
        )

        self.assertEqual(available.display_text(), "ffmpeg: 8.1.1")
        self.assertEqual(missing.display_text(), "ffprobe: ffprobe not found")

    def test_reports_missing_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("audiofix.core.ffmpeg.shutil.which", return_value=None):
                status = check_ffmpeg_tools(project_root=Path(temp_dir))

        self.assertFalse(status.available)
        self.assertFalse(status.ffmpeg.available)
        self.assertFalse(status.ffprobe.available)
        self.assertIn("ffmpeg", status.summary())
        self.assertIn("ffprobe", status.summary())

    def test_builds_ogg_vorbis_volume_command_with_source_bitrate(self) -> None:
        plan = build_output_plan(
            source_path=Path("source.ogg"),
            output_dir=Path("out"),
            db_offset=-12.39,
            step_count=1,
            interval_db=-3.0,
        )

        command = build_ffmpeg_command(
            ffmpeg_path=Path("ffmpeg"),
            source_path=Path("source.ogg"),
            item=plan[0],
            options=FfmpegOptions(
                audio_bitrate="160k",
                encoder_mode=ENCODER_MODE_BITRATE,
                sample_rate=44100,
                channels=2,
                overwrite=True,
            ),
        )

        self.assertEqual(
            command,
            [
                "ffmpeg",
                "-y",
                "-i",
                "source.ogg",
                "-filter:a",
                "volume=-12.39dB",
                "-c:a",
                "libvorbis",
                "-b:a",
                "160k",
                "-ar",
                "44100",
                "-ac",
                "2",
                str(Path("out/source_0.ogg")),
            ],
        )

    def test_omits_bitrate_when_source_bitrate_is_unknown(self) -> None:
        plan = build_output_plan(
            source_path=Path("source.ogg"),
            output_dir=Path("out"),
            db_offset=-12.39,
            step_count=1,
            interval_db=-3.0,
        )

        command = build_ffmpeg_command(
            ffmpeg_path=Path("ffmpeg"),
            source_path=Path("source.ogg"),
            item=plan[0],
            options=FfmpegOptions(audio_bitrate=None, overwrite=False),
        )

        self.assertNotIn("-b:a", command)

    def test_builds_vorbis_quality_command(self) -> None:
        plan = build_output_plan(
            source_path=Path("source.ogg"),
            output_dir=Path("out"),
            db_offset=-12.39,
            step_count=1,
            interval_db=-3.0,
        )

        command = build_ffmpeg_command(
            ffmpeg_path=Path("ffmpeg"),
            source_path=Path("source.ogg"),
            item=plan[0],
            options=FfmpegOptions(
                audio_bitrate="160k",
                encoder_mode=ENCODER_MODE_QUALITY,
                vorbis_quality=5,
                overwrite=True,
            ),
        )

        self.assertIn("-q:a", command)
        self.assertIn("5", command)
        self.assertNotIn("-b:a", command)

    def test_convert_plan_item_uses_built_command(self) -> None:
        plan = build_output_plan(
            source_path=Path("source.ogg"),
            output_dir=Path("out"),
            db_offset=-12.39,
            step_count=1,
            interval_db=-3.0,
        )

        with mock.patch("audiofix.core.ffmpeg.run_ffmpeg_command") as run_command:
            convert_plan_item(
                ffmpeg_path=Path("ffmpeg"),
                source_path=Path("source.ogg"),
                item=plan[0],
                options=FfmpegOptions(overwrite=True),
            )

        run_command.assert_called_once_with(
            [
                "ffmpeg",
                "-y",
                "-i",
                "source.ogg",
                "-filter:a",
                "volume=-12.39dB",
                "-c:a",
                "libvorbis",
                str(Path("out/source_0.ogg")),
            ]
        )

    def test_validates_output_file_with_ffprobe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.ogg"
            output_path.write_bytes(b"audio")

            with mock.patch(
                "audiofix.core.ffmpeg.probe_audio_info",
                return_value=AudioInfo(
                    codec_name="vorbis",
                    bit_rate=160000,
                    sample_rate=44100,
                    channels=2,
                ),
            ) as probe_audio_info:
                validate_output_file(Path("ffprobe"), output_path)

        probe_audio_info.assert_called_once_with(Path("ffprobe"), output_path)

    def test_rejects_empty_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.ogg"
            output_path.write_bytes(b"")

            with self.assertRaises(RuntimeError):
                validate_output_file(Path("ffprobe"), output_path)


class ConversionLogTests(unittest.TestCase):
    def test_builds_failed_conversion_log_lines(self) -> None:
        plan = build_output_plan(
            source_path=Path("source.ogg"),
            output_dir=Path("out"),
            db_offset=-1.5,
            step_count=1,
            interval_db=-3.0,
        )
        settings = ConversionLogSettings(
            source_path=Path("source.ogg"),
            output_dir=Path("out"),
            max_db=0.0,
            min_db=-60.0,
            interval_db=3.0,
            raw_peak_db=1.0,
            headroom_db=0.5,
            calculated_gain_db=-1.5,
            encoder_mode="Vorbis Quality",
            vorbis_quality=5.0,
            overwrite=False,
        )

        lines = build_conversion_log_lines(
            settings=settings,
            items=[
                ConversionLogItem(
                    plan_item=plan[0],
                    status="failed",
                    message="ffmpeg failed",
                )
            ],
            success=False,
            failure_message="source_0.ogg: ffmpeg failed",
        )

        log_text = "\n".join(lines)
        self.assertIn("Status: failed", log_text)
        self.assertIn("source_0.ogg: ffmpeg failed", log_text)
        self.assertIn("index\toutput_file\tgain_db\tstatus\tmessage", log_text)
        self.assertIn("0\tsource_0.ogg\t-1.500\tfailed\tffmpeg failed", log_text)
        self.assertNotIn("out/source_0.ogg", log_text)


class PeakAnalysisServiceTests(unittest.TestCase):
    def test_analyzes_peak_from_core_service(self) -> None:
        status = mock.Mock()
        status.ffmpeg.available = True
        status.ffmpeg.path = Path("ffmpeg")
        status.ffprobe.available = True
        status.ffprobe.path = Path("ffprobe")
        audio_info = AudioInfo(
            codec_name="vorbis",
            bit_rate=160000,
            sample_rate=44100,
            channels=2,
        )

        with (
            mock.patch("audiofix.core.analysis.check_ffmpeg_tools", return_value=status),
            mock.patch("audiofix.core.analysis.probe_audio_info", return_value=audio_info),
            mock.patch("audiofix.core.analysis.measure_max_volume_db", return_value=0.813),
        ):
            result = analyze_peak(
                PeakAnalysisRequest(
                    source_path=Path("source.ogg"),
                    headroom_db=0.5,
                    encoder_mode=ENCODER_MODE_QUALITY,
                )
            )

        self.assertEqual(result.audio_info, audio_info)
        self.assertEqual(result.max_volume_db, 0.813)
        self.assertAlmostEqual(result.calculated_gain_db, -1.313)


class ConversionServiceTests(unittest.TestCase):
    def test_runs_conversion_and_writes_success_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            plan = build_output_plan(
                source_path=Path("source.ogg"),
                output_dir=output_dir,
                db_offset=-1.5,
                step_count=1,
                interval_db=-3.0,
            )
            settings = ConversionLogSettings(
                source_path=Path("source.ogg"),
                output_dir=output_dir,
                max_db=0.0,
                min_db=-60.0,
                interval_db=3.0,
                raw_peak_db=1.0,
                headroom_db=0.5,
                calculated_gain_db=-1.5,
                encoder_mode="Vorbis Quality",
                vorbis_quality=5.0,
                overwrite=True,
            )
            completed = mock.Mock(returncode=0, stdout="", stderr="")
            progress_updates = []

            with (
                mock.patch("audiofix.core.conversion.run_ffmpeg_command", return_value=completed),
                mock.patch("audiofix.core.conversion.validate_output_file"),
            ):
                result = run_conversion_request(
                    ConversionRequest(
                        ffmpeg_path=Path("ffmpeg"),
                        ffprobe_path=Path("ffprobe"),
                        source_path=Path("source.ogg"),
                        output_dir=output_dir,
                        plan=plan,
                        options=FfmpegOptions(overwrite=True),
                        settings=settings,
                    ),
                    on_progress=progress_updates.append,
                )

        self.assertTrue(result.success)
        self.assertEqual(result.file_count, 1)
        self.assertEqual(progress_updates[0].filename, plan[0].output_path.name)
        self.assertEqual(result.log_path.name, "conversion_log.txt")


class BackgroundTaskTests(unittest.TestCase):
    def test_background_task_schedules_success_callback(self) -> None:
        callbacks = []
        results = []

        thread = start_background_task(
            work=lambda: "done",
            on_success=results.append,
            on_error=lambda error: self.fail(str(error)),
            schedule=callbacks.append,
        )
        thread.join(timeout=5)

        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        self.assertEqual(results, ["done"])


if __name__ == "__main__":
    unittest.main()
