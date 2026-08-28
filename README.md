# JPEG2000 benchmark — a reproducible measurement procedure

Version of 28 August 2026. Latest full comparison run: 28 August 2026, on an RTX 4090.

> **The decoding figures changed on 28 August 2026.** Our own harness for nvJPEG2000 stopped
> the clock with the decoded pixels still in GPU memory, while the Fastvideo sample returned
> them to host memory — so the two sides were not measuring the same path. The harness is
> fixed and the run of 28 August measures both codecs from host to host. Encoding is
> unaffected. The details are in `results/2026-08-28/README.md`; the earlier run and its logs
> stay in `results/2026-08-24/` so the two can be compared line by line.

## The problem

Published JPEG2000 numbers are hard to compare with each other.

- The same quality setting — say 85 — gives files of different sizes in different codecs, and a
  codec that produced a smaller file did less work.
- The same "frames per second" means different things depending on the measurement mode.
- What was inside the measured interval is usually not stated: the copy to the GPU, the assembly on
  the CPU, the write to disk.
- Speed on its own is not enough: a codec is only comparable if the decoded frame is checked too.

This repository is not here to prove that someone is faster. It is here to give a procedure you can
run yourself. Numbers go stale with every driver and library version; the procedure lives longer.

## What is measured

Four measurement modes:

| Mode | What it gives |
|---|---|
| Single frame, first run | the baseline, one-off costs included |
| Single image mode | the stable processing time of one frame |
| Multithreaded, threads | frames per second with neighbouring frames overlapping |
| Multithreaded, threads and batch | frames per second at the highest GPU load |

"8×2" means eight CPU threads with two frames in flight on the GPU in each of them. The two codecs
reach that differently: fvJPEG2000 has a real batch — one call takes an array of images —
nvJPEG2000 has no such call, so the same effect is built by hand out of several codec states, CUDA
streams and asynchronous calls. That is done with the library's own facilities and it does help:
1.03 to 1.35 times on the encoder and 1.20 to 3.36 times on the decoder.

**The boundary is not the same in the two modes, and that is deliberate.** Each harness mirrors the
Fastvideo sample it is compared against.

In the multithreaded modes — the "best" columns of the tables, and the energy figures — the interval
runs from host memory to host memory: for the encoder, from the raw frame in CPU memory to the
compressed image in CPU memory; for the decoder, the other way round. The copy of the raw pixels
between CPU and GPU is inside it in both directions, and so is every CPU part of both codecs. Only
disk work is outside. That boundary is the one a working system pays for: frames arrive in a stream,
several are in flight at once, and a decoded frame has to end up where the rest of the pipeline
expects it. The transfer is not small — 6.2 MB per 2K frame and 24.9 MB per 4K frame, 0.25 ms and
0.99 ms at the 25.2 GB/s measured on this machine.

In single image mode the samples time the codec alone: the encoder starts with the pixels already on
the card, the decoder stops with them still there. That mode answers a different question — how long
one frame takes inside the codec — and the pixel-side transfer is left out of it on both sides.

Which boundary a given measurement used is recorded per row in `results.csv`, in the `boundary`
column: `all`, `no_h2d` or `no_d2h`.

Every measurement is followed by a full cycle: encode, decode, compare with the source. Lossless
must match byte for byte; for lossy, PSNR is computed.

**Rate control is measured separately.** fvJPEG2000 has two ways of setting the loss and they
combine: the quality parameter `-q`, which controls quantization and lets the file size fall where
it may, and PCRD mode (`-cr`), which is given a compression ratio and discards the least
significant bits of the code blocks until the frame fits. nvJPEG2000 has no mode that targets a
file size, so the PCRD runs are one-sided by nature and live in their own results folders.

The full walk-through of the method is the article:
<https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm>

## Results

### Test system

| Item | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 4090, 24 GB |
| GPU driver | 610.88 |
| GPU maximum power | 450 W |
| CPU | AMD, 32 threads |
| RAM | 128 GB |
| Fastvideo JPEG2000 codec (FV) | Fastvideo SDK 0.23.1.0, CUDA 13.3 |
| nvJPEG2000 library (NV) | version 0.11.0.51 |
| Operating system | Windows 11 |
| Bus speed, measured | 25.2 GB/s from CPU to GPU |
| Images | 1920×1080 and 3840×2160, 3 channels, 8 bit |
| Settings | code block 32×32, 6 levels, 1 quality layer, LRCP, no tiles |
| Series per point | 3, the tables show the median |
| Measurement date | 28 August 2026 |

The quality parameter of nvJPEG2000 is tuned by search until its file matches the fvJPEG2000 file
to better than one tenth of a percent, so both codecs handle the same amount of compressed data.

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

