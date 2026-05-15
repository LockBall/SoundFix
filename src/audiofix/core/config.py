from dataclasses import dataclass
from pathlib import Path


APP_NAME = "AudioFix"

# Output defaults
DEFAULT_OUTPUT_EXTENSION = ".ogg"

# Level defaults
DEFAULT_MAX_DB = 0.0
DEFAULT_MIN_DB = -60.0
DEFAULT_CALCULATED_GAIN_DB_TEXT = ""
DEFAULT_INTERVAL_DB = 3.0
DEFAULT_PEAK_HEADROOM_DB = 0.500
DB_DISPLAY_DECIMALS = 3

# Window defaults
DEFAULT_WINDOW_WIDTH = 1000
DEFAULT_WINDOW_HEIGHT = 575

# Layout spacing
APP_ROW_GAP_PX = 20
CONTROL_TITLE_GAP_PX = 2
COMPACT_SECTION_ROW_GAP_PX = 6
RELATED_CONTROL_GAP_PX = 8
FIELD_PAD_X_PX = 8
BUTTON_PAD_X_PX = 8
ENCODER_SCALE_PAD_X_PX = 32

# Widget sizing
DB_FIELD_WIDTH_CHARS = 12
DB_LABEL_WIDTH_CHARS = 14
CALCULATED_GAIN_LABEL_WIDTH_CHARS = 18
ENCODER_MODE_WIDTH_CHARS = 22
VORBIS_SCALE_LENGTH_PX = 330
SETTINGS_COLUMN_COUNT = 4

# Encoder defaults
ENCODER_MODE_BITRATE = "bitrate"
ENCODER_MODE_QUALITY = "quality"
DEFAULT_ENCODER_MODE = ENCODER_MODE_QUALITY
DEFAULT_VORBIS_QUALITY = 5
VORBIS_QUALITY_BITRATES = {
    -1: "45 kbit/s",
    0: "64 kbit/s",
    1: "80 kbit/s",
    2: "96 kbit/s",
    3: "112 kbit/s",
    4: "128 kbit/s",
    5: "160 kbit/s",
    6: "192 kbit/s",
    7: "224 kbit/s",
    8: "256 kbit/s",
    9: "320 kbit/s",
    10: "500 kbit/s",
}


@dataclass(frozen=True)
class RuntimePaths:
    project_root: Path
    vendor_root: Path
    ffmpeg_root: Path


def get_runtime_paths(project_root: Path | None = None) -> RuntimePaths:
    root = project_root or Path(__file__).resolve().parents[3]
    vendor_root = root / "vendor"
    return RuntimePaths(
        project_root=root,
        vendor_root=vendor_root,
        ffmpeg_root=vendor_root / "ffmpeg",
    )
