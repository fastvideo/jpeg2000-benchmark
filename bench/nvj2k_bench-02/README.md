# nvj2k_bench version 02

The nvJPEG2000 side of the benchmark. One source file, built twice — once as an
encoder program and once as a decoder program — because that is how the
Fastvideo SDK samples it is compared against are laid out.

    nvj2kEncoderSample.exe
    nvj2kDecoderSample.exe

Both answer `-version` by printing the version and exiting without touching the
device, so which build made a set of results is a question with an answer rather
than a guess from the numbers.

## What changed from version 01

**1. The version is visible before the build, not after.** It lives in three
places at once and all three have to agree: the file name, the first line inside
the file, and the constant printed into every log. The benchmark script asks
both executables for their version before the first measurement and refuses to
measure if it does not match the source next to them.

**2. `-nodownload` is honoured, and the label follows the flag.** In single
frame mode the harness is now started with `-nodownload`, and it then prints
"excluding the device-to-host transfer" — the same flag decides the measurement
and the label. That matters: the Fastvideo sample started with `-discard` never
copies the decoded frame back to host memory, so measured the other way the two
sides were not mirror images and nvJPEG2000 came out slower than it is. That is
the error in the single-frame decoding column of the results dated 28 August.

**3. The asynchronous encoder no longer prints a label that contradicts the
flag.** It used to say "including all transfers" whatever was asked for.

No timer and no measurement boundary was changed.

## Boundaries, in words

| mode | what the timer covers |
|---|---|
| single frame, encoding | from the pixels already on the card to the compressed stream in host memory — the upload of the source frame is outside |
| single frame, decoding | from the compressed stream in host memory to the decoded frame on the card — the download is outside, `-nodownload` |
| threads and batch, both directions | host memory to host memory, transfers included on both sides |

Disk is excluded everywhere: nothing is written, `-discard`.

## Building

This folder is the whole build set: the source, `CMakeLists.txt`, `build.sh` and
this README. That is deliberate — with the build files one level up, a new source
could be built with an old build file and nobody would notice.

On Windows `bench-06.py` builds the harness itself with the Microsoft compiler,
and on the machine these results come from it lands in `bin/x64/Release` next to
the Fastvideo samples. On Linux, a Jetson board among others:

    cmake -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j

If nvJPEG2000 is not in a standard place, add `-DNVJPEG2K_ROOT=/path/to/nvjpeg2k`.
The two executables land in `build/`; copy them next to the test frames.
`build.sh` does the same with one `g++` call per executable, for when CMake is
unavailable or too old.

What the source needs: CUDA, the nvJPEG2000 library (free, downloaded separately
from NVIDIA), and a C++11 compiler.

## Version 01

`bench/nvj2k_bench-01/` is kept next to this one untouched. The results dated
28 August were made with it, and they can only be reproduced with it.
