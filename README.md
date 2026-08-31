# JPEG2000 benchmark — a reproducible measurement procedure

Version of 31 August 2026. Latest full comparison run: 31 August 2026, on an RTX 4090.

> **Everything comes from one run, and only that run is kept.** Until 31 August the tables here
> were assembled from three separate series — encoding from one day, decoding from another,
> energy from a third — and rows from different series could not be divided by each other. The
> run of 31 August measures all of it at once, on an extended search grid, and it also corrects
> the single-frame decoding column: our harness used to copy the decoded frame back to host
> memory while the Fastvideo sample does not, so nvJPEG2000 came out slower than it is there.
> Details in `results/2026-08-31/README.md`.
>
> The earlier full runs — 19, 24 and 28 August — **have been removed from the working tree**,
> together with the harnesses that made them. Each of them contained figures we later found to
> be wrong, and keeping a corrected run next to three superseded ones only invites someone to
> quote the wrong table. They are in the repository history if anyone needs them:
> `git log --diff-filter=D -- results/` finds the commit that removed a file and
> `git show <commit>^:<path>` brings it back. The two PCRD runs stay: they measure a different
> thing and nothing in them was superseded.

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

Two measurement modes:

| Mode | What it gives |
|---|---|
| Single image mode | the stable processing time of one frame |
| Multithreaded, threads and batch | frames per second at the load a real pipeline puts on the card |

The multithreaded mode is swept over six combinations, all of them published: 8×1, 8×2, 16×2, 8×4,
32×1 and 32×2. The last two were added in this run to answer a direct question — is it enough to
give the library more CPU threads? On a 32-core machine, 32 threads is the whole machine.

"8×2" means eight CPU threads with two frames in flight on the GPU in each of them. The two codecs
reach that differently: fvJPEG2000 has a real batch — one call takes an array of images —
nvJPEG2000 has no such call, so the same effect is built by hand out of several codec states, CUDA
streams and asynchronous calls. That is done with the library's own facilities and it does help:
1.04 to 1.43 times on the encoder and 1.22 to 2.05 times on the decoder.

**The measured interval follows the mode, and that is stated on purpose.**

- **Single image mode.** From the data where the codec picks it up to the result on the other side:
  for the encoder, from the raw frame in GPU memory to the compressed image in host memory; for the
  decoder, mirrored. The copy of the raw pixels is outside the interval on both sides.
- **Multithreaded mode.** Host memory to host memory in both directions. The copy of the raw pixels
  is inside the interval on both sides.

Every CPU part of both codecs is inside the interval in both modes. Only disk work is outside.

The reason the two differ: in single image mode frames go one at a time and the codec reports the
time of its own stages, so the boundary can be an internal one. In multithreaded mode several
frames are on the card at once and the time of one stage of one frame cannot be separated from the
work on its neighbours — only external boundaries are observable.

For the multithreaded mode that boundary is the one a working system pays for. Frames arrive in a
stream, several are in flight at once, and a decoded frame has to end up where the rest of the
pipeline expects it — in host memory. The transfer is not small: 6.2 MB per 2K frame and 24.9 MB
per 4K frame, which is 0.25 ms and 0.99 ms at the 25.2 GB/s measured on this machine.

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
| Search grid | 8×1, 8×2, 16×2, 8×4, 32×1, 32×2 |
| Series per point | 3, the tables show the median; a point whose repeats disagreed by more than 7 % was measured up to 2 more times |
| Measurement date | 31 August 2026 |

The quality parameter of nvJPEG2000 is tuned by search until its file matches the fvJPEG2000 file
to better than one tenth of a percent, so both codecs handle the same amount of compressed data.

### Encoding, frames per second

| Task | FV single | NV single | FV over NV | FV best | NV best | FV over NV |
|---|---:|---:|---:|---:|---:|---:|
| 2K, lossy | 381 | 198 | 1.93× | 1914 (8×2) | 292 (32×2) | 6.55× |
| 2K, lossless | 329 | 146 | 2.25× | 1179 (8×2) | 187 (32×2) | 6.31× |
| 4K, lossy | 195 | 128 | 1.53× | 616 (8×1) | 160 (16×2) | 3.86× |
| 4K, lossless | 140 | 56 | 2.49× | 371 (8×1) | 64 (16×2) | 5.77× |

### Decoding, frames per second

| Task | FV single | NV single | NV over FV | FV best | NV best | Difference |
|---|---:|---:|---:|---:|---:|---:|
| 2K, lossy | 144 | 298 | 2.07× | 1024 (8×4) | 1033 (8×4) | NV +0.8 % |
| 2K, lossless | 116 | 237 | 2.04× | 436 (32×2) | 438 (8×4) | NV +0.3 % |
| 4K, lossy | 96 | 193 | 2.01× | 394 (32×2) | 428 (8×4) | NV +8 % |
| 4K, lossless | 59 | 91 | 1.53× | 145 (32×1) | 134 (8×4) | FV +8 % |

**Encoding is faster with fvJPEG2000** — 1.5 to 2.5 times in single image mode and 3.9 to 6.6 times
at the best combination of threads and batch. The main reason is that the nvJPEG2000 encoder gains
almost nothing from multithreading: eight threads give it 1.035 times, against 2.7 to 4.7 times for
fvJPEG2000. Thirty-two threads do not change that — on 2K they buy it about 5 %, which is inside
the scatter of its own repeats, and on 4K nothing at all.

**On decoding the single frame and the loaded pipeline say different things.** In single image mode
nvJPEG2000 is ahead by 1.5 to 2.1 times — on three tasks out of four exactly twice — and where the
time of one frame is what matters, that is the number that counts. At the best combination of
threads and batch the gap closes: on 2K the two decoders are within a percent of each other and the
lead changes hands, on 4K the gap is about eight percent and it also goes both ways.

