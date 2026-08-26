# PCRD mode, follow-up run — 26 August 2026

The run of 25 August left a gap. It measured quality 85, 90, 95 and 100 combined with PCRD, and the
best variant was 90 — but at 85 the frame already comes out at the target size and PCRD has nothing
to trim, while at 90 the natural size is already one and a half times the target. The optimum lies
between them. This run measures quality **86, 87 and 88**.

## System

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4090, driver 610.88, power limit 450 W |
| OS | Windows 11 |
| Codec | Fastvideo SDK 0.23.1.0, CUDA 13.3 |
| Frames | `2k_wild.ppm` (1920×1080) and `4k_wild.ppm` (3840×2160), 8 bit, 3 channels |
| Parameters | 9/7 wavelet, code block 32×32, 6 decomposition levels, one quality layer, LRCP |
| Runs | 88 encoder launches, 1 min 19 s |
| Harness | `bench/pcrd-cost-03.py`, version `pcrd-2026-08-26.3` |

## Result

At 4K, quality 86 plus PCRD gives the smallest slowdown of every variant measured — 1.34 times
against quality 85 with no rate control — and a PSNR of 42.00 dB, which is no worse than a file of
the same size compressed by quantization alone (41.97). At 2K the speed at 86, 87 and 88 is the
same to within one percent, while PSNR falls: 40.40, 40.23, 39.98.

So the rule is: set the base quality one or two units above the value at which the frame already
comes out at the size you need, and leave PCRD for the fine adjustment.

The ratios agree with the run of 25 August: the "quality 100 plus PCRD" row gives 1.79 times at 2K
and 1.54 at 4K here, against 1.84 and 1.56 there. The absolute speeds differ by a few percent —
a different measurement session.

## What is in the files

| File | What it is |
|---|---|
| `results.jsonl` | the primary record: one line per result, written at the moment it was computed |
| `results.json`, `results.csv` | the same data, assembled at the end of the run |
| `summary.txt` | human-readable report: quality ladder, measured rows, slowdown against the reference, stage breakdown under `-info` |
| `logs.zip` | 88 raw encoder logs; each log carries its own parsed result in the header |

`results.jsonl`, `results.json` and `results.csv` are exactly as the harness wrote them.
`summary.txt` is the same report rendered in English — the harness prints it in Russian and no
number is changed.

## Reproducing

    python pcrd-cost-03.py --q-variants 86,87,88

with `J2kEncoderSample`, `J2kDecoderSample`, `2k_wild.ppm` and `4k_wild.ppm` in the same folder.
`--selftest` runs the checks only: that the frames and executables are there, that the encoder
accepts `-q` and `-cr` together, what quality it uses when none is given, and whether the build
watermarks the decoded frame.
