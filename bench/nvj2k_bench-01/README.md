# bench version 01

The harness the results dated **19 August 2026** were made with. Kept here so
that run can be repeated; for current measurements use `../bench-06.py`.

    python bench.py --final

**The file inside is not renamed.** It carries no version number of its own, and
`results/2026-08-19/` was made with it under exactly this name. Renaming it would
make the folder of results describe a file that no longer exists. So the version
is carried by the folder instead — the same arrangement as `nvj2k_bench-01/`.

    bench.py   91880 bytes, md5 c87ca26919de0aa3b68dbed949ed4919

## What it does not do

Everything the later versions learned to do is missing here, and that is the
point of keeping it: the run of 19 August must be repeatable as it was, not
improved after the fact.

- the search grid has four points, not six;
- the decoding boundary is the one corrected on 28 August: the nvJPEG2000 side
  stopped the clock with the decoded frame still on the card;
- the single-frame decoding boundary is the one corrected on 31 August;
- results are written at the end of a run, not as each measurement is made;
- there is no `-version` check against the C++ harness, no repeat of points whose
  repeats disagree, no energy phase with two meters.

For what replaced each of these, see `../README.md` and the results folders.