**CPU cores are part of the price.** At its optimum the fvJPEG2000 encoder occupies 7.0 to 7.6
cores against 14.7 to 29.8 for nvJPEG2000. At decoding it is the other way round: nvJPEG2000 gets
by on 3.4 to 4.8 cores, while fvJPEG2000 occupies 26 to 29 on three tasks out of four, because its
optimum there landed on thirty-two threads and buys only a few percent of speed for it.

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
| 2K | lossy | 0.122 J | 0.523 J | 0.178 J | 0.254 J |
| 2K | lossless | 0.224 J | 1.373 J | 0.435 J | 0.794 J |
| 4K | lossy | 0.355 J | 1.199 J | 0.517 J | 0.653 J |
| 4K | lossless | 0.729 J | 4.195 J | 1.384 J | 2.471 J |

Energy repeats the speed picture on encoding but does not amplify it. On decoding the two codecs run
at nearly the same speed, and the frame still costs 1.3 to 1.8 times less with fvJPEG2000, because
its card draws 176–182 W against 255–343 W.

### One cell is not settled, and it is named rather than hidden

nvJPEG2000 decoding 2K lossy at 8×1 does not scatter — it splits in two. Twenty launches in a row
gave 309 frames per second nine times and 539 eleven times, with the state decided when the process
starts and held for the whole launch. It is not thermal and not another program on the machine: the
GPU clock and temperature are the same in both states and a control point measured in between ran
evenly. The slow state spends 45 % more CPU time per frame. The cause is on the CPU side and is not
established.

The table above carries the median of the run, 310. The neighbouring cells argue for 539 — on every
other nvJPEG2000 decoding task, 32 threads with one frame each give what 8 threads with one frame
each give, and only this cell would be an exception. We publish what was measured and say so.
The twenty launches, with clock, temperature, power and CPU load for each, are in
`results/2026-08-31/point-repeat/`.

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

    python bench-06.py                  prints how to start it and measures nothing
    python bench-06.py --final          the full cycle, three repeats per point, about an hour
    python bench-06.py --selftest       checks only, measures nothing, needs no card
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

On Windows `bench-06.py` builds the harness itself with the Microsoft compiler. On Linux — a Jetson
board among others — build it with CMake, from the folder of the harness version you want:

    cd bench/nvj2k_bench-02
    cmake -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j

If nvJPEG2000 is not in a standard place, add `-DNVJPEG2K_ROOT=/path/to/nvjpeg2k`. The two
executables land in `build/`; copy them next to the test frames. `build.sh` in the same folder does
the same thing with one `g++` call per executable, for when CMake is unavailable or too old.

The harness is a complete build set in its own folder — source, `CMakeLists.txt`, `build.sh` and
a `README.md` — so that a new source cannot be built with an old build file by accident.
`bench/nvj2k_bench-02/` is the version that made the run of 31 August, and the only one kept.

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
| `bench/bench-06.py` | the harness of the 31 August run: the full cycle, both codecs, energy |
| `bench/pcrd-cost-03.py` | the PCRD run: one output size reached in several ways |
| `bench/nvj2k_bench-02/` | the nvJPEG2000 harness: source, CMake, build script, README |
| `bench/make_charts-03.py` | draws the charts of the article from a results folder |
| `bench/j2k-nv-threads-and-states-02.py` | what the library gives on its own and what our way of driving it adds |
| `bench/j2k-point-repeat-02.py` | one point, many launches: one cluster of values or two |
| `bench/get-nvidia-sample-02.py` | downloads NVIDIA's own sample programs |
| `bench/README.md` | run options and workflow |
| `results/2026-08-31/` | **the only full run kept:** everything in one series, the extended grid, CPU load, and the twenty-launch re-measurement in `point-repeat/` |
| `results/2026-08-25-pcrd/` | PCRD, first run: 970 logs, quality ladder up to 120 |
| `results/2026-08-26-pcrd/` | PCRD, follow-up: quality 86, 87, 88 — the best point |

Every results folder holds `summary.txt` with the full tables, `results.json` with the same data in
machine-readable form, and `logs.zip` with every raw log. Each folder has a `README.md` of its own
that states what the run was for, on what system it was made and how to repeat it.

The working tree carries only what the current run needs. Superseded harnesses — `bench.py`,
`bench-04.py`, `bench-05.py`, `nvj2k_bench-01/` — and the results folders they made are in the
repository history: `git log --diff-filter=D -- bench/` finds the commit that removed a file and
`git show <commit>^:<path>` brings it back. Keeping stale copies next to current ones is how a run
ends up being repeated with the wrong script, and keeping superseded tables next to corrected ones
is how a wrong number gets quoted.

Every long-lived file carries its version in its name, and the version inside the file has to match
it. Where the name cannot change — as with the C++ harness, whose file has to stay byte-identical to
what built a given set of results — the version is carried by the folder name instead, and the
folder holds the whole build set rather than one changed part.

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

**The article snapshots** — `results/2026-08-31/fastvideo-vs-nvjpeg2000-rtx4090.md` and any later
one — are CC BY-ND 4.0:
reprint and quote in full, rewriting and translating by agreement.

In every case, name the source, and carry the measurement conditions along with the numbers.

Third-party software is not included in this repository and is distributed under its own terms: the
Fastvideo SDK libraries, nvJPEG2000 and the CUDA Toolkit. Details are in `THIRD-PARTY.md`.

## Comments and errors

If you find a mistake in the procedure, open an issue. An error in the method is more useful found
before the next numbers are published than after.

If your own numbers come out different, write which card and which versions you used — that alone
usually explains it.

Business questions — a build, your frames, licensing — go through the form on the site.
