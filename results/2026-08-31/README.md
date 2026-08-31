# Run of 31 August 2026 — RTX 4090

One run for everything: encoding, decoding, energy and the quality checks. The
three previous series had been made on different days and could not be put in
one table; this one can.

    python bench-05.py --no-build --final

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4090, driver 610.88, power limit 450 W |
| CPU | AMD, 32 threads, 128 GB RAM |
| OS | Windows 11 |
| Fastvideo SDK | 0.23.1.0, CUDA 13.3 |
| nvJPEG2000 | 0.11.0.51 |
| Benchmark script | `bench-05.py`, version `2026-08-31.3` |
| nvJPEG2000 harness | `nvj2k_bench-02.cpp`, version 02 |
| Repeats per point | 3, median in the tables; a point whose repeats disagreed by more than 7 % was measured up to 2 more times |
| Search grid | 8×1, 8×2, 16×2, 8×4, 32×1, 32×2 |

**The script that made this run is not in the repository.** Right after the run `bench-05.py`
was superseded by `bench-06.py`, and the older copy was not kept: a harness sitting next to the
current one under a different number is how a run gets repeated with the wrong script. Three
things changed between the two, and each of them would change what a repeat produces, so
`bench-06.py` reproduces the method rather than this exact grid:

- a grid point that does not fit in card memory is now skipped for **both** codecs, decided once
  for the whole grid before measuring, instead of leaving a cell filled on one side only;
- the energy figure from the differential method now reaches `results.csv`, not only
  `results.json`;
- the best thread and batch combination for the no-upload phase is taken per frame size instead
  of once for the whole run.

The numbers in this folder are what `bench-05.py` version `2026-08-31.3` printed. Every launch it
made is in `logs.zip`, and `results.csv` and `results.jsonl` carry the exact command line of each
one, so nothing here has to be taken on trust.

Stream settings: code block 32×32, six resolution levels, one quality layer,
LRCP progression, tiling off, SOP and EPH markers off, 4:4:4. The nvJPEG2000
quality factor is matched to the file size our encoder produces at q = 85, to
better than 0.1 %.

## What is new in this run

**Two things that were wrong before are fixed here.**

1. **The single-frame decoding boundary is now mirrored.** The Fastvideo sample
   started with `-discard` never copies the decoded frame back to host memory
   and says so; our nvJPEG2000 harness copied it back by default. Measured that
   way the two halves were not mirror images and nvJPEG2000 came out slower than
   it is. In single frame mode the harness is now started with `-nodownload`.
   nvJPEG2000 single-frame decoding rises from 276 / 223 / 162 / 83 to
   298 / 237 / 193 / 91 frames per second.

2. **The grid was too short.** It had no point with many threads and one frame
   per thread, so it had never been checked what the library does when it is
   simply given more CPU threads. 32×1 and 32×2 were added. The answer: on
   encoding nvJPEG2000 gains about 5 % on 2K and nothing on 4K, and our own
   encoder gets *slower* with 32 threads.

**A combination that does not fit in card memory for one codec is left out for
both.** 4K at 32×2 does not fit for our encoder; the corresponding cells are
empty for nvJPEG2000 as well. A cell filled on one side and empty on the other
would read as "the other codec was slower here", when in truth it was never
measured.

## Headline numbers

Frames per second, best combination of threads and batch:

| workload | Fastvideo | nvJPEG2000 | ratio |
|---|---:|---:|---:|
| encode 2K lossy | 1914 (8×2) | 292 (32×2) | 6.55 |
| encode 2K lossless | 1179 (8×2) | 187 (32×2) | 6.31 |
| encode 4K lossy | 616 (8×1) | 160 (16×2) | 3.86 |
| encode 4K lossless | 371 (8×1) | 64 (16×2) | 5.77 |
| decode 2K lossy | 1024 (8×4) | 1033 (8×4) | 0.99 |
| decode 2K lossless | 436 (32×2) | 438 (8×4) | 1.00 |
| decode 4K lossy | 394 (32×2) | 428 (8×4) | 0.92 |
| decode 4K lossless | 145 (32×1) | 134 (8×4) | 1.08 |

