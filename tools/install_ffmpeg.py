"""Developer utility for installing Windows ffmpeg/ffprobe into vendor/ffmpeg."""

from pathlib import Path
import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEFAULT_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
TARGET_BIN = ROOT / "vendor" / "ffmpeg" / "win-x64" / "bin"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from audiofix.core.ffmpeg import check_ffmpeg_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install ffmpeg.exe and ffprobe.exe into vendor/ffmpeg/win-x64/bin."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="ffmpeg Windows zip URL to download.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing ffmpeg.exe and ffprobe.exe in the target folder.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    existing = [TARGET_BIN / "ffmpeg.exe", TARGET_BIN / "ffprobe.exe"]
    if not args.force and any(path.exists() for path in existing):
        print("ffmpeg binaries already exist. Use --force to replace them.")
        return 1

    TARGET_BIN.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "ffmpeg.zip"
        extract_dir = Path(temp_dir) / "extract"

        print(f"Downloading {args.url}")
        urllib.request.urlretrieve(args.url, archive_path)

        print("Extracting archive")
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)

        source_bin = find_extracted_bin(extract_dir)
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            source = source_bin / name
            if not source.exists():
                print(f"Archive did not contain {name}")
                return 1
            shutil.copy2(source, TARGET_BIN / name)

    status = check_ffmpeg_tools(project_root=ROOT)
    print(status.summary())
    return 0 if status.available else 1


def find_extracted_bin(extract_dir: Path) -> Path:
    matches = [
        path
        for path in extract_dir.rglob("bin")
        if (path / "ffmpeg.exe").exists() and (path / "ffprobe.exe").exists()
    ]
    if not matches:
        raise FileNotFoundError("Could not find ffmpeg.exe and ffprobe.exe in archive")
    return matches[0]


if __name__ == "__main__":
    raise SystemExit(main())
