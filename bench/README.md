# JPEG2000 measurements — one file, one command

    python bench-06.py

Run with no options it measures nothing: it prints how it can be started, what
has to be next to it and what is missing right now, and exits with code 1, so no
wrapper mistakes it for a finished run. A long run is asked for by name.

    python bench-06.py --final       full measurement run, used for the article
    python bench-06.py --selftest    checks only, measures nothing, needs no card
    python bench-06.py --build       builds the nvJPEG2000 harness and stops
    python bench-06.py --dry-run     show the plan, measure nothing
    python bench-06.py --budget 300  five minutes
    python bench-06.py --codec fv    the Fastvideo codec only
    python bench-06.py --reps 3      three repeats per point
    python bench-06.py --ratios      add the compression ratio sweep
    python bench-06.py --no-energy   skip the energy phase
    python bench-06.py --no-sub      no chroma subsampling anchor points
    python bench-06.py --no-build    never invoke the compiler
    python bench-06.py --label 15W   suffix for the output folder name

**The full measurement run is `python bench-06.py --final`.** It includes every
phase, three repeats per point, and every measurement lasts a fixed length
instead of sharing out a budget — which is why it takes about an hour. Every
number in the article comes from it: one command, one run, nothing assembled
piece by piece from different runs.

**Ctrl-C stops a run at any point.** The program being measured is killed, the
results file is closed, and the script says what has already been measured and
where it is. Nothing is lost: every measurement is on disk the moment it is made.

Put it next to the four programs (`J2kEncoderSample.exe`,
`J2kDecoderSample.exe`, `nvj2kEncoderSample.exe`, `nvj2kDecoderSample.exe`)
and the two images (`2k_wild.ppm`, `4k_wild.ppm`). It needs Python 3.6 or
newer and no third-party libraries.

## Which build did the measuring

Every long-lived file carries its version in three places at once: the number in
the file name, a line inside the file, and a constant printed into the results.
Before the first measurement the script asks both nvJPEG2000 executables for
their version with `-version` and refuses to measure if it does not match the
source lying next to them. So "what was this run made with" is a question with an
answer rather than a guess from the numbers.

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
3. **Probe.** A short run per task, to learn the speed and the memory
   appetite. The speed says how many frames each task needs for the
   measuring window to come out the same length everywhere — a fast point
   must not degenerate into a fraction of a second of measuring while a slow
   one runs for half a minute. The memory says which sweep points fit into
   the card at all.

   **A point that does not fit for one codec is skipped for both.** Deciding
   that per codec, as earlier versions did, leaves a cell filled on one side
   and empty on the other, and that reads as "the other codec was slower
   here" when in truth it was never measured. The decision is taken once for
   the whole grid, before measuring, and the skipped points are printed by
   name.
4. **Measurements.** Single image mode and six combinations of threads and
   batch — `8x1`, `8x2`, `16x2`, `8x4`, `32x1`, `32x2`. The last two were
   added on 31 August: the earlier grid had no point where the threads are
   many and the frame in a thread is one, so it had never been checked what
   simply giving the library more CPU threads does.

   The `-b` key means different things on the two sides. In the Fastvideo
   samples it is a real batch: several frames in one call. nvJPEG2000 has
   no such call — the library takes one image at a time — so here every
   thread gets `B` independent codec states and `B` CUDA streams, and the
   encodings are submitted one after another without waiting for the
   result: `B` frames are computed on the card at once. The number of CPU
   threads stays exactly `-thread`, not `-thread × -b`. The means are the
   standard library ones; only the ready-made mode is missing, and the
   NVIDIA samples do not do this. The gain, read at one and the same thread
   count: 1.04 to 1.43 times for the encoder, 1.22 to 2.05 times for the
   decoder.

   **A point whose three repeats disagree by more than 7% is measured
   again**, up to two extra runs, and the median is then taken over all
   five. Points that still disagree are named in the report one by one, with
   the spread and the number of runs. A grid winner that is ahead of the
   runner-up by less than the repeats disagree is marked as a tie, not as a
   best combination — otherwise a table can name an optimum that was decided
   by half a percent between two noisy points.
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
    the best combination of settings **for that frame** — first with the
    frame copy to the card, then without it. This separates the benchmark
    harness from the library: if the gain stays small even without the copy,
    the encoder's flat behaviour is its own property. Taking one best point
    for the whole run, as earlier versions did, meant measuring 4K at a
    combination that does not fit in card memory.
