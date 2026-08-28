# Full comparison run — 28 August 2026

The current run. It replaces the run of 24 August as the source of the tables in the root
`README.md` and in the article. The earlier run is kept in `results/2026-08-24/` with all of its
logs: the two can be compared line by line, and the reason they differ is stated below.

## What changed since 24 August

**The nvJPEG2000 harness measured decoding along a shorter path than the Fastvideo sample did.**

`bench/nvj2k_bench.cpp` is our own code: nvJPEG2000 ships no measuring application comparable to
the Fastvideo samples, so the harness is built from source in this repository. In the asynchronous
mode its decoder stopped the clock with the decoded pixels still in GPU memory. The Fastvideo
decoder, in the same mode, returns them to host memory. The harness nevertheless printed
`GPU pipeline including all transfers`.

The asynchronous mode is the one that models a working system: frames arrive in a stream, several
are in flight at once, and a decoded frame is returned to where the rest of the pipeline expects
it — in host memory. Host to host is therefore the boundary that matters, and the transfer left
out of the nvJPEG2000 figure is one a real system pays for.

The missing transfer is 6.2 MB per 2K frame and 24.9 MB per 4K frame: 0.25 ms and 0.99 ms at the
25.2 GB/s measured on this machine. The faster the decoder, the larger the share of a frame that
fixed cost takes — which is why it flattered nvJPEG2000 more than it would have flattered a slower
codec.

**Encoding is unaffected.** The upload of the frame was inside the measured region from the start,
and the encode figures of this run reproduce those of 24 August.

**Three smaller fixes in the same harness.**

- Sample precision is now taken from `maxval` instead of being rounded up to 16 bits. A 12-bit
  frame was being declared as 16-bit, which made the encoder code four extra bit planes. They are
  empty and the file barely grows, but the work is real. This affects 12-bit material only; the
  frames of this run are 8-bit.
- Options that would change what is encoded (`-noMCT`, `-cr`, `-s`, `-outputBitdepth`,
  `-overwriteSourceBitdepth`, `-noHeader`) used to be accepted and ignored. A command line could
  therefore look applied while the comparison ran on different terms. The harness now refuses to
  run when one of them is given.
- The second line of the summary repeated the first under a different name. This harness has no
  separate reader and writer threads, and now says so.

## What did not change

The compressed streams are the same size to the byte, and a lossless round trip still returns the
frame identical to the source for both codecs. Only the boundary of the measurement moved, not
what is being measured.

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
| Harness | `bench-04.py` version `2026-08-24.2`, and `bench/nvj2k_bench.cpp` |
| Measurement date | 28 August 2026, 15:55 |

The quality parameter of nvJPEG2000 is tuned by search until its file matches the fvJPEG2000 file
to better than one tenth of a percent: 87.29 at 2K and 87.14 at 4K against 85 for fvJPEG2000. Both
codecs therefore handle the same amount of compressed data.

**Which boundary each measurement used is recorded per row** in `results.csv`, in the `boundary`
column. `all` means host memory to host memory; `no_h2d` and `no_d2h` mean that the pixel-side
transfer was left out, which is what the Fastvideo samples do in single image mode. The summary
field `settings.boundary` in `results.json` describes that single-frame case only, and says nothing
about the multithreaded runs — a shortcoming of `bench-04.py`, to be fixed in its next version.

**One column of this run was measured on unequal terms.** In single image mode the nvJPEG2000
harness kept the copy of the decoded frame to host memory inside the timed region, while the
Fastvideo sample leaves it out. So the `NV single` column of the decoding table below is understated
by roughly one transfer per frame. It was found by reading the `boundary` column of `results.csv`
after the run: `no_d2h` for fvJPEG2000 against `default` for nvJPEG2000, where the two should have
matched. The harness now follows the mode — asynchronous includes the transfer, synchronous leaves
it out — and the column will be measured again rather than corrected by arithmetic. The
multithreaded columns, the encoding table and the energy figures are not affected: those were
measured `all` against `all`.

## Results

### Encoding, frames per second

