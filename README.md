# JPEG2000 benchmark — a reproducible measurement procedure

**README for the `fastvideo/jpeg2000-benchmark` repository. Version of
19 August 2026.**

The results in "Results" come from a single measurement run made on
19 August 2026 on an RTX 4090.

---

Here is everything needed to measure the speed of JPEG2000 implementations on
a GPU and get your own numbers: the script, the benchmark harness for
nvJPEG2000, the results of the latest measurement runs together with the raw
logs, and an article with a detailed walk-through of the method.

## The problem

An engineer choosing a JPEG2000 codec has to compare implementations by other
people's results. Those results are usually not comparable, and here is why.

**Different settings mean different work.** Each implementation has its own
quality scale: "85" in one and "85" in another produce files of different
size, which means the codecs do different amounts of work. The comparison has
to be made at the same result — at a matching output file size — not at the
same number in a setting.

**The same fps figure means different things.** One codec on one card gives
values that differ by tens of times, and all of them are true: the difference
is in which work overlaps with which. A number without a description of the
mode means nothing.

**What goes into the measured time is usually not stated.** Whether the
measured time includes copying pixels to the card, assembling the compressed
file on the CPU, writing to disk — that affects the result more than the codec
itself does.

**Speed alone is not enough for a comparison.** A decoder that does less work
than it should looks faster.

Hence the goal of this repository: **not to prove that someone is faster, but
to give a procedure you can run yourself.** Numbers go stale with every driver
and library version; the procedure lives longer.

## What is measured

Four modes, because "codec speed" is not a single number:

| Mode                           | What it gives                                 |
|--------------------------------|-----------------------------------------------|
| Single frame, first run        | a baseline; it includes one-time costs        |
| Single image mode              | the time to process one frame, a stable value |
| Multithreaded, threads         | fps, stages of neighbouring frames overlap    |
| Multithreaded, threads + batch | fps at maximum GPU load                       |

**Batching is built differently in the two codecs, and you need to know that
when reading the tables.** The notation 8×2 means eight CPU threads, each with
two frames in flight on the GPU at the same time. There are exactly eight CPU
threads at any batch size; what doubles is the number of jobs the GPU works on
at one moment.

In fvJPEG2000 those frames go into the codec in a single call — the batch is
real. nvJPEG2000 has no such call: no function of the library takes an array
of images. So the load is built up differently — each thread gets as many
independent codec states and CUDA streams as the batch size says, and the
encodes are submitted one after another, without waiting for the result.

The means for this come from the NVIDIA library itself: multiple states, CUDA
streams, asynchronous calls. The only thing it lacks is a ready-made mode —
the order of calls has to be laid out by hand, and the NVIDIA samples do not
do it. The gain is real: 1.33x for the encoder, 1.17x for the decoder; without
it the gap in the tables would be larger. We take exactly these values as the
best for nvJPEG2000: the comparison has to be against the maximum the library
can give.

The measured time is the same for all participants, and mirrored:

- **encoder** — from pixels in GPU memory to compressed data in CPU memory;
- **decoder** — from compressed data in CPU memory to pixels in GPU memory.

Everything that happens on the compressed side is counted, including the CPU
parts on both sides. Copying pixels between the CPU and the card is not
counted. Disk is excluded entirely.

Every measurement run ends with a check: encode, decode, compare against the
source image. Lossless is expected to match byte for byte; for lossy, PSNR is
computed.

