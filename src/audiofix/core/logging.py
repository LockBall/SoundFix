"""Conversion log formatting and writing for successful and failed runs."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from audiofix.core.planning import OutputPlanItem


@dataclass(frozen=True)
class ConversionLogSettings:
    source_path: Path
    output_dir: Path
    max_db: float
    min_db: float
    interval_db: float
    raw_peak_db: float | None
    headroom_db: float
    calculated_gain_db: float
    encoder_mode: str
    vorbis_quality: float | None
    overwrite: bool


@dataclass(frozen=True)
class ConversionLogItem:
    plan_item: OutputPlanItem
    status: str
    message: str = ""


def write_conversion_log(
    log_path: Path,
    settings: ConversionLogSettings,
    items: list[ConversionLogItem],
    success: bool,
    failure_message: str | None = None,
) -> Path:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            build_conversion_log_lines(
                settings=settings,
                items=items,
                success=success,
                failure_message=failure_message,
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return log_path


def build_conversion_log_lines(
    settings: ConversionLogSettings,
    items: list[ConversionLogItem],
    success: bool,
    failure_message: str | None = None,
) -> list[str]:
    lines = [
        "AudioFix conversion log",
        f"Status: {'success' if success else 'failed'}",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Settings:",
        f"Source: {settings.source_path}",
        f"Output folder: {settings.output_dir}",
        f"Maximum dB: {settings.max_db:.3f}",
        f"Minimum dB: {settings.min_db:.3f}",
        f"Interval dB: {settings.interval_db:.3f}",
        f"Raw peak dB: {_format_optional_db(settings.raw_peak_db)}",
        f"Headroom dB: {settings.headroom_db:.3f}",
        f"Raw + Head gain dB: {settings.calculated_gain_db:.3f}",
        f"Encoder mode: {settings.encoder_mode}",
        f"Vorbis quality: {_format_optional_number(settings.vorbis_quality)}",
        f"Overwrite: {settings.overwrite}",
        "",
    ]
    if failure_message:
        lines.extend(["Failure:", failure_message, ""])

    lines.extend(
        [
            "Files:",
            "index\toutput_file\tgain_db\tstatus\tmessage",
        ]
    )
    for item in items:
        lines.append(
            "\t".join(
                [
                    str(item.plan_item.index),
                    _format_output_path(item.plan_item.output_path, settings.output_dir),
                    f"{item.plan_item.gain_db:.3f}",
                    item.status,
                    item.message,
                ]
            )
        )
    return lines


def _format_optional_db(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.3f}"


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:g}"


def _format_output_path(output_path: Path, output_dir: Path) -> str:
    try:
        return str(output_path.relative_to(output_dir))
    except ValueError:
        return output_path.name
