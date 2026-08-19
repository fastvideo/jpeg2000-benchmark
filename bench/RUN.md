# The full measurement run — what to do, step by step

Version of 2026-08-19. Every number in the article comes from this
measurement run, so there is no need to assemble them piece by piece from
different runs: one command, one run, one set of results.

---

## 1. What to put in one folder

| File                       | Where from                                 |
|----------------------------|--------------------------------------------|
| `bench.py`                 | from this archive                          |
| `nvj2k_bench.cpp`          | from this archive                          |
| `J2kEncoderSample.exe`     | Fastvideo SDK                              |
| `J2kDecoderSample.exe`     | Fastvideo SDK                              |
| `2k_wild.ppm`              | our test image set                         |
| `4k_wild.ppm`              | our test image set                         |

The script builds the nvJPEG2000 benchmark harness itself, it does not have
to be placed there. The Fastvideo SDK libraries must be located so that the
samples start the usual way.

## 2. What must be installed

- CUDA Toolkit;
- the nvJPEG2000 library — it is installed **separately from the CUDA
  Toolkit**: downloaded from the NVIDIA site or installed as the
  `nvidia-nvjpeg2k-cu12` package. The `nvjpeg2k.h` header and the
  `nvjpeg2k.lib` library are needed; if they are not next to the CUDA
  Toolkit, the path is set by the `NVJPEG2K_PATH` variable;
- Python 3.6 or newer. No third-party libraries are needed; if `numpy` is
  present in the system, PSNR is computed over all pixels, if not — over a
  sample, and the report says which way it was;
- the Microsoft C++ compiler. The simplest way is to run everything from
  the "x64 Native Tools Command Prompt for VS" — then the script builds the
  harness itself. If you start it from a plain command prompt, it will try
  to find Visual Studio through `vswhere`.

## 3. Before the run

- close everything that loads the GPU: a browser with video, other
  computations;
- if the card has been under load, let it cool down for a couple of
  minutes — otherwise the first frames land in the measurements at already
  reduced clocks;
- check that at least 2 GB is free on the disk: logs and intermediate
  files.

## 4. Quick check, one minute

    python bench.py --budget 60 --reps 1

The point is to make sure everything builds and starts, not to get numbers.
What the output should contain:

- the line `[0] nvJPEG2000 harness` and after it `built ...` or
  `already built and up to date`;
- in phase `[1b]`, eight lines with the sizes of the reference files;
- in phase `[2]`, two quality search lines with a miss below 0.1%;
- then the measurements, and the summary table at the end.

If something did not build, the build log with the full command line is in
the `cmp_<date>/logs/` folder.

## 5. The full measurement run

    python bench.py --final

Half an hour. What it does: the quality ladder, the reference files, the
size fitting, the scale correspondence check, the speed and memory probe,
the latency and four sweep points with three repeats each, quality control,
cross-decoding, subsampling, the compression ratio sweep, the stage
breakdown and a separate measurement of the host to device copy.

The run prints every line as it becomes ready — if something has stopped,
it is visible at once, there is no need to wait for the end.

If half an hour does not suit you, you can set your own time:

    python bench.py --final --budget 3600

The script picks the frame count for that budget itself.

If there are several measurement runs and they have to be told apart, add a
label to the folder name:

    python bench.py --final --label 4090

The result is `cmp_<date>_4090`. On Jetson this is a convenient way to mark
the power mode.

## 6. What to send me

The whole `cmp_<date>` folder, as one archive. It contains:

| File           | What it is                                         |
|----------------|----------------------------------------------------|
| `summary.txt`  | ready tables, the article is written from them     |
| `results.csv`  | one line per run                                   |
| `results.json` | the same machine-readable, goes to the repository  |
| `logs/`        | the raw output of each run with the command line   |

## 7. What to look at yourself while the measurements run

Three places where the result can turn out wrong, and it is visible at
once.

**Quality search.** In phase `[2]` the miss must be below 0.1%. If it is
larger, the file sizes are not matched and the speed comparison loses its
value.

**Skipped sweep points.** If phase `[4]` shows lines
`skipped, needs ... MB of ... MB`, some point does not fit into the card
memory. That is normal and better than a silent slowdown, but such points
will not reach the article — tell me if there are many skips.

**Quality control.** In phase `[5]` the lossless mode must show an "exact
match". If instead there are differences across the whole frame rather than
in a single rectangle, something is wrong and the speed numbers are
meaningless.

## 8. What is new in this run

Three things that were not there before, and their result is interesting in
itself.

**Quality scale correspondence.** The script repeats the search with a
0.05% tolerance, from two different starting intervals and at three quality
levels. The answer is printed in words: whether this is a property of the
scales or a trace of the search procedure. One wording in section 3.3 of
the article depends on it.

**Demo build watermark.** The script checks whether it is applied
identically in two independent lossless round trips. If it is, quality can
be checked on the demo version, and no special build is needed in the
repository. This is the question that got in the way of an open project the
most.

**Stage breakdown.** It will show how much time each stage takes inside a
frame, including the assembly of interleaved RGB in the decoder. Whether a
note is needed in the decoding tables depends on this.

## 9. If something went wrong

- **"Not found in this folder"** — a program or an image is missing, the
  list is in the message;
- **the benchmark harness build failed** — see
  `cmp_<date>/logs/build_*.log`, the full compiler command is there;
- **the measurements hung** — every run is limited to fifteen minutes,
  after which `ERROR: timed out` is written and the measurements go on;
- **the numbers look strange** — do not delete the folder, send it as is:
  the logs hold the raw output, which shows what happened.
