# nvj2k_bench version 03

The nvJPEG2000 side of the benchmark. One source file, built twice — once as an
encoder program and once as a decoder program — because that is how the
Fastvideo SDK samples it is compared against are laid out.

    nvj2kEncoderSample.exe
    nvj2kDecoderSample.exe

Both answer `-version` by printing the version and exiting without touching the
device, so which build made a set of results is a question with an answer rather
than a guess from the numbers.

## What changed from version 02

**One option, `-sync auto|spin|yield|block`, and nothing else.** It chooses how a
worker thread waits for the card: `cudaDeviceScheduleAuto` (the default, and the
behaviour of version 02), `...Spin`, `...Yield` or `...BlockingSync`. No timer,
no measurement boundary and no default was changed. With `-sync auto` this
program measures exactly what version 02 measured.

**Why it exists.** One point of the run of 31 August — nvJPEG2000, decoding 2K
lossy, 8 threads and batch 1 — has two stable states, 309 and 539 frames per
second. The state is drawn once at start-up and then holds for the whole run,
and no value ever lands between the two.

On 1 September the first suspect was ruled out by measurement. The processor is
an AMD Ryzen 9 7950X: two chiplets of eight cores each, and traffic between
chiplets costs more than traffic inside one. Pinning the eight worker threads to
one chiplet, to the other, evenly across both, and to eight distinct physical
cores — 36 runs in all — changes nothing: **both states appear in every set of
cores**, including the one where each thread has a physical core of its own. So
it is not thread placement.

The next suspect is the wait mode. `cudaDeviceScheduleAuto` picks between
spinning and yielding by a heuristic, once, when the context is created — which
is exactly when the state is drawn. The slow state also spends more processor
time per frame while the card draws *less* power, which is what a starved card
looks like. This option takes the choice away from the heuristic so that the
guess can be confirmed or dropped.

**The mode is read back, not assumed.** It is set before the context exists, then
read from the device with `cudaGetDeviceFlags` and printed:

    Sync mode: spin (asked spin)

If what the device reports is not what was asked for, the program prints why and
**refuses to measure**, exit code 2. A condition that did not take effect must
not produce a number that looks valid. This matters in practice: since CUDA 12
`cudaSetDevice` creates the context itself, so on any device other than 0 the
flag may well come too late — and then you are told, instead of getting a
plausible number measured under conditions nobody chose.

## Boundaries, in words

Unchanged from version 02.

| mode | what the timer covers |
|---|---|
| single frame, encoding | from the pixels already on the card to the compressed stream in host memory — the upload of the source frame is outside |
| single frame, decoding | from the compressed stream in host memory to the decoded frame on the card — the download is outside, `-nodownload` |
| threads and batch, both directions | host memory to host memory, transfers included on both sides |

Disk is excluded everywhere: nothing is written, `-discard`.

## Building

`CMakeLists.txt` and `build.sh` are the ones from `bench/nvj2k_bench-02/`, with
the source file name changed to `nvj2k_bench-03.cpp`. Nothing else about the
build differs: the same two targets, the same `BUILD_DECODER` definition for the
decoder, the same CUDA and nvJPEG2000 lookup.

(The README of version 02 still says these two files "have not been written and
tested yet". That sentence is out of date — both are in the repository. It is
worth fixing there.)

What the source needs: CUDA, the nvJPEG2000 library (free, downloaded separately
from NVIDIA), and a C++14 compiler.

## Earlier versions

`bench/nvj2k_bench-01/` and `bench/nvj2k_bench-02/` are kept next to this one,
untouched. The results dated 28 August were made with 01 and can only be
reproduced with it; the results dated 31 August were made with 02, and `-sync
auto` here reproduces them.
