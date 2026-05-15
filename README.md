# AudioFix
Generate multiple quieter versions of an audio file for game audio tuning.

## Table of Contents

- [Purpose](#purpose)
- [Design](#design)
- [Project Structure](#project-structure)
- [Run the GUI](#run-the-gui)
- [MVP Scope](#mvp-scope)
- [Example](#example)
- [Words are Words](#words-are-words)
- [Levels](#levels)
- [Tools](#tools)
- [Vendor Resources](#vendor-resources)

## Purpose
- Take one source audio file and export multiple files with different volume reductions.
- Support peak analysis: AudioFix measures the source peak with ffmpeg and calculates the first gain value from raw peak plus headroom.
- Let the user choose the minimum dB range and interval dB between outputs; AudioFix calculates the number of output files.
- Write a success or failure log that records the shared settings plus per-file gain and validation status.

## Design
- WoW's files are Ogg Vorbis, so the initial target output format is Ogg Vorbis.
- Use a Python Tkinter GUI frontend to control ffmpeg.
- Provide basic dependency-free light and dark GUI themes.
- Keep the first version free of third-party Python runtime dependencies.
- Prefer bundled `ffmpeg` and `ffprobe` binaries under `vendor/ffmpeg` so users do not need to install them manually.
- User-entered parameters:
  - minimum dB range
  - headroom dB for peak analysis
  - interval dB between files
  - raw plus headroom dB, calculated from analysis and still editable
  - Ogg Vorbis encoder mode: match source bitrate or choose a Vorbis quality level
  - overwrite behavior
  - output folder
- Peak analysis:
  - ffmpeg `astats` reads the overall source peak.
  - AudioFix calculates `-1 * (raw peak dB + headroom dB)` for file `_0`.
- Displayed input metadata:
  - codec
  - bitrate
  - sample rate
  - channel count
- Calculated parameters:
  - number of output files / steps
- Output files use unique numbered names: `filename_0.ogg`, `filename_1.ogg`, `filename_2.ogg`, etc.
- Conversion applies the calculated gain with ffmpeg's `volume` filter, applies later interval reductions with `volume`, reuses detected source sample rate/channel count, and exports Ogg Vorbis files. The default encoder mode uses Vorbis quality; match-source-bitrate mode uses the detected input bitrate when available.
- Successful runs write `conversion_log.txt`; failed runs write `conversion_failed_log.txt`.

## Project Structure
- `src/audiofix/gui/`: Tkinter interface.
- `src/audiofix/core/`: conversion planning, naming, ffmpeg command generation, conversion logging, and configuration.
- `vendor/ffmpeg/`: bundled ffmpeg/ffprobe resources.
- `tools/`: maintenance scripts for bundled resources and release prep.
- `docs/`: project notes that are more detailed than the README.
- `tests/`: focused tests for planning, naming, and command construction.

## Run the GUI
From the project root:

```powershell
python run_gui.py
```

## MVP Scope
- Batch loudness conversion first.
- The app handles simple peak analysis with ffmpeg.
- The app applies deterministic dB gain changes and exports numbered files.
- Advanced restoration, clipping repair, compression repair, and generative audio features are future ideas tracked in `docs/ideas.md`.

## Example
- Example/source: https://www.wowhead.com/sound=8960/readycheck  
The infamous "Your dungeon is ready" sound that is much louder than desired.

## Words are Words
Audio (data) or (physical) Sound ?  
A microphone converts sound into audio, and a speaker converts audio into sound.

## Levels
- Use the minimum dB range and interval dB to calculate output count.
- Use the calculated raw-plus-headroom value as the first output gain, then apply interval reductions for later outputs.
- The first gain value is calculated as `-1 * (overall peak dB + headroom dB)`.
- Most WoW sound files appear to be volume maximized already, so the current workflow assumes the source is loud enough and generates quieter variants.
- Automatic LUFS normalization and perceived-loudness analysis are out of scope for the first version.

## Tools

Utility scripts for maintaining bundled resources belong under `tools/`.

Current scripts:

- `tools/check_ffmpeg.py`: verify bundled or PATH ffmpeg/ffprobe.
- `tools/install_ffmpeg.py`: download and install Windows ffmpeg/ffprobe into `vendor/ffmpeg/win-x64/bin/`.

Planned scripts:

- prepare standalone release artifacts

## Vendor Resources

AudioFix is intended to be a mostly standalone utility. Third-party runtime
tools that users should not have to install manually belong here.

### ffmpeg

Expected layout for Windows builds:

```text
vendor/
  ffmpeg/
    win-x64/
      bin/
        ffmpeg.exe
        ffprobe.exe
```

Do not commit downloaded archives unless there is a deliberate release reason.
The app should prefer bundled binaries first and can later fall back to system
`ffmpeg` during development.

At startup and before conversion, AudioFix checks both `ffmpeg` and `ffprobe`
by running their `-version` commands. Runtime conversion does not download or
update these tools automatically.