Single image mode, frames per second:

| workload | Fastvideo | nvJPEG2000 | ratio |
|---|---:|---:|---:|
| encode 2K lossy | 381 | 198 | 1.93 |
| encode 2K lossless | 329 | 146 | 2.25 |
| encode 4K lossy | 195 | 128 | 1.53 |
| encode 4K lossless | 140 | 56 | 2.49 |
| decode 2K lossy | 144 | 298 | 0.48 |
| decode 2K lossless | 116 | 237 | 0.49 |
| decode 4K lossy | 96 | 193 | 0.50 |
| decode 4K lossless | 59 | 91 | 0.65 |

Energy per frame, joules, differential method on the card's own counter, at the
best combination:

| workload | Fastvideo | nvJPEG2000 |
|---|---:|---:|
| encode 2K lossy | 0.122 | 0.523 |
| encode 2K lossless | 0.224 | 1.373 |
| encode 4K lossy | 0.355 | 1.199 |
| encode 4K lossless | 0.729 | 4.195 |
| decode 2K lossy | 0.178 | 0.254 |
| decode 2K lossless | 0.435 | 0.794 |
| decode 4K lossy | 0.517 | 0.653 |
| decode 4K lossless | 1.384 | 2.471 |

## Acceptance checks

- Measurement boundaries mirrored on both sides in every workload — no
  mismatches.
- All four lossless round trips came back byte for byte identical.
- No watermark on either build, so PSNR is measured against the original.
- Two independent energy meters agree to 2 % on the median point and 10 % at
  worst.
- Cross-decoding: each decoder on the other encoder's stream changes the result
  by at most 1.4 %, so the streams give the decoders the same amount of work.

## One point is not settled, and it is named here

**nvJPEG2000, decoding 2K lossy, 8×1.** Its repeats do not scatter — they split
in two. The point was measured twenty more times in a row (`point-repeat/`):
nine launches gave 309 frames per second, eleven gave 539, and inside each group
the values agree to a tenth. The state is decided once when the process starts
and holds for the whole run.

It is not thermal and not another program on the machine: the clock is the same
2745 MHz in both states, the temperature 46–52 °C, GPU utilisation 97 and 98 %,
and the control point 8×2 measured in between ran evenly. What differs is the
CPU side — the slow state spends 45 % more CPU time per frame (13.3 against
9.2 ms of a core), and the card, given less work, draws 135 W instead of 171.

The table carries the median of this run, 310. The neighbouring cells argue for
539: on every other nvJPEG2000 decoding workload 32 threads with one frame each
give the same figure as 8 threads with one frame each (369 vs 360, 207 vs 208,
108 vs 108), and on 2K lossy 32×1 gives 532. With 539 the cell joins that rule;
with 310 it is the only exception. We publish what was measured and name the
doubt rather than fitting the number to the rule.

Everything else in the nvJPEG2000 decoding column repeats to within a couple of
per cent — 23 points out of 24.

## What is in this folder

| file | what it is |
|---|---|
| `summary.txt` | the report the run printed, all tables |
| `results.json` | the same, machine readable, plus the environment |
| `results.csv` | one row per measurement |
| `results.jsonl` | one line per measurement, written as it was made |
| `benchmarks.json` | the headline figures in one flat, machine-readable file |
| `logs.zip` | the output of every single launch, 580 files |
| `img/` | the five charts of the article, English, 1200 px |
| `point-repeat/` | the twenty-launch re-measurement of the disputed point |

`benchmarks.json` is a convenience file, not a new measurement. It carries eight
records — encoding and decoding, 2K and 4K, lossy and lossless — each with the
single-frame and best-point frame rates of both codecs, the energy per frame, the
CPU cores busy, the best thread and batch combination, and the compression ratio.
It is built from the published article by `_scripts/site-llms-j2k-04.py --json=`,
so it cannot drift away from the tables a reader sees. Everything in it is also in
`results.json`, which stays the primary record: `benchmarks.json` exists because a
machine reading `llms.txt` should be able to reach the numbers in one hop.

The article that goes with these numbers:
[fastcompression.com](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm)
