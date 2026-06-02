# AudioFix

Generate quieter Ogg Vorbis variants from one source audio file for game audio
tuning.

## Purpose

AudioFix is a small Tkinter utility for batch volume reduction. It analyzes the
source peak with FFmpeg, calculates a safe loudest output gain, then exports a
numbered set of quieter files.

The current workflow is aimed at World of Warcraft addon sound tuning, where a
custom slider can select among generated files and a separate off checkbox can
mute the sound.

## Current Behavior

- Input: one audio file.
- Output: numbered Ogg Vorbis files named from the editable output path, such
  as `readycheck_0.ogg`, `readycheck_1.ogg`, etc.
- File `_0` is the loudest generated file.
- Later files are quieter by a regular dB interval.
- Peak analysis uses FFmpeg `astats` overall `Peak level dB`.
- AudioFix calculates the loudest output gain as:

```text
calculated gain dB = -overall peak dB - abs(headroom dB)
```

- Default headroom is `0.500 dB`, targeting a `-0.500 dB` peak for file `_0`.
- Conversion uses FFmpeg's `volume=...dB` filter.
- Successful runs write `conversion_log.txt`.
- Failed runs write `conversion_failed_log.txt`.

## Output Path

The output path field controls both the destination folder and the generated
file stem. AudioFix appends the numbered suffix and `.ogg` extension.

For example, this output path:

```text
F:\sounds\readycheck_out\readycheck
```

generates:

```text
F:\sounds\readycheck_out\readycheck_0.ogg
F:\sounds\readycheck_out\readycheck_1.ogg
F:\sounds\readycheck_out\readycheck_2.ogg
```

## Level Controls

The GUI generates outputs with regular/even dB intervals. The user chooses a
minimum dB range and then selects which level input should be authoritative:

- `File Count`: enter the number of output files; AudioFix calculates the regular interval dB.
- `Interval dB`: enter the regular dB spacing; AudioFix calculates file count.

Current defaults:

```text
Minimum dB: -26.000
File Count: 20
Interval dB: 26 / 19 = 1.368421...
```

The default range reflects in-game testing: files quieter than about `-26 dB`
were not useful because the addon can mute sounds separately.

## Slider Mapping

Percent labels are useful UI, but audio gain is not linear percentage behavior.
AudioFix preserves the original sound character by applying plain gain changes
instead of LUFS normalization.

Useful amplitude equations:

```text
dB = 20 * log10(amplitude)
amplitude = 10^(dB / 20)
percent = 100 * 10^(dB / 20)
```

Examples:

| Linear amplitude | Gain dB |
|-----------------:|--------:|
| 100% | 0.00 dB |
| 50% | -6.02 dB |
| 25% | -12.04 dB |
| 10% | -20.00 dB |
| 5% | -26.02 dB |

For the current default `20` files from `0 dB` to `-26 dB`, AudioFix uses
regular dB spacing across the range. The slider-position gain is added after
peak-headroom gain:

```text
final gain dB = calculated peak-headroom gain dB + slider-position gain dB
```

See [docs/slider-level-mapping.md](docs/slider-level-mapping.md) for the current
default mapping table and reference formulas.

## Encoder Controls

The GUI shows detected source metadata:

- codec
- bitrate
- sample rate
- channel count
- raw peak after analysis

Output encoding is Ogg Vorbis. The user can either:

- use Vorbis quality mode, or
- match source bitrate when the source bitrate is available.

AudioFix reuses detected source sample rate and channel count where possible.

## Run the GUI

From the project root:

```powershell
python run_gui.py
```

## Tools

Current maintenance scripts:

- `tools/check_ffmpeg.py`: verify bundled or PATH FFmpeg/FFprobe.
- `tools/install_ffmpeg.py`: download and install Windows FFmpeg/FFprobe into
  `vendor/ffmpeg/win-x64/bin/`.

AudioFix prefers bundled tools first:

```text
vendor/
  ffmpeg/
    win-x64/
      bin/
        ffmpeg.exe
        ffprobe.exe
```

The app checks both binaries with `-version` at startup and before conversion.
Runtime conversion does not download or update tools automatically.

## Project Structure

- `src/audiofix/gui/`: Tkinter interface.
- `src/audiofix/core/`: planning, analysis, conversion, FFmpeg command building,
  logging, defaults, and runtime paths.
- `tests/`: focused tests for deterministic core behavior.
- `tools/`: maintenance scripts for bundled resources and release prep.
- `docs/`: supporting notes and reference tables.
- `vendor/ffmpeg/`: bundled FFmpeg/FFprobe resources.

## Scope

In scope:

- peak analysis
- deterministic gain reduction
- Ogg Vorbis export
- output validation with FFprobe
- success/failure logs

Out of scope for the current utility:

- LUFS normalization
- perceived-loudness matching
- clipping repair
- compression repair
- generative audio restoration


## Use Case Notes
### Goal: Change the Volume of a Specific Sound in WoW 
**Actions Performed in GoldWave**

- WoW doesnt natively support changing the volume of individual sounds, only entire channels of sounds.

- So we must provide a replacement sound file for each desired volume level.

- This utility can make a specific number of files at fixed dB intervals such that different volume levels can be seleted for a specific sound from within the game.

#### Getting Audio Files from WoW

1. Download from **WoWhead**: https://www.wowhead.com/sounds  
or  
Extract from game files using **Software**:  
   - CASCView: http://www.zezula.net/en/casc/main.html
   - listfile: https://github.com/wowdev/wow-listfile/releases  
     - in CASCView click the Battle.Net Icon *Game Storage* then select the World of Warcraft installation.
     - The listfile might be required to parse everything.

1. Save the file(s) as a .wav for future processing, e.g. de-clipping, conversion from mono → stero
   - `File > Save As... > .wav`
   - `Attributes... > PCM Signed 24 bit , stereo`
     - selecting stereo here will convert mono to stereo

**DO ALL PROCESSING ON MONO FIRST !!**
#### Mono → Stereo Conversion
- Many WoW audio files are mono.  
e.g. achievmentsound1, FishingBobber_ver2

- WoW plays these mono audio effects on both the left and right channel simulataneously so they don't have any stereo width. 

- These can be made into stereo audio files by duplicating the original channel so there will be a left and right channel.

- Stereo width can be added by adding an ~ 8 ms silent pad to the beginning of the new duplicate channel, thus shifting the new channel to the right in time.
  - De-Select the top, left, white channel by unchecking the box in the middle of the channel.
  - The bottom info-bar should now say `Right`
  - `Edit > Insert Silence`
    - `Duration (s): 0.008000`
    - `Location: Beginning of File`
    - `OK`
    - `Save As...` with new name

  **Mono** for positional sounds so the game engine can place it correctly.

  **Stereo** (slightly wide) for non‑positional sounds that always play centered.


#### Amplitude Correction / De-Clipping

- I've gone back and forth on this, i though these were very lossy badly clipped files. I don't think any of them are terribly lossy for the purposes of the game although they definitely arent HiFi. Some are clipped, some arent.

- File inspection: after converintg to 24 bit PCM wav, use `Tool > Amplitude Statistics` we can see that some of the files are clipped. This clipping is evident in other formats as well. We must account for this before batch compressing to .ogg or the issue will be exacerbated.

- Can we AI resample to reconstruct the missing pieces using somethign like iZotope RX 12? YES

1. open the file in RX 12
1. select the entire waveform, ctrl + A
1. open the De-Clip tool



 ## Acronyms

 - World of Warcraft WoW