This page has the problem statement and the results. The step-by-step
walk-through of the method — why there are four modes, where the boundaries
run, how quality is matched and how the check is computed — is in the
[article](https://www.fastcompression.com/blog/jpeg2000-gpu-benchmark.htm?utm_source=github&utm_medium=referral&utm_campaign=j2k-benchmark&utm_content=method). It is also
kept here, next to the results of each run:
`results/2026-08-19/jpeg2000-gpu-benchmark-rtx4090.md`.

## Results

The test system and conditions. Every number refers to this configuration and
to no other.

| Item             | Value                                               |
|------------------|-----------------------------------------------------|
| GPU              | NVIDIA GeForce RTX 4090                             |
| Driver           | 610.88                                              |
| Fastvideo SDK    | 0.23.1.0, CUDA 13.3                                 |
| nvJPEG2000       | 0.11.0.51                                           |
| Operating system | Windows 11, 32 CPU threads, 128 GB RAM              |
| Images           | 1920×1080 and 3840×2160, 3 channels, 8 bit          |
| Settings         | code block 32×32, 6 levels, 1 layer, LRCP, no tiles |
| Measurement date | 19 August 2026                                      |

The compressed file sizes were matched on purpose: nvJPEG2000 quality was
tuned to the fvJPEG2000 file size to within 0.1%.

FV is the JPEG2000 codec from Fastvideo SDK, NV is the nvJPEG2000 library. In
parentheses — the "thread count × batch size" combination that gave the best
speed.

**Encoding, fps.**

| Task          | FV single | NV single | FV / NV | FV multithr. | NV multithr. | FV / NV |
|---------------|----------:|----------:|--------:|-------------:|-------------:|--------:|
| 2K, lossy     |       371 |       193 |   1.92x |   1913 (8×2) |   267 (16×2) |   7.17x |
| 2K, lossless  |       327 |       146 |   2.24x |   1134 (8×2) |   180 (16×2) |   6.30x |
| 4K, lossy     |       191 |       128 |   1.50x |    590 (8×4) |   155 (16×2) |   3.80x |
| 4K, lossless  |       138 |        56 |   2.44x |    364 (8×1) |    64 (16×2) |   5.66x |

**Decoding, fps.**

| Task          | FV single | NV single | FV / NV | FV multithr. | NV multithr. | FV / NV |
|---------------|----------:|----------:|--------:|-------------:|-------------:|--------:|
| 2K, lossy     |       140 |       289 |   0.48x |   1040 (8×4) |   1571 (8×4) |   0.66x |
| 2K, lossless  |       114 |       237 |   0.48x |   420 (16×2) |   469 (16×2) |   0.90x |
| 4K, lossy     |        92 |       193 |   0.48x |   371 (16×2) |    576 (8×2) |   0.64x |
| 4K, lossless  |        58 |        90 |   0.64x |   134 (16×2) |    146 (8×2) |   0.92x |

The ratio is FV / NV everywhere: above one means fvJPEG2000 is faster, below
one means nvJPEG2000 is faster.

The short conclusion. **fvJPEG2000 is faster at encoding** — by one and a half
to two and a half times in single image mode and by 3.8 to 7.2 times in
multithreaded mode; the latter mainly because the nvJPEG2000 encoder gains
almost nothing from multithreading. **nvJPEG2000 is faster at decoding** —
up to twice as fast in single image mode and one and a half times as fast in
multithreaded mode with lossy compression; with lossless compression the
difference almost disappears.

**Quality at equal file size.** Lossless compression in both codecs gives an
exact byte-for-byte match with the source image. With lossy compression, PSNR
is 40.42 dB against 40.60 for nvJPEG2000 on 2K and 41.97 against 42.23 on 4K,
that is, a difference within three tenths of a decibel — indistinguishable by
eye.

**Energy per frame at the best combination of threads and batch.** On encoding
2K lossy, 0.125 J for fvJPEG2000 against 0.624 for nvJPEG2000; on 4K lossless,
0.757 against 4.577. On decoding the gap is small: 0.187 against 0.230 on 2K
lossy. The full table, together with CPU load, is in `summary.txt`.

**Cross-decoding.** Each decoder was given not only its own stream but the
other one's as well: the difference nowhere exceeded four percent. So the
comparison of decoders is not quietly replaced by a comparison of what the
encoders produced.

What follows from this for a particular task is in the
[article](https://www.fastcompression.com/blog/jpeg2000-gpu-benchmark.htm?utm_source=github&utm_medium=referral&utm_campaign=j2k-benchmark&utm_content=practice), section "What this means in practice".

The full tables, including every search point, the quality check, energy per
frame and the stage breakdown, are in `results/<date>/summary.txt`. The same
data in machine-readable form is in `results.json`. The raw output of every
single launch, together with its command line, is in `logs.zip` next to them:
438 files, one per launch, so that any row of any table can be traced back to
the run that produced it.

## How to reproduce

You need: an NVIDIA GPU, the CUDA Toolkit, the nvJPEG2000 library (it ships
separately from the CUDA Toolkit — download it from the NVIDIA site or install
it as a Python package), Python 3.6 or newer with no third-party libraries,
and the Microsoft C++ compiler.

    python bench.py --final

The script builds the benchmark harness for nvJPEG2000 itself, prepares the
reference files, matches quality to an equal file size, runs the measurements
on both sides in four modes, checks quality and writes out finished tables. A
full measurement run takes about half an hour, three repeats per point. A
quick check:

    python bench.py --budget 300

Other options and the workflow are in `bench/README.md`.

**The Fastvideo side.** The speed reproduces on the demo build of Fastvideo
SDK. It is freely downloadable:
<https://www.fastcompression.com/download/demo/fvSDK-0.22.0.0-Win64-CUDA-12.6-Demo-Exp-2027-04-18.7z>

Note that the demo build above is 0.22.0.0 with CUDA 12.6, while the run
published here was made with 0.23.1.0 and CUDA 13.3 — the versions are stated
in the test system table, and results from different versions should not be
mixed in one table.

The quality check reproduces on the demo version too, even though it puts its
own watermark on the frame. The technique: the reference for PSNR is not the
source file but the frame that came back through a **lossless round trip on
the same build**. The watermark is applied before encoding, lossless mode
keeps everything bit for bit, so such a reference is exactly what the encoder
got. PSNR then measures the loss of the encoding itself, not the watermark.
The script checks this by itself: two independent lossless round trips must
match byte for byte, and the result of the check is printed in the report.

If you need a build without the watermark, write to us through the
[form on the site][form-build].

**The NVIDIA side.** Nothing has to be requested: nvJPEG2000 is free, it is
downloaded from the NVIDIA site or installed as the `nvidia-nvjpeg2k-cu12`
package. The benchmark harness is built from the sources kept here.

## What is not here

**Kakadu and Comprimato** — the other implementations an engineer looks at
first. They are not measured: we did not approach their developers and we do
not take it upon ourselves to interpret their licences for them. The procedure
is open — anyone who holds a licence can run the measurements and publish the
result.

**OpenJPEG** — the open CPU implementation everyone else is usually compared
against. It makes sense to add it separately: the gap between CPU and GPU is
orders of magnitude, and in one table with two GPU implementations it would
hide the very thing the table is made for.

**Bit depth above eight bits, 8K frames, multi-tile images, Jetson** — not in
this measurement run. Medical and satellite applications live exactly at 12
and 16 bits, and that is a separate piece of work.

## What is where

| Path                            | What it is                                         |
|---------------------------------|----------------------------------------------------|
| `bench/bench.py`                | the whole cycle: preparation, measurements, tables |
| `bench/nvj2k_bench.cpp`         | the benchmark harness for nvJPEG2000               |
| `bench/README.md`               | run options and workflow                           |
| `results/<date>/`               | tables, machine-readable data, raw logs in `logs.zip` |
| `results/<date>/<article>.md`   | snapshot of the article these results belong to    |

The article snapshot is not edited by hand: there is one author's text — the
article on the site — and here lies a dated copy tied to its own measurement
run. That way, a year later, it is clear which revision of the method produced
these results.

## Your own frames

The two images in this measurement run are ordinary photographic scenes. For
your project it is your own material that decides: your sensor, your
resolution, your bit depth, the compression ratio you need. Send us a few
frames — we will put them through both codecs and return the results and the
decoded images, so that the opinion is yours and not ours retold:
[send frames through the form][form-frames].

## What is measured on the Fastvideo side

This is the JPEG2000 module from Fastvideo SDK — a CUDA library that runs the
whole camera pipeline on the GPU; it is licensed per platform:
[fastcompression.com/products/gpu-jpeg2000.htm](https://www.fastcompression.com/products/gpu-jpeg2000.htm). nvJPEG2000 is free and ships separately from the CUDA
Toolkit.

## Links

- Article with the full walk-through of the method:
  https://www.fastcompression.com/blog/jpeg2000-gpu-benchmark.htm
- Product page: https://www.fastcompression.com/products/gpu-jpeg2000.htm
- Source images: https://www.fastcompression.com/img/test_j2k/2k_wild.ppm and
  https://www.fastcompression.com/img/test_j2k/4k_wild.ppm
- Fastvideo SDK demo build:
  https://www.fastcompression.com/download/demo/fvSDK-0.22.0.0-Win64-CUDA-12.6-Demo-Exp-2027-04-18.7z
- nvJPEG2000, separate download from the NVIDIA site: https://developer.nvidia.com/nvjpeg2000-downloads
- This repository: https://github.com/fastvideo/jpeg2000-benchmark

## Licences

There are three different things here under three different licences, see the
file `LICENSE-CONTENT.md`:

- **code** — the script and the benchmark harness — MIT, file `LICENSE`. Take
  it, change it, publish your own results;
- **the measurement results and this README** — everything under `results/`
  except the article snapshot, plus the README itself — CC BY 4.0. Move them into your
  own materials, rebuild them, compute on top of them. The README is here on
  purpose: the repository exists to be forked, and a fork almost always edits
  the README for itself;
- **the article snapshot** — `results/2026-08-19/jpeg2000-gpu-benchmark-rtx4090.md` —
  CC BY-ND 4.0.
  Reprinting it in full and quoting it are allowed; rewriting and translating
  it are by agreement.

Attribution to the source is required in all cases, and we ask that the
measurement conditions be kept next to the results.

Third-party software is not included here and is distributed under its own
terms: the Fastvideo SDK libraries, nvJPEG2000 and the CUDA Toolkit from
NVIDIA. Details are in `THIRD-PARTY.md`.

## Comments and errors

Found an error in the procedure — open an issue. An error in the method is
more useful to find before the next numbers are published than after. Ran it
yourself and got something different — that is interesting too: tell us which
card and which versions.

Everything to do with working with us — your own frames, a build without the
watermark, licence questions — goes through the
[form on the site][form-contact].

[form-build]: https://www.fastcompression.com/products/gpu-jpeg2000.htm?utm_source=github&utm_medium=referral&utm_campaign=j2k-benchmark&utm_content=build#contact-form
[form-frames]: https://www.fastcompression.com/products/gpu-jpeg2000.htm?utm_source=github&utm_medium=referral&utm_campaign=j2k-benchmark&utm_content=frames#contact-form
[form-contact]: https://www.fastcompression.com/products/gpu-jpeg2000.htm?utm_source=github&utm_medium=referral&utm_campaign=j2k-benchmark&utm_content=contact#contact-form
