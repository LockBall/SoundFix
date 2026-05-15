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

from audiofix.core.config import ENCODER_MODE_QUALITY
from audiofix.core.ffmpeg import (
    BinaryStatus,
    FfmpegOptions,
    build_audio_filter,
    build_ffmpeg_command,
    check_ffmpeg_tools,
    convert_plan_item,
    gain_to_peak_margin_db,
    measure_max_volume_db,
    refine_gain_for_encoded_peak,
    refine_gain_for_encoded_peak_with_history,
    scale_gain_db,
)


class BuildOutputPlanTests(unittest.TestCase):
    def test_calculates_step_count_from_min_db_and_interval(self) -> None:
        self.assertEqual(calculate_step_count(min_db=-60.0, db_interval=3.0), 21)
        self.assertEqual(calculate_step_count(min_db=-60.0, db_interval=1.5), 41)

    def test_rejects_invalid_step_count_inputs(self) -> None:
        with self.assertRaises(ValueError):
            calculate_step_count(min_db=0.0, db_interval=3.0)
        with self.assertRaises(ValueError):
            calculate_step_count(min_db=-60.0, db_interval=0.0)

    def test_builds_numbered_outputs_with_db_steps(self) -> None:
        plan = build_output_plan(
            source_path=Path("levelup2.ogg"),
            output_dir=Path("out"),
            db_offset=-3.0,
            step_count=3,
            db_interval=-3.0,
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
                db_interval=-3.0,
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
        """

        with mock.patch("audiofix.core.ffmpeg.subprocess.run", return_value=completed):
            measured = measure_max_volume_db(Path("ffmpeg"), Path("source.ogg"))

        self.assertEqual(measured, 0.813331)

    def test_calculates_gain_to_peak_margin(self) -> None:
        self.assertEqual(gain_to_peak_margin_db(-0.4, 0.0), 0.4)
        self.assertEqual(gain_to_peak_margin_db(0.813331, 0.0), -0.813331)
        self.assertEqual(gain_to_peak_margin_db(0.813331, 0.2), -1.013331)
        self.assertEqual(gain_to_peak_margin_db(0.813331, 9.0), -9.813331)

    def test_scales_refined_gain(self) -> None:
        self.assertEqual(scale_gain_db(-1.4, 1.0), -1.4)
        self.assertEqual(scale_gain_db(-1.4, 0.95), -1.3299999999999998)

    def test_refines_gain_against_encoded_peak(self) -> None:
        completed = mock.Mock()
        completed.returncode = 0
        completed.stdout = ""
        completed.stderr = ""

        with (
            mock.patch("audiofix.core.ffmpeg.convert_plan_item", return_value=completed),
            mock.patch("audiofix.core.ffmpeg.measure_max_volume_db", side_effect=[0.15, 0.01]),
        ):
            gain_db, encoded_peak_db = refine_gain_for_encoded_peak(
                ffmpeg_path=Path("ffmpeg"),
                source_path=Path("source.ogg"),
                initial_gain_db=-0.81,
                peak_target_db=0.0,
                options=FfmpegOptions(audio_bitrate="112000", sample_rate=44100, channels=2),
                iterations=2,
            )

        self.assertAlmostEqual(gain_db, -0.96)
        self.assertEqual(encoded_peak_db, 0.01)

    def test_refines_gain_with_measured_pass_history(self) -> None:
        completed = mock.Mock()
        completed.returncode = 0
        completed.stdout = ""
        completed.stderr = ""

        with (
            mock.patch("audiofix.core.ffmpeg.convert_plan_item", return_value=completed),
            mock.patch("audiofix.core.ffmpeg.measure_max_volume_db", side_effect=[0.15, 0.01]),
        ):
            gain_db, encoded_peak_db, history = refine_gain_for_encoded_peak_with_history(
                ffmpeg_path=Path("ffmpeg"),
                source_path=Path("source.ogg"),
                initial_gain_db=-0.81,
                peak_target_db=0.0,
                options=FfmpegOptions(audio_bitrate="112000", sample_rate=44100, channels=2),
                iterations=2,
            )

        self.assertAlmostEqual(gain_db, -0.96)
        self.assertEqual(encoded_peak_db, 0.01)
        self.assertEqual([result.pass_number for result in history], [1, 2])
        self.assertEqual([result.encoded_peak_db for result in history], [0.15, 0.01])
        self.assertEqual([result.error_db for result in history], [0.15, 0.01])

    def test_builds_goldwave_style_volume_filter_from_initial_db(self) -> None:
        plan = build_output_plan(
            source_path=Path("source.ogg"),
            output_dir=Path("out"),
            db_offset=-12.39,
            step_count=1,
            db_interval=-3.0,
        )

        audio_filter = build_audio_filter(plan[0], FfmpegOptions())

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
            db_interval=-3.0,
        )

        command = build_ffmpeg_command(
            ffmpeg_path=Path("ffmpeg"),
            source_path=Path("source.ogg"),
            item=plan[0],
            options=FfmpegOptions(
                audio_bitrate="160k",
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
            db_interval=-3.0,
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
            db_interval=-3.0,
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
            db_interval=-3.0,
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


if __name__ == "__main__":
    unittest.main()
