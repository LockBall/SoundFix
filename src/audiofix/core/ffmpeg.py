from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from audiofix.core.config import ENCODER_MODE_BITRATE, get_runtime_paths
from audiofix.core.planning import OutputPlanItem


@dataclass(frozen=True)
class FfmpegOptions:
    audio_bitrate: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    encoder_mode: str = ENCODER_MODE_BITRATE
    vorbis_quality: float | None = None
    overwrite: bool = False


@dataclass(frozen=True)
class AudioInfo:
    codec_name: str
    bit_rate: int | None
    sample_rate: int | None
    channels: int | None


@dataclass(frozen=True)
class PeakRefinementPass:
    pass_number: int
    gain_db: float
    encoded_peak_db: float
    error_db: float


@dataclass(frozen=True)
class BinaryStatus:
    name: str
    path: Path | None
    source: str
    version: str | None
    error: str | None

    @property
    def available(self) -> bool:
        return self.path is not None and self.error is None

    def display_text(self) -> str:
        if self.available:
            version = _compact_version(self.name, self.version)
            return f"{self.name}: {version}"
        return f"{self.name}: {self.error or 'missing'}"


def _compact_version(name: str, version: str | None) -> str:
    if not version:
        return "available"
    prefix = f"{name} version "
    if version.startswith(prefix):
        return version[len(prefix) :].split()[0].split("-")[0]
    return version.split()[0]


@dataclass(frozen=True)
class ToolStatus:
    ffmpeg: BinaryStatus
    ffprobe: BinaryStatus

    @property
    def available(self) -> bool:
        return self.ffmpeg.available and self.ffprobe.available

    def summary(self) -> str:
        if self.available:
            return f"ffmpeg ready: {self.ffmpeg.source}; ffprobe ready: {self.ffprobe.source}"
        missing = [
            status.name
            for status in (self.ffmpeg, self.ffprobe)
            if not status.available
        ]
        return f"Missing or invalid tools: {', '.join(missing)}"


def _find_binary_with_source(name: str, project_root: Path | None = None) -> tuple[Path | None, str]:
    paths = get_runtime_paths(project_root)
    bundled = paths.ffmpeg_root / "win-x64" / "bin" / f"{name}.exe"
    if bundled.exists():
        return bundled, "bundled"

    system_binary = shutil.which(name)
    if system_binary:
        return Path(system_binary), "PATH"

    return None, "missing"


def _find_binary(name: str, project_root: Path | None = None) -> Path | None:
    path, _source = _find_binary_with_source(name, project_root)
    return path


def find_ffmpeg(project_root: Path | None = None) -> Path | None:
    return _find_binary("ffmpeg", project_root)


def find_ffprobe(project_root: Path | None = None) -> Path | None:
    return _find_binary("ffprobe", project_root)


def check_ffmpeg_tools(project_root: Path | None = None) -> ToolStatus:
    return ToolStatus(
        ffmpeg=_check_binary("ffmpeg", project_root),
        ffprobe=_check_binary("ffprobe", project_root),
    )


