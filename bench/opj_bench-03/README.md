# opj_bench version 03

The OpenJPEG side of the benchmark: a measurement program built against the
OpenJPEG library, with the same command-line keys and the same summary lines as
`nvj2k_bench`, so that one run script drives all three codecs the same way.

| file | what it is |
|---|---|
| `opj_bench-03.cpp` | the program |
| `CMakeLists.txt` | builds it against an OpenJPEG build tree or an installed OpenJPEG |
| `opj-build-03.cmd` | builds OpenJPEG twice — an ordinary Release build and one with `/arch:AVX2` — and the program against each |

These are byte for byte the files that built the run of 14 September 2026
(`results/2026-09-14/`). They are kept as they were for that reason, so two
lines in `opj-build-03.cmd` are out of date: it names `opj-run-04.py` as the
script to run next (the run was made with `bench/opj-run-05.py`), and its error
messages point to a folder of our working copy that has since been renamed.
Neither affects the build.

## Build

From "x64 Native Tools Command Prompt for VS":

    opj-build-03.cmd <OpenJPEG source> <root for the builds>

for example `opj-build-03.cmd D:\_Test\openjpeg-master D:\_Test\opj`. The result
is two folders, `<root>\builds\plain\` and `<root>\builds\avx2\`, each holding
one executable and the `openjp2.dll` it was built against. Windows loads the
dll from beside the executable, so the two must never share a folder.

The AVX2 comparison is about the library, not about this program: it does no
arithmetic worth vectorising, and all the work happens inside OpenJPEG. The
program prints which build it is (`Build: <tag>`) and whether it was itself
compiled with AVX2, and the run script checks the tag against the folder name.

## What is measured

The frame is read from disk once, before anything is timed, and converted into
the layout the library wants. Inside the timer the program works in memory,
from host memory to host memory — the boundary the GPU codecs are measured with.
This is why the standard `opj_compress` is not used: it starts a process and
reads a file for every frame, and both land inside its timer.

    opj_bench -i 2k_wild.ppm -a irrev -targetsize 601703
    opj_bench -i 2k_wild.ppm -a irrev -r 10.34 -repeat 2000 -thread 8
    opj_bench -decode -i frame.jp2 -repeat 2000 -thread 8

`-thread N` gives N worker threads, each coding whole frames of its own;
`-opjthreads K` gives OpenJPEG's own thread pool inside one frame. The run
script measures both and their products. The full list of keys is at the top of
`opj_bench-03.cpp`.
