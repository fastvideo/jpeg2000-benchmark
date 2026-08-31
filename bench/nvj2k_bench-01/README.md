# nvj2k_bench version 01

The harness the results dated **28 August 2026** were made with. Kept here
untouched so that run can be reproduced; for current measurements use
`../nvj2k_bench-02/`.

**The file inside is not renamed.** It carries no version line of its own, and
adding one would change the bytes that produced those results. So the version is
carried by the folder name instead, and the folder holds the whole set rather
than one changed part — otherwise a mixture could be built: a new source with an
old build file.

    nvj2k_bench.cpp   38264 bytes, md5 5a20d3e8512ee64edb29c0baa432cdca

`CMakeLists.txt` and `build.sh` are here too, unchanged, so this version can be
rebuilt without borrowing build files from the current one. They used to live one
level up, in `bench/`; they moved down here together with the source so that a
source and a build file of different versions cannot meet by accident.

## Why it was replaced

Two errors and one cosmetic fix, all of them described in
`../nvj2k_bench-02/README.md`:

1. **Single frame decoding was not mirrored.** This harness copied the decoded
   frame back to host memory even though the Fastvideo sample it is compared
   against does not. Measured that way nvJPEG2000 came out slower than it is —
   that is the error in the single-frame decoding column of
   `results/2026-08-28/`.
2. **The asynchronous encoder printed "including all transfers" whatever was
   asked for**, so the label was not evidence of anything.
3. There was no way to ask a built executable which source it came from.

Version 02 answers `-version`, honours `-nodownload` and prints a label that
follows the flag.

**No timer and no measurement boundary was changed between 01 and 02.** The
difference in the numbers comes from the copy that is no longer made, not from a
different way of counting.