> **The "NV single" column of this table is understated and will be measured again.** In the run of
> 28 August the nvJPEG2000 harness kept the copy of the decoded frame to host memory inside the
> timed region in single image mode as well, while the Fastvideo sample leaves it out — so the two
> sides of that column were not measuring the same path. Subtracting the transfer gives about 293,
> 235, 192 and 90 frames per second, within one per cent of the figures of 24 August, which were
> measured on equal terms. The harness now follows the mode, and the column will be replaced by
> measurement rather than by arithmetic. Everything else in these tables is unaffected: the "best"
> columns, the encoding table and the energy figures were measured from host to host on both
> sides.

**Encoding is faster with fvJPEG2000** — 1.5 to 2.5 times in single image mode and 4.0 to 6.9 times
at the best combination of threads and batch. The main reason is that the nvJPEG2000 encoder gains
almost nothing from multithreading: eight threads give it 1.04 to 1.10 times, against 2.7 to 4.7
times for fvJPEG2000.

**On decoding the single frame and the loaded pipeline say different things.** In single image mode
nvJPEG2000 is ahead by 1.4 to 1.9 times, and where the time of one frame is what matters, that is
the number that counts. At the best combination of threads and batch the gap closes: in three cases
out of four the two decoders are within two per cent of each other and the lead changes hands, and
only at 4K lossy does nvJPEG2000 stay ahead, by 11 %.

### Quality at an equal file size

Lossless: both codecs return the frame byte for byte. Lossy, PSNR against the source:

| Image | fvJPEG2000, dB | nvJPEG2000, dB | Difference |
|---|---:|---:|---:|
| 2K | 40.42 | 40.60 | 0.18 |
| 4K | 41.97 | 42.23 | 0.26 |

Tenths of a decibel — indistinguishable by eye.

### Energy per frame, at the best combination of threads and batch

| Frame | Mode | Encoding FV | Encoding NV | Decoding FV | Decoding NV |
|---|---|---:|---:|---:|---:|
| 2K | lossy | 0.123 J | 0.534 J | 0.183 J | 0.250 J |
| 2K | lossless | 0.229 J | 1.391 J | 0.428 J | 0.799 J |
| 4K | lossy | 0.392 J | 1.167 J | 0.521 J | 0.647 J |
| 4K | lossless | 0.733 J | 4.189 J | 1.354 J | 2.476 J |

Energy repeats the speed picture on encoding but does not amplify it. On decoding the two codecs run
at nearly the same speed, and the frame still costs 1.2 to 1.8 times less with fvJPEG2000, because
its card draws 183–202 W against 258–350 W.

### PCRD mode: a fixed file size

At one and the same output size — the size that quality 85 gives — reaching it with rate control
instead of quantization alone costs speed and a little quality:

| Frame | How the size was reached | Single image mode | Slowdown | PSNR, dB |
|---|---|---:|---:|---:|
| 4K | quality 85, no PCRD | 187.2 | — | 41.97 |
| 4K | quality 90 and PCRD | 134.1 | 1.40× | 41.50 |
| 4K | quality 100 and PCRD | 120.1 | 1.56× | 41.24 |

In multithreaded mode the gap is larger — up to 2.76× at 2K. A follow-up run found the best point:
at 4K, quality 86 with PCRD is only 1.34× slower and gives a PSNR of 42.00 dB, no worse than
quantization alone. The rule that follows: set the base quality one or two units above the value at
which the frame already comes out at the size you need, and leave PCRD for the fine adjustment.

Full tables, the search points and the raw logs are in the results folders; see below.

## How to reproduce

You need an NVIDIA GPU, the CUDA Toolkit, the nvJPEG2000 library (a separate download from NVIDIA),
Python 3.6 or newer — no third-party Python packages — and the Microsoft C++ compiler for the
nvJPEG2000 harness, which the script builds itself.

    python bench-04.py --final          the full cycle, three repeats per point
    python bench-04.py --budget 300     a five-minute check
    python pcrd-cost-03.py              the PCRD run, about a minute
    python pcrd-cost-03.py --selftest   checks only, measures nothing

**On the Fastvideo side.** Speed is reproducible on the demo build of the SDK, which is a free
download and is the same version as the published results — 0.23.1.0 with CUDA 13.3. When a newer
demo appears, check its version before comparing: numbers from different SDK versions should not be
mixed. The quality check is reproducible on the demo build as well: the script takes as its PSNR
reference a lossless round trip made by the same build, so a watermark, if the build has one,
cancels out. Whether it has one is checked by the script itself —
two independent lossless round trips must match byte for byte. A build without a watermark is
needed only if you want to compare the decoded frame with the original file directly; ask through
the form on the site.

**On the NVIDIA side.** nvJPEG2000 is free: download it from NVIDIA or install the
`nvidia-nvjpeg2k-cu12` package. The harness is built from the sources in this repository. Nothing
has to be requested from anyone.

On Windows `bench-04.py` builds the harness itself with the Microsoft compiler. On Linux — a Jetson
board among others — build it with CMake:

    cmake -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j

If nvJPEG2000 is not in a standard place, add `-DNVJPEG2K_ROOT=/path/to/nvjpeg2k`. The two
executables land in `build/`; copy them next to the test frames. `bench/build.sh` does the same
thing with one `g++` call per executable, for when CMake is unavailable or too old.

