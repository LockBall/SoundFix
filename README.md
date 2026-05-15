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
- Support manual analysis: the user enters the initial dB gain value determined in GoldWave or another tool.
- Let the user choose the minimum dB range and dB interval between outputs; AudioFix calculates the number of output files.
- Generate a log file that records the source file, output files, and dB levels used.

## Design
- WoW's files are Ogg Vorbis, so the initial target output format is Ogg Vorbis.
- Use a Python Tkinter GUI frontend to control ffmpeg.
- Provide basic dependency-free light and dark GUI themes.
- Keep the first version free of third-party Python runtime dependencies.
- Prefer bundled `ffmpeg` and `ffprobe` binaries under `vendor/ffmpeg` so users do not need to install them manually.
- User-entered parameters:
  - minimum dB range
  - initial dB gain measured externally for the selected input file
  - peak margin dB for optional peak analysis
  - dB interval between files
  - Ogg Vorbis encoder mode: match source bitrate or choose a Vorbis quality level
  - overwrite behavior
  - output folder
- Optional analysis:
  - peak analysis can fill initial dB from ffmpeg `astats` and refine through a temporary Ogg encode so the encoded output peak lands closer to the requested margin.
  - peak scale can adjust the refined result before it is used as Initial dB; `1.00` uses the refined value directly, while `0.95` uses 95% of that dB value.
- Displayed input metadata:
  - codec
  - bitrate
  - sample rate
  - channel count
- Calculated parameters:
  - number of output files / steps
- Output files use unique numbered names: `filename_0.ogg`, `filename_1.ogg`, `filename_2.ogg`, etc.
- Each run writes a log file as a reference for the dB levels used.
- Conversion applies the user-entered initial dB value with ffmpeg's `volume` filter, applies later dB step reductions with `volume`, reuses detected source sample rate/channel count, and exports Ogg Vorbis files. The default encoder mode matches the detected source bitrate; quality mode uses ffmpeg `-q:a`.

## Project Structure
- `src/audiofix/gui/`: Tkinter interface.
- `src/audiofix/core/`: conversion planning, naming, ffmpeg command generation, and logging logic.
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
- The user handles audio analysis manually for now.
- The app applies deterministic dB gain changes and exports numbered files.
- Advanced restoration, clipping repair, compression repair, and generative audio features are future ideas tracked in `docs/ideas.md`.

## Example
- Example/source: https://www.wowhead.com/sound=8960/readycheck  
The infamous "Your dungeon is ready" sound that is much louder than desired.

## Words are Words
Audio (data) or (physical) Sound ?  
A microphone converts sound into audio, and a speaker converts audio into sound.

## Levels
- Use the minimum dB range and dB interval to calculate output count.
- Use the user-entered initial dB value as the first output gain, then apply dB interval reductions for later outputs.
- The initial dB value can also be calculated from peak analysis as `0 - overall peak dB - peak margin dB`, then refined against a temporary encoded output; a margin of `9.00` targets a `-9.00 dB` peak.
- Temporary files created during peak refinement are used only for measurement and are discarded automatically. Final outputs are always encoded from the original input file, not from the temporary files.
- Most WoW sound files appear to be volume maximized already, so the initial workflow assumes the source is loud enough and generates quieter variants.
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
