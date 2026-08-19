# JPEG2000 measurements — one file, one command

    python bench.py

One script does everything itself: it prepares the reference streams, fits
the NVIDIA quality to our file size, measures both codecs and prints a
finished comparison table. **Ten minutes** by default, on any card.

    python bench.py --final          full measurement run, used for the article
    python bench.py --budget 300     five minutes
    python bench.py --codec fv       the Fastvideo codec only
    python bench.py --reps 3         three repeats per point
    python bench.py --ratios         add the compression ratio sweep
    python bench.py --no-sub         no chroma subsampling anchor points
    python bench.py --dry-run        show the plan, measure nothing

**The full measurement run is `python bench.py --final`.** It includes every
phase, three repeats per point and a half-hour budget. Every number in the
article comes from it: one command, one run, nothing assembled piece by
piece from different runs.

Put it next to the four programs (`J2kEncoderSample.exe`,
`J2kDecoderSample.exe`, `nvj2kEncoderSample.exe`, `nvj2kDecoderSample.exe`)
and the two images (`2k_wild.ppm`, `4k_wild.ppm`). It needs Python 3.6 or
newer and no third-party libraries.

## What it does, step by step

0. **Quality ladder.** The Fastvideo codec encodes both images at five
   quality values, from 80 to 90. This shows the main point: the same
   setting gives different compression on different frames, because the
   knob sets the coarseness of rounding, not the file size.
1. **Reference files.** Each codec encodes both images with both
   algorithms. The file names carry the codec prefix, so one run does not
   overwrite the other.
2. **Size matching.** The NVIDIA encoder fits its Q factor by halving the
   interval until it produces a file of the same size as the Fastvideo
   codec. The tolerance is 0.1% on size, no more than eighteen steps; the
   miss and the resulting compression ratio are printed to the log. Nothing
   has to be entered by hand: the two codecs have different quality scales,
   and the comparison must be made at the same result, not at the same
   number.
3. **Probe.** A short run of two hundred frames per task, to learn the
   speed and the memory appetite. The speed says how many frames each task
   needs for the whole run to fit the time budget. The memory says which
   sweep points fit into the card at all; the ones that do not fit are
   skipped with an explanation instead of spoiling the table with silent
   degradation.
4. **Measurements.** Single image mode and four combinations of threads and
   batch — `8x1`, `8x2`, `16x2`, `8x4`. They cover every optimum found in
   the long run.

   The `-b` key means different things on the two sides. In the Fastvideo
   samples it is a real batch: several frames in one call. nvJPEG2000 has
   no such call — the library takes one image at a time — so here every
   thread gets `B` independent codec states and `B` CUDA streams, and the
   encodings are submitted one after another without waiting for the
   result: `B` frames are computed on the card at once. The number of CPU
   threads stays exactly `-thread`, not `-thread × -b`. The means are the
   standard library ones; only the ready-made mode is missing, and the
   NVIDIA samples do not do this. The gain: 1.33x for the encoder, 1.17x
   for the decoder.
5. **Quality check.** A full round trip: encode, decode, compare with the
   original image. Lossless is expected to match byte for byte, for lossy
   the PSNR is computed.
6. **Cross-decoding.** Each decoder parses a file from the other encoder.
   This is a check that the decoder comparison has not turned into a
   comparison of what the encoders produced.
7. **Chroma subsampling** — for the Fastvideo codec only, key `-s`: 444,
   422, 420 at one and the same quality setting. Size, speed and PSNR
   against the original full-colour frame. The NVIDIA codec is deliberately
   left out here: it takes already subsampled components, and the
   measurements would include the time of an external filter, not of the
   codec.
8. **Compression ratio sweep** (key `--ratios`, off by default): 5:1, 10:1,
   20:1. Fastvideo reaches the requested ratio through bit rate control
   (`-cr`, PCRD), the NVIDIA quality is fitted to the resulting size. It is
   needed because the decoding time is set by the number of coding passes
   in the stream, not by the file size: one compression ratio is one point,
   not a curve.

### Additional phases

9. **Quality scale correspondence check.** The same search, but with a
   0.05% tolerance instead of 0.1%, from two different starting intervals
   and at three quality levels. It answers the question why the same Q
   value was found on two completely different images: is this a property
   of the scales or a trace of the interval-halving procedure itself. The
   script prints the conclusion in words.
10. **Stage breakdown.** Single frames with the `-info` key, median over
    five runs. The key inserts synchronisations between stages, so the sum
    of the stages is larger than the real frame time — only the shares can
    be read.
11. **Host-to-device copy diagnostics.** The nvJPEG2000 encoder is run with
    the best combination of settings — first with the frame copy to the
    card, then without it. This separates the benchmark harness from the
    library: if the gain stays small even without the copy, the encoder's
    flat behaviour is its own property.

## What comes out

