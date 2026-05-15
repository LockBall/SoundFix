"""Peak analysis service for measuring source audio and calculating first gain."""

from dataclasses import dataclass
from pathlib import Path

from audiofix.core.config import ENCODER_MODE_BITRATE
from audiofix.core.ffmpeg import (
    AudioInfo,
    ToolStatus,
    check_ffmpeg_tools,
    gain_to_peak_headroom_db,
    measure_max_volume_db,
    probe_audio_info,
)


@dataclass(frozen=True)
class PeakAnalysisRequest:
    source_path: Path
    headroom_db: float
    encoder_mode: str


@dataclass(frozen=True)
class PeakAnalysisResult:
    tool_status: ToolStatus
    audio_info: AudioInfo
    max_volume_db: float
    headroom_db: float
    calculated_gain_db: float


def analyze_peak(request: PeakAnalysisRequest) -> PeakAnalysisResult:
    tool_status = check_ffmpeg_tools()
    if not tool_status.ffmpeg.available or tool_status.ffmpeg.path is None:
        raise RuntimeError("ffmpeg unavailable; cannot analyze peak.")
    if not tool_status.ffprobe.available or tool_status.ffprobe.path is None:
        raise RuntimeError("ffprobe unavailable; cannot read input audio settings.")

    audio_info = probe_audio_info(tool_status.ffprobe.path, request.source_path)
    if request.encoder_mode == ENCODER_MODE_BITRATE and audio_info.bit_rate is None:
        raise RuntimeError("Input audio bitrate is unknown; cannot analyze peak with match-bitrate mode.")

    max_volume_db = measure_max_volume_db(tool_status.ffmpeg.path, request.source_path)
    calculated_gain_db = gain_to_peak_headroom_db(max_volume_db, request.headroom_db)
    return PeakAnalysisResult(
        tool_status=tool_status,
        audio_info=audio_info,
        max_volume_db=max_volume_db,
        headroom_db=request.headroom_db,
        calculated_gain_db=calculated_gain_db,
    )
