"""Conversion service that runs planned ffmpeg outputs, validates them, and writes logs."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from audiofix.core.ffmpeg import (
    FfmpegOptions,
    build_ffmpeg_command,
    run_ffmpeg_command,
    validate_output_file,
)
from audiofix.core.logging import (
    ConversionLogItem,
    ConversionLogSettings,
    write_conversion_log,
)
from audiofix.core.planning import OutputPlanItem


@dataclass(frozen=True)
class ConversionRequest:
    ffmpeg_path: Path
    ffprobe_path: Path
    source_path: Path
    output_dir: Path
    plan: list[OutputPlanItem]
    options: FfmpegOptions
    settings: ConversionLogSettings


@dataclass(frozen=True)
class ConversionProgress:
    completed_count: int
    total_count: int
    filename: str


@dataclass(frozen=True)
class ConversionResult:
    output_dir: Path
    file_count: int
    total_count: int
    success: bool
    failure_message: str | None
    log_path: Path


def run_conversion_request(
    request: ConversionRequest,
    on_progress: Callable[[ConversionProgress], None] | None = None,
) -> ConversionResult:
    log_items: list[ConversionLogItem] = []
    failure_message: str | None = None

    for completed_count, item in enumerate(request.plan):
        if on_progress:
            on_progress(
                ConversionProgress(
                    completed_count=completed_count,
                    total_count=len(request.plan),
                    filename=item.output_path.name,
                )
            )

        command = build_ffmpeg_command(
            ffmpeg_path=request.ffmpeg_path,
            source_path=request.source_path,
            item=item,
            options=request.options,
        )
        result = run_ffmpeg_command(command)
        if result.returncode != 0:
            error_text = result.stderr.strip() or result.stdout.strip() or "ffmpeg failed"
            failure_message = f"{item.output_path.name}: {error_text}"
            log_items.append(
                ConversionLogItem(
                    plan_item=item,
                    status="failed",
                    message=error_text,
                )
            )
            break

        try:
            validate_output_file(request.ffprobe_path, item.output_path)
        except (RuntimeError, ValueError) as error:
            failure_message = f"{item.output_path.name}: {error}"
            log_items.append(
                ConversionLogItem(
                    plan_item=item,
                    status="failed",
                    message=str(error),
                )
            )
            break

        log_items.append(
            ConversionLogItem(
                plan_item=item,
                status="success",
                message="validated",
            )
        )

    success = failure_message is None and len(log_items) == len(request.plan)
    log_path = request.output_dir / ("conversion_log.txt" if success else "conversion_failed_log.txt")
    try:
        write_conversion_log(
            log_path=log_path,
            settings=request.settings,
            items=log_items,
            success=success,
            failure_message=failure_message,
        )
    except OSError as error:
        if failure_message:
            failure_message = f"{failure_message}; additionally failed to write log: {error}"
        else:
            failure_message = f"Generated files, but failed to write log: {error}"
        success = False
        log_path = request.output_dir / "conversion_failed_log.txt"
        try:
            write_conversion_log(
                log_path=log_path,
                settings=request.settings,
                items=log_items,
                success=False,
                failure_message=failure_message,
            )
        except OSError as failed_log_error:
            failure_message = f"{failure_message}; failed to write failure log: {failed_log_error}"

    return ConversionResult(
        output_dir=request.output_dir,
        file_count=sum(1 for item in log_items if item.status == "success"),
        total_count=len(request.plan),
        success=success,
        failure_message=failure_message,
        log_path=log_path,
    )