def _check_binary(name: str, project_root: Path | None = None) -> BinaryStatus:
    path, source = _find_binary_with_source(name, project_root)
    if path is None:
        return BinaryStatus(
            name=name,
            path=None,
            source=source,
            version=None,
            error=f"{name} not found",
        )

    result = subprocess.run(
        [str(path), "-version"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        error_text = result.stderr.strip() or result.stdout.strip()
        return BinaryStatus(
            name=name,
            path=path,
            source=source,
            version=None,
            error=error_text or f"{name} -version failed",
        )

    first_line = result.stdout.splitlines()[0] if result.stdout else None
    return BinaryStatus(
        name=name,
        path=path,
        source=source,
        version=first_line,
        error=None,
    )


def probe_audio_info(ffprobe_path: Path, source_path: Path) -> AudioInfo:
    command = [
        str(ffprobe_path),
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,bit_rate,sample_rate,channels:format=bit_rate",
        "-of",
        "json",
        str(source_path),
    ]
    result = subprocess.run(command, capture_output=True, check=False, text=True)
    if result.returncode != 0:
        error_text = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(error_text or "ffprobe failed")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("No audio stream found")

    stream = streams[0]
    format_data = data.get("format", {})
    bit_rate = _parse_optional_int(stream.get("bit_rate"))
    if bit_rate is None:
        bit_rate = _parse_optional_int(format_data.get("bit_rate"))

    return AudioInfo(
        codec_name=str(stream.get("codec_name") or "unknown"),
        bit_rate=bit_rate,
        sample_rate=_parse_optional_int(stream.get("sample_rate")),
        channels=_parse_optional_int(stream.get("channels")),
    )


def measure_max_volume_db(ffmpeg_path: Path, source_path: Path) -> float:
    command = [
        str(ffmpeg_path),
        "-hide_banner",
        "-nostats",
        "-i",
        str(source_path),
        "-af",
        "astats=metadata=1:reset=0",
        "-f",
        "null",
        "NUL",
    ]
    result = subprocess.run(command, capture_output=True, check=False, text=True)
    output = f"{result.stdout}\n{result.stderr}"
    matches = re.findall(r"Peak level dB:\s*(-?\d+(?:\.\d+)?)", output)
    if result.returncode != 0 and not matches:
        error_text = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(error_text or "ffmpeg peak analysis failed")
    if not matches:
        raise RuntimeError("Could not read peak level from ffmpeg analysis")
    return float(matches[-1])


def gain_to_peak_margin_db(max_volume_db: float, peak_margin_db: float) -> float:
    return -max_volume_db - abs(peak_margin_db)


def scale_gain_db(gain_db: float, scale: float) -> float:
    return gain_db * scale


def refine_gain_for_encoded_peak(
    ffmpeg_path: Path,
    source_path: Path,
    initial_gain_db: float,
    peak_target_db: float,
    options: FfmpegOptions,
    iterations: int = 4,
) -> tuple[float, float]:
    gain_db, encoded_peak_db, _history = refine_gain_for_encoded_peak_with_history(
        ffmpeg_path=ffmpeg_path,
        source_path=source_path,
        initial_gain_db=initial_gain_db,
        peak_target_db=peak_target_db,
        options=options,
        iterations=iterations,
    )
    return gain_db, encoded_peak_db


def refine_gain_for_encoded_peak_with_history(
    ffmpeg_path: Path,
    source_path: Path,
    initial_gain_db: float,
    peak_target_db: float,
    options: FfmpegOptions,
    iterations: int = 4,
) -> tuple[float, float, list[PeakRefinementPass]]:
    if iterations < 1:
        raise ValueError("iterations must be at least 1")

    gain_db = initial_gain_db
    encoded_peak_db = 0.0
    history: list[PeakRefinementPass] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        for index in range(iterations):
            temp_output = temp_root / f"peak_refine_{index}.ogg"
            item = OutputPlanItem(index=index, gain_db=gain_db, output_path=temp_output)
            result = convert_plan_item(
                ffmpeg_path=ffmpeg_path,
                source_path=source_path,
                item=item,
                options=FfmpegOptions(
                    audio_bitrate=options.audio_bitrate,
                    sample_rate=options.sample_rate,
                    channels=options.channels,
                    encoder_mode=options.encoder_mode,
                    vorbis_quality=options.vorbis_quality,
                    overwrite=True,
                ),
            )
            if result.returncode != 0:
                error_text = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(error_text or "ffmpeg peak refinement failed")

            encoded_peak_db = measure_max_volume_db(ffmpeg_path, temp_output)
            error_db = encoded_peak_db - peak_target_db
            history.append(
                PeakRefinementPass(
                    pass_number=index + 1,
                    gain_db=gain_db,
                    encoded_peak_db=encoded_peak_db,
                    error_db=error_db,
                )
            )
            if index < iterations - 1:
                gain_db -= error_db

    return gain_db, encoded_peak_db, history


def _parse_optional_int(value: object) -> int | None:
    if value in (None, "N/A"):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def build_ffmpeg_command(
    ffmpeg_path: Path,
    source_path: Path,
    item: OutputPlanItem,
    options: FfmpegOptions,
) -> list[str]:
    overwrite_flag = "-y" if options.overwrite else "-n"
    filters = [build_audio_filter(item, options)]

    command = [
        str(ffmpeg_path),
        overwrite_flag,
        "-i",
        str(source_path),
        "-filter:a",
        ",".join(filters),
        "-c:a",
        "libvorbis",
    ]
    if options.encoder_mode == ENCODER_MODE_BITRATE and options.audio_bitrate:
        command.extend(["-b:a", options.audio_bitrate])
    if options.encoder_mode != ENCODER_MODE_BITRATE and options.vorbis_quality is not None:
        command.extend(["-q:a", str(options.vorbis_quality)])
    if options.sample_rate:
        command.extend(["-ar", str(options.sample_rate)])
    if options.channels:
        command.extend(["-ac", str(options.channels)])
    command.append(str(item.output_path))
    return command


def build_audio_filter(item: OutputPlanItem, options: FfmpegOptions) -> str:
    return f"volume={item.gain_db:g}dB"


def convert_plan_item(
    ffmpeg_path: Path,
    source_path: Path,
    item: OutputPlanItem,
    options: FfmpegOptions,
) -> subprocess.CompletedProcess[str]:
    command = build_ffmpeg_command(
        ffmpeg_path=ffmpeg_path,
        source_path=source_path,
        item=item,
        options=options,
    )
    return run_ffmpeg_command(command)


def run_ffmpeg_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
    )
