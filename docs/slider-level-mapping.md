# Slider Level Mapping

This note records the current practical level mapping for the addon slider.
Older trial tables were removed; keep this file focused on the active default
and formulas needed to reason about future changes.

## Current Default

AudioFix uses regular/even dB spacing for generated files. It currently
defaults to:

```text
minimum dB: -26.000
file count: 20
interval dB: 26 / 19 = 1.368421...
```

File index `0` is the loudest output and uses `0.000 dB` slider-position gain.
Later indices get quieter.

The generated per-position gain is a regular dB interval:

```text
slider-position gain dB = -index * (abs(minimum dB) / (file count - 1))
```

That gain is added to the peak-headroom gain calculated from the source file:

```text
final gain dB = calculated peak-headroom gain dB + slider-position gain dB
```

## Current Default Table

| File Index | Slider-Position Gain dB | Linear Amplitude |
|-----------:|------------------------:|-----------------:|
| 0 | 0.000 | 100.00% |
| 1 | -1.368 | 85.42% |
| 2 | -2.737 | 72.97% |
| 3 | -4.105 | 62.34% |
| 4 | -5.474 | 53.25% |
| 5 | -6.842 | 45.49% |
| 6 | -8.211 | 38.86% |
| 7 | -9.579 | 33.19% |
| 8 | -10.947 | 28.36% |
| 9 | -12.316 | 24.22% |
| 10 | -13.684 | 20.69% |
| 11 | -15.053 | 17.68% |
| 12 | -16.421 | 15.10% |
| 13 | -17.789 | 12.90% |
| 14 | -19.158 | 11.02% |
| 15 | -20.526 | 9.41% |
| 16 | -21.895 | 8.04% |
| 17 | -23.263 | 6.87% |
| 18 | -24.632 | 5.87% |
| 19 | -26.000 | 5.01% |

## Reference Formulas

Convert linear amplitude to dB:

```text
dB = 20 * log10(amplitude)
```

Convert percent to dB:

```text
dB = 20 * log10(percent / 100)
```

Convert dB to percent:

```text
percent = 100 * 10^(dB / 20)
```

## Useful Reference Points

| Linear Amplitude | Gain dB |
|-----------------:|--------:|
| 100% | 0.00 dB |
| 75% | -2.50 dB |
| 50% | -6.02 dB |
| 25% | -12.04 dB |
| 10% | -20.00 dB |
| 5% | -26.02 dB |
| 4% | -27.96 dB |

## Design Notes

- Percent labels are a UI convenience; FFmpeg receives dB gain values.
- AudioFix uses regular dB intervals, either entered directly or calculated from
  file count.
- Even dB spacing gives smoother audio behavior than exact linear-percent steps.
- LUFS normalization is intentionally not part of the current workflow because
  it may alter the relative feel of source game sounds.
- The addon has a separate off checkbox, so AudioFix does not need to generate
  extremely quiet files.
