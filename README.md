# JPEG2000 benchmark — a reproducible measurement procedure

Version of 26 August 2026. Latest full comparison run: 24 August 2026, on an RTX 4090.

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
1.33× on the encoder and 1.17× on the decoder.

The measured interval runs from the source image in GPU memory to the compressed image in host
memory for the encoder, and the other way round for the decoder. Everything on the compressed side
and all the CPU parts of both codecs are inside it; copying the raw pixels between CPU and GPU and
any disk work are outside it.

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
| Measurement date | 24 August 2026 |

The quality parameter of nvJPEG2000 is tuned by search until its file matches the fvJPEG2000 file
to better than one tenth of a percent, so both codecs handle the same amount of compressed data.

### Encoding, frames per second

| Task | FV single | NV single | FV over NV | FV best | NV best | FV over NV |
|---|---:|---:|---:|---:|---:|---:|
| 2K, lossy | 378 | 197 | 1.92× | 1920 (8×2) | 267 (16×2) | 7.19× |
| 2K, lossless | 328 | 146 | 2.25× | 1173 (8×2) | 179 (16×2) | 6.54× |
| 4K, lossy | 195 | 127 | 1.53× | 618 (8×1) | 161 (16×2) | 3.84× |
| 4K, lossless | 140 | 56 | 2.49× | 367 (8×1) | 64 (16×2) | 5.73× |

### Decoding, frames per second

| Task | FV single | NV single | NV over FV | FV best | NV best | NV over FV |
|---|---:|---:|---:|---:|---:|---:|
| 2K, lossy | 143 | 296 | 2.07× | 1043 (8×4) | 1593 (8×2) | 1.53× |
| 2K, lossless | 116 | 236 | 2.04× | 427 (8×4) | 468 (8×2) | 1.10× |
| 4K, lossy | 96 | 193 | 2.01× | 379 (16×2) | 577 (8×2) | 1.52× |
| 4K, lossless | 59 | 91 | 1.53× | 137 (16×2) | 145 (8×2) | 1.06× |

**Encoding is faster with fvJPEG2000** — 1.5 to 2.5 times in single image mode and 3.8 to 7.2 times
at the best combination of threads and batch. The main reason is that the nvJPEG2000 encoder gains
almost nothing from multithreading: eight threads give it 1.04×, against 4.7× for fvJPEG2000.

**Decoding is faster with nvJPEG2000** — about 2 times in single image mode and 1.5 times at the
best combination in lossy mode. In lossless mode the difference nearly disappears: 6 % at 4K and
10 % at 2K.

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
| 2K | lossy | 0.125 J | 0.571 J | 0.182 J | 0.228 J |
| 2K | lossless | 0.227 J | 1.396 J | 0.430 J | 0.787 J |
| 4K | lossy | 0.381 J | 1.205 J | 0.520 J | 0.623 J |
| 4K | lossless | 0.738 J | 4.189 J | 1.370 J | 2.434 J |

Energy repeats the speed picture on encoding but does not amplify it. On decoding it goes the other
way: fvJPEG2000 is slower, yet its frame costs 1.2 to 1.8 times less, because its card runs at
178–184 W against 351–364 W.

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
download. The demo is 0.22.0.0 with CUDA 12.6 while the published results are 0.23.1.0 with CUDA
13.3, so do not mix numbers from the two. The quality check is reproducible on the demo build as
well: the script takes as its PSNR reference a lossless round trip made by the same build, so a
watermark, if the build has one, cancels out. Whether it has one is checked by the script itself —
two independent lossless round trips must match byte for byte. A build without a watermark is
needed only if you want to compare the decoded frame with the original file directly; ask through
the form on the site.

**On the NVIDIA side.** nvJPEG2000 is free: download it from NVIDIA or install the
`nvidia-nvjpeg2k-cu12` package. The harness is built from the sources in this repository. Nothing
has to be requested from anyone.

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

**The raw data of the 24 August run is not published here.** The tables above and the article come
from it; the runs whose logs are in the repository are listed in the next section.

## What is where

| Path | What it is |
|---|---|
| `bench/bench.py` | the harness of the 19 August run |
| `bench/bench-04.py` | the harness of the 24 August run: the full cycle, both codecs, energy |
| `bench/pcrd-cost-03.py` | the PCRD run: one output size reached in several ways |
| `bench/nvj2k_bench.cpp` | the benchmark harness for nvJPEG2000 |
| `bench/README.md` | run options and workflow |
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
  <https://www.fastcompression.com/download/demo/fvSDK-0.22.0.0-Win64-CUDA-12.6-Demo-Exp-2027-04-18.7z>
- nvJPEG2000 downloads: <https://developer.nvidia.com/nvjpeg2000-downloads>
- This repository: <https://github.com/fastvideo/jpeg2000-benchmark>

## Licences

Three of them, described in `LICENSE-CONTENT.md`.

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
