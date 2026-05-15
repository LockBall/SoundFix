"""Developer utility for checking bundled or PATH ffmpeg/ffprobe availability."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from audiofix.core.ffmpeg import check_ffmpeg_tools


def main() -> int:
    status = check_ffmpeg_tools(project_root=ROOT)
    print(status.summary())

    for binary_status in (status.ffmpeg, status.ffprobe):
        print(f"{binary_status.name}:")
        print(f"  source: {binary_status.source}")
        print(f"  path: {binary_status.path or 'not found'}")
        print(f"  version: {binary_status.version or 'unknown'}")
        print(f"  error: {binary_status.error or 'none'}")

    return 0 if status.available else 1


if __name__ == "__main__":
    raise SystemExit(main())
