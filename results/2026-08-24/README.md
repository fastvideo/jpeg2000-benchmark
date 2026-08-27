# Full comparison run — 24 August 2026

The run behind the current tables in the root `README.md` and behind the article. Both codecs, both
frames, both modes, on an RTX 4090: speed in four measurement modes, a full encode-decode-compare
cycle, energy per frame and the stage breakdown of a single frame.

It replaces the run of 19 August as the current one. The earlier run is kept in
`results/2026-08-19/` — it was made with the previous harness, and its energy figures were computed
a different way.

## System

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4090, 24 GB, driver 610.88, power limit 450 W |
| CPU / RAM | AMD, 32 threads / 128 GB |
| OS | Windows 11, Python 3.13.14 |
| Codecs | Fastvideo SDK 0.23.1.0 (CUDA 13.3), nvJPEG2000 0.11.0.51 |
| Frames | `2k_wild.ppm` (1920×1080) and `4k_wild.ppm` (3840×2160), 8 bit, 3 channels |
| Parameters | code block 32×32, 6 decomposition levels, one quality layer, LRCP, no tiling |
| Search grid | 8×1, 8×2, 16×2, 8×4 |
| Repeats per point | 3, the tables show the median |
| Bus, measured | 25 213 MB/s host → GPU |
| Harness | `bench-04.py`, version `2026-08-24.2` |
| Measurement date | 24 August 2026, 15:05 |

The quality parameter of nvJPEG2000 is tuned by search until its file matches the fvJPEG2000 file
to better than one tenth of a percent: 87.29 at 2K and 87.14 at 4K against 85 for fvJPEG2000. Both
codecs therefore handle the same amount of compressed data.

## What is in the files

| File | What it is |
|---|---|
| `results.json` | the primary machine-readable record: every measurement, the energy block, the stage breakdown, the round-trip checks |
| `results.csv` | the same measurements as a table |
| `summary.txt` | the human-readable report: quality ladder, all measured rows, ratios, energy, stage breakdown |
| `logs.zip` | 470 raw logs, one per launch, exactly as the codec printed them |
| `img/` | the charts of this run, the same ones the article uses |

`results.json`, `results.csv` and `logs.zip` are exactly as the harness wrote them.

## Energy: how it is measured, and which number to take

`results.json` gives four figures per point, and they differ by method rather than by chance:

| Field | Method |
|---|---|
| `j_per_frame_diff` | **the one used in the tables.** Two runs, N frames and 2N frames; the energy difference divided by N. Everything spent once per launch cancels out |
| `j_per_frame_counter` | the NVML cumulative energy counter over one run, divided by the frame count |
| `j_per_frame_sampled` | power sampled over the run, integrated over time |
| `j_per_frame_sampled_net` | the same, with the idle power of the card subtracted |

The four agree to within a few percent, which is the point of publishing all of them: a single
number with no method next to it cannot be checked.

## The stage breakdown is an estimate, not a measurement

`stage_breakdown` in `results.json` and the `img/j2k-stages-4090.webp` chart come from the `-info`
option of the Fastvideo test application, five launches per case, median. The logs are
`fv_stages_*` in `logs.zip`.

Two things follow, and both matter when reading the numbers:

- **the sum of the stages is larger than the real frame time** — 4.72 ms against 2.65 ms for
  encoding 2K. The option synchronises the stages against each other, and every one-off cost lands
  inside some stage. Compare stages with each other, do not add the column up;
- **it exists for fvJPEG2000 only.** nvJPEG2000 does not report stage times, so the table describes
  how one codec is built, not an advantage of one over the other.

## Reproducing

    python bench-04.py

with `J2kEncoderSample`, `J2kDecoderSample`, the nvJPEG2000 harness and both frames in the same
folder. The harness is time-budgeted: it probes the speed of each codec first and then sizes the
runs to fit the budget, so on a slower card the run takes about as long and the point count drops
rather than the wall clock growing.