12. **Energy, two meters.** Each point is measured twice, on N frames and on
    2N, and the energy per frame is taken as the difference divided by the
    difference in frames: everything that does not scale with the frame
    count — process start, buffers, the card's idle draw — drops out of the
    difference. The card's own cumulative energy counter is read through
    NVML; power sampling with `nvidia-smi` runs alongside as an independent
    second meter, and the two must agree. The CPU load of the codec is
    recorded here as well, in cores busy on average.

## Boundaries of the measured time

The samples print them themselves and the script records what they printed:
`no_h2d` — without copying the pixels to the card, `no_d2h` — without the
readback, `all` — all transfers included. Every row has a `boundary` column.

- **Single image mode:** `no_h2d` for encoding, `no_d2h` for decoding, on both
  sides. The transfer of the pixels themselves is outside the count.
- **Threads and batch:** `all` on both sides, host memory to host memory.

Rows with different boundaries must not be mixed in one table, and the script
checks this before writing the report: both codecs must share one boundary per
workload, and a mismatch stops the report rather than being footnoted.

The nvJPEG2000 harness is started with `-nodownload` in single image mode, and it
then prints "excluding the device-to-host transfer" — the same flag decides the
measurement and the label, so the boundary column is evidence and not decoration.

## What comes out

Everything is written the moment it is made, so an interrupted run keeps all of
it:

- `results.jsonl` — one line per measurement, appended and flushed as the run
  goes. This is the record; the three files below are a convenient view of it,
  and they can be rebuilt from it at any time;
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
Summary: single image mode and the best combination of threads and batch

  dir   frame alg              single, fps           multithreaded, fps
                                fv      nv ratio  fv          nv          ratio
  --------------------------------------------------------------------------
  E     2k    lossy            381     198  1.93    1914 8x2     292 32x2  6.55
  D     2k    lossy            144     298  0.48    1024 8x4    1033 8x4   0.99
```

## The other scripts here

| File | What it does |
|---|---|
| `make_charts-03.py` | the five charts of the article from a run folder, both languages, three widths |
| `j2k-nv-threads-and-states-02.py` | how much of the nvJPEG2000 speed is the library and how much is our way of driving it |
| `j2k-point-repeat-02.py` | one named point, many launches: do the values form one cluster or two |
| `get-nvidia-sample-02.py` | downloads NVIDIA's own decode and encode samples for the comparison above |

`j2k-point-repeat-02.py` loads `bench-06.py` as a module and takes the command
line, the output parsing and the result record from it, so its measurement is the
same one rather than a similar one.

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

**Two measurement modes, not one.** Single image mode is a synchronous repeat,
and it is the only value that may be called the processing time of a single
frame. Threads and batch is total frames per second. Multithreaded mode overlaps
neighbouring frames even in a single thread, so single-frame time cannot be
measured with it. Earlier versions of this file listed four levels; the two that
are gone — a first cold run and batching without threads — never turned out to
be the fastest and never went into a published table, so they are not measured
any more.

**Median, not mean.** Each point is run several times, the summary shows
the median and the spread. The mean over a single measurement run is
inflated by the first, unwarmed frame, and over ten frames the error
reaches six percent.

**Nothing is skipped silently.** A point that was not measured is named in the
report together with the reason. A silent omission reads as "everything was
measured", and that is not true.

**A missing value is checked against `None`, never against falsehood.** Zero is a
measurement. Earlier versions dropped whole rows from a table because a short
run's time rounded to zero and the zero was treated as "nothing measured".

## Known limitations as of 2026-08-31

- **nvJPEG2000 decoding of 2K lossy at 8×1 has two stable states.** Twenty
  launches in a row gave 309 fps nine times and 539 eleven times, with the state
  decided when the process starts and held for the whole launch. It is not
  thermal — the same GPU clock and temperature in both states — and not another
  program on the machine: a control point measured in between ran evenly. The
  slow state spends 45% more CPU time per frame, so the cause is on the CPU side,
  and it is not established. The measurement is in
  `results/2026-08-31/point-repeat/`. This is the only point where it happens;
  the other 23 nvJPEG2000 decoding points repeat to within a couple of percent.
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
  printed two, the second about reader and writer threads. Our own harness has
  no such threads and says so in one line since version 02; the parser
  understands both formats, and where a second value exists it goes into the
  `pipeline_ms` column.
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
