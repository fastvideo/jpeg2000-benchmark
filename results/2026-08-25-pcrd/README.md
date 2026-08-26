# PCRD mode, first run — 25 August 2026

What it costs, in encoding speed and in image quality, to reach a **fixed output file size**
instead of letting the size follow from a quality setting.

fvJPEG2000 has two ways to set the loss and they combine: the quality parameter `-q`, which
controls quantization and lets the file size fall where it may, and PCRD mode (`-cr`), which is
given a compression ratio and discards the least significant bits of the code blocks until the
frame fits. This run measures the same output size reached in different ways, so that the encoder
does the same amount of work in every row and the rows can be compared.

nvJPEG2000 is not in this run: it has no mode that targets a file size.

## System

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4090, driver 610.88, power limit 450 W |
| OS | Windows 11 |
| Codec | Fastvideo SDK 0.23.1.0, CUDA 13.3 |
| Frames | `2k_wild.ppm` (1920×1080) and `4k_wild.ppm` (3840×2160), 8 bit, 3 channels |
| Parameters | 9/7 wavelet, code block 32×32, 6 decomposition levels, one quality layer, LRCP |
| Runs | 970 encoder launches, 9 h 26 min |

## What is in the files

| File | What it is |
|---|---|
| `summary.txt` | the run's own report: quality ladder, all measured rows, slowdown against the reference, stage breakdown under `-info` |
| `results.json` | the same data, machine readable |
| `results.csv` | the measured rows as a table |
| `logs.zip` | 970 raw encoder and decoder logs; each log carries its own parsed result in the header |

## How to read the rows

Every row for a given frame produces a file of the same size, to better than one tenth of a
percent. The reference row is `q85` — quality 85 and no rate control; this is the mode the article
uses for its main tables. `cr-only` is rate control alone, `q90+cr` and `q95+cr` are quantization
set first and PCRD trimming the rest.

Rows marked in `summary.txt` as **not binding** did not reach the target size: quantization alone
had already compressed harder than the requested ratio, so PCRD had nothing to trim. That is a
normal outcome, not a failed point, but such rows are not comparable with the others and are not
used in the article.

The ladder in this run goes above quality 100. Those points are measurements, not a recommendation:
above 100 lossy compression of these frames comes out **larger** than lossless, so the useful range
of the scale is 0 to 100.

## Reproducing

The harness for this run was `bench/pcrd-cost-01.py`. It has been superseded by
`bench/pcrd-cost-03.py`, which measures the same thing about ten times faster and writes results as
they are computed. The numbers of the two agree; see the run of 26 August.