| Task | FV single | NV single | FV over NV | FV best | NV best | FV over NV |
|---|---:|---:|---:|---:|---:|---:|
| 2K, lossy | 380 | 197 | 1.93× | 1916 (8×2) | 277 (16×2) | 6.91× |
| 2K, lossless | 330 | 145 | 2.27× | 1175 (8×2) | 180 (16×2) | 6.53× |
| 4K, lossy | 196 | 128 | 1.53× | 628 (8×2) | 158 (16×2) | 3.99× |
| 4K, lossless | 140 | 56 | 2.49× | 372 (8×1) | 64 (16×2) | 5.82× |

### Decoding, frames per second

| Task | FV single | NV single | NV over FV | FV best | NV best | Difference |
|---|---:|---:|---:|---:|---:|---:|
| 2K, lossy | 144 | 274 | 1.90× | 1029 (8×4) | 1045 (8×4) | NV +2 % |
| 2K, lossless | 116 | 223 | 1.93× | 427 (8×4) | 436 (8×4) | NV +2 % |
| 4K, lossy | 96 | 163 | 1.69× | 381 (16×2) | 424 (8×4) | NV +11 % |
| 4K, lossless | 59 | 83 | 1.40× | 139 (16×2) | 134 (8×4) | FV +4 % |

At the best combination of threads and batch the gap closes: three of the four points are within two
per cent and the lead changes hands, and only 4K lossy stays with nvJPEG2000, by 11 %.

The single-frame column is the one described above as measured on unequal terms. Subtracting the
transfer that should not have been there gives about 293, 235, 192 and 90 frames per second for
nvJPEG2000 — within one per cent of the 296, 236, 193 and 91 of 24 August, which were measured on
equal terms. On that footing nvJPEG2000 decodes a single frame about twice as fast, at 2K and at 4K
alike. These are estimates and are not carried into the tables; the column will be replaced by a new
measurement.

Cross decoding — each decoder run on a file made by the other encoder — moves the result by 3.3 %
at most, and by less than half a per cent in five combinations out of eight. Neither decoder gains
from being fed its own encoder's stream, so the comparison is not an artefact of how the two
encoders lay out their data.

### Quality at an equal file size

Lossless: both codecs return the frame byte for byte. Lossy, PSNR against the source:

| Image | fvJPEG2000, dB | nvJPEG2000, dB | Difference |
|---|---:|---:|---:|
| 2K | 40.42 | 40.60 | 0.18 |
| 4K | 41.97 | 42.23 | 0.26 |

### Energy per frame, at the best combination of threads and batch

Measured with the NVML cumulative counter, by difference: a run of 2N frames minus a run of N
frames, divided by N. That removes the fixed cost of starting up.

| Frame | Mode | Encoding FV | Encoding NV | Decoding FV | Decoding NV |
|---|---|---:|---:|---:|---:|
| 2K | lossy | 0.123 J | 0.534 J | 0.183 J | 0.250 J |
| 2K | lossless | 0.229 J | 1.391 J | 0.428 J | 0.799 J |
| 4K | lossy | 0.392 J | 1.167 J | 0.521 J | 0.647 J |
| 4K | lossless | 0.733 J | 4.189 J | 1.354 J | 2.476 J |

On decoding the two codecs run at nearly the same speed, and the frame still costs 1.2 to 1.8 times
less with fvJPEG2000: its card draws 183–202 W against 258–350 W.

## Spread between repeats

Every point is three repeats and the tables show the median. At the sixteen points that decide the
comparison the spread between repeats runs from 0.1 to 6.7 %, with a median of 1.4 %. The three
widest are all on encoding at 4K, and there the two codecs scatter about equally — 6.7 % against
6.3 % at 4K lossy — so the difference between them is not an artefact of the scatter.

## What is in this folder

| File | What it is |
|---|---|
| `README.md` | this file |
| `summary.txt` | the full tables as the run printed them |
| `results.json` | the same data machine-readable, plus every check |
| `results.csv` | one row per measurement |
| `logs.zip` | every raw log of the run |
| `img/` | the charts of the article, drawn from this folder by `bench/make_charts.py` |

## How to repeat

    python bench-04.py --final

The harness builds the nvJPEG2000 executables from `bench/nvj2k_bench.cpp` itself. Nothing in this
run needs a non-public build of anything: the Fastvideo demo SDK is the same version as here, and
nvJPEG2000 is a free download.

## How the error was found

The harness was read line by line after a plain question: does it measure what its own output
claims. It did not. Both runs stay in this repository, with every raw log, so that the difference
can be checked rather than taken on trust.