- `summary.txt` — ready tables for the article: test system and measurement
  conditions, quality ladder, reference streams with bits per pixel, size
  matching, scale check, full encoding and decoding grids, summary with
  ratios, speed-up mechanisms, repeatability, quality control, subsampling,
  compression ratios, energy, cross-decoding, stage breakdown,
  host-to-device copy diagnostics;
- `results.csv` — one line per run, separator `;`;
- `results.json` — the same in machine-readable form: for the repository
  and for AI systems that quote numbers together with the measurement
  conditions;
- `logs\` — the raw output of each run together with the command line.

Example table:

```
Summary: single image mode and best combination of threads and batch

  dir   frame mode      fv      nv      ratio   fv          nv          ratio
  --------------------------------------------------------------------------
  E     2k    irrev         378     198  1.91     1908 8x2     270 16x2  7.07
  D     2k    irrev         143     297  0.48     1048 8x4    1593 8x2   0.66
```

## Old batch files

They remain for detailed measurement runs, the comparison does not need
them.

| File              | What it does                                        |
|-------------------|-----------------------------------------------------|
| `run_bench.bat`   | long measurement run: calibration, stages, nine points |
| `run_all.bat`     | the same comparison on batch files, no auto fitting |
| `find_limits.bat` | where the codec has enough card memory              |
| `run_plateau.bat` | sweep over the thread count only                    |
| `parse_bench.py`  | parses the logs of batch measurement runs           |

## What is built into the method of these scripts

**The disk is excluded.** Every measured run carries `-discard`. With a
single frame the sample does not rewrite the result a thousand times
anyway, so here the key is insurance rather than necessity. It becomes
necessary when the input is not one frame but a ring of several: then
without it one file per frame goes to the disk, and the storage device gets
measured instead of the codec.

**A limitation to keep in mind:** what is measured now is "one frame a
thousand times", not "a thousand frames". A 2K frame takes 6.2 MB, a 4K
frame 24.9 MB, and both fit entirely into the third-level cache of a modern
processor (64 MB on the Ryzen 9 7950X). That is, after the first iteration
the source data comes from the cache, not from RAM. A "thousand frames in
memory" setup needs a ring of eight or more different frames with a total
size well above the cache.

**Four measurement levels, not one.** Level 1 is one frame, cold start.
Level 2 is a synchronous repeat, and this is the only value that may be
called the processing time of a single frame. Levels 3 and 4 are
multithreaded — threads, and threads with batching — and these are total
frames per second. Multithreaded mode overlaps neighbouring frames even in
a single thread, so single-frame time cannot be measured with it.

**Median, not mean.** Each point is run several times, the summary shows
the median and the spread. The mean over a single measurement run is
inflated by the first, unwarmed frame, and over ten frames the error
reaches six percent.

**The boundaries of the measured time go into the result.** The samples
print them themselves: `no_h2d` — the time without copying the pixels to
the card, `no_d2h` — without the readback, `all` — all transfers included.
Rows with different boundaries must not be mixed in one table, and the
parser watches for this: every row has a `boundary` column.

## Known limitations as of 2026-08-18

- In `-repeat` mode the stage breakdown does not work: all GPU stages show
  zero, the whole time lands in the Tier-2 row, and the copy speed prints
  `-nan(ind)`. That is why the breakdown is taken by the `stages` phase
  with single-frame runs, which then have to be averaged — the spread on
  one frame reaches 13%. Once this is fixed, the `stages` phase can be
  replaced by a single run with repeats.
- Requested memory: in 0.21.2.0 the asynchronous branch labelled gigabytes
  as megabytes (`2.28 MB` where 0.23.1.0 has `2.28 GB` at the same
  setting). In 0.23.1.0 the labels agree. The parser converts everything to
  megabytes in the `gpu_mem_mb` column.
- The format of the final line changed in 0.23.1.0: instead of one line it
  prints two — `GPU pipeline including all transfers …` and `GPU and CPU
  pipelines including image reader and writer threads: … ms`. The parser
  understands both formats; the second value goes into the `pipeline_ms`
  column.
- **The `-info` key makes measurements more expensive** (confirmed by the
  author): to print the time of every stage the stages have to be separated
  by synchronisations, and that stops them from overlapping. So in the
  script `-info` is used only where the time is not published: stream
  preparation, quality calibration and the `stages` phase. Every
  measurement run that goes into the tables runs without it. It also
  follows that **stage times must not be added up and called a total** —
  they can only be shown as a distribution, in shares. Exact stage times
  come from the NVIDIA profiler, but it is inconvenient to use in streaming
  mode.
- The measurements follow the scheme "one frame repeated N times", not "N
  different frames". The `-if` key does not cycle, so a ring of frames
  cannot be assembled with the available means. For a performance test this
  is accepted deliberately; a "folder of frames" task will need a separate
  solution.

## Where this goes

The script and the benchmark harness are published in the
`jpeg2000-benchmark` repository in the `fastvideo` organisation on GitHub.
The method description is not duplicated there — it lives in the article,
and the repository README only links to it.