`bench/README.md` has the run options and the workflow.

## What is not here

**Kakadu and Comprimato are not measured.** We did not approach their developers and we do not
interpret their licences. Any licence holder is welcome to run this procedure and publish the
result.

**OpenJPEG is not here either.** It is an open CPU implementation, and the gap between CPU and GPU
is large enough to swamp the comparison of two GPU codecs. It deserves its own run.

**Bit depth above 8 bits, 8K frames, multi-tile images and Jetson are not measured.** These are
separate application areas — medical, satellite, embedded — and each needs its own measurement
rather than a line in this table.

## What is where

| Path | What it is |
|---|---|
| `bench/bench.py` | the harness of the 19 August run |
| `bench/bench-04.py` | the harness of the 24 August run: the full cycle, both codecs, energy |
| `bench/pcrd-cost-03.py` | the PCRD run: one output size reached in several ways |
| `bench/nvj2k_bench.cpp` | the benchmark harness for nvJPEG2000, our own code |
| `bench/make_charts.py` | draws the charts of the article from a results folder |
| `bench/CMakeLists.txt` | builds that harness on Linux, Jetson included |
| `bench/build.sh` | the same build without CMake, one `g++` call per executable |
| `bench/README.md` | run options and workflow |
| `results/2026-08-28/` | **the current run:** tables, machine-readable data, every log, energy and the stage breakdown; the first run with the corrected decoder measurement |
| `results/2026-08-24/` | the previous run, kept for comparison: its decoding figures were measured along a shorter path on the nvJPEG2000 side |
| `results/2026-08-19/` | the first full comparison: tables, machine-readable data, 438 logs, and the article of that date |
| `results/2026-08-25-pcrd/` | PCRD, first run: 970 logs, quality ladder up to 120 |
| `results/2026-08-26-pcrd/` | PCRD, follow-up: quality 86, 87, 88 — the best point |

Every results folder holds `summary.txt` with the full tables, `results.json` with the same data in
machine-readable form, and `logs.zip` with every raw log. Each folder has a `README.md` of its own
that states what the run was for, on what system it was made and how to repeat it.

An article snapshot in a results folder is never edited by hand. There is one author's text — the
article on the site — and a dated copy next to the results, so that it is always clear which
version of the method produced which numbers.

## Your own frames

The two test images are ordinary photographic scenes. On your material — noise, text, medical or
satellite specifics — the ratios will be different. Send a few of your own frames through the form
on the site: we will run both codecs on them by this same procedure and return the tables and the
decoded images, so that the opinion is yours and not ours retold.

## What is measured on the Fastvideo side

The JPEG2000 module of the Fastvideo SDK — a CUDA library for a full camera pipeline on the GPU,
licensed per platform: <https://www.fastcompression.com/products/gpu-jpeg2000.htm>

nvJPEG2000 is free and ships separately from the CUDA Toolkit.

## Links

- Article, the method in full: <https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm>
- The same article in Russian: <https://www.fastvideo.ru/blog/jpeg2000-benchmarks.htm>
- Product page: <https://www.fastcompression.com/products/gpu-jpeg2000.htm>
- Source image, 2K: <https://www.fastcompression.com/img/test_j2k/2k_wild.ppm>
- Source image, 4K: <https://www.fastcompression.com/img/test_j2k/4k_wild.ppm>
- Fastvideo SDK demo:
  <https://www.fastcompression.com/download/demo/fvSDK-0.23.1.0-Win64-CUDA-13.3-Demo-Exp-2027-08-18.7z>
- nvJPEG2000 downloads: <https://developer.nvidia.com/nvjpeg2000-downloads>
- This repository: <https://github.com/fastvideo/jpeg2000-benchmark>

## Licences

Three of them. GitHub shows one MIT badge for the whole repository, because that is the licence
of the code; the measurement results and the article snapshots have their own, and all three are
described in `CONTENT-LICENSE.md`.

**The code** — the measurement scripts and the nvJPEG2000 harness — is MIT, see `LICENSE`. Take it,
change it, publish your own results.

**The measurement results and this README** — everything under `results/` except the article
snapshots, plus the README itself — are CC BY 4.0. Move them into your own materials, rebuild them,
compute on top of them. The repository exists to be forked, and a fork almost always edits the
README for itself.

**The article snapshots** — `results/2026-08-19/jpeg2000-gpu-benchmark-rtx4090.md` and any later
one — are CC BY-ND 4.0: reprint and quote in full, rewriting and translating by agreement.

In every case, name the source, and carry the measurement conditions along with the numbers.

Third-party software is not included in this repository and is distributed under its own terms: the
Fastvideo SDK libraries, nvJPEG2000 and the CUDA Toolkit. Details are in `THIRD-PARTY.md`.

## Comments and errors

If you find a mistake in the procedure, open an issue. An error in the method is more useful found
before the next numbers are published than after.

If your own numbers come out different, write which card and which versions you used — that alone
usually explains it.

Business questions — a build, your frames, licensing — go through the form on the site.
