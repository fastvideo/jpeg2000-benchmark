# Run of 14 September 2026 — OpenJPEG on the CPU

The CPU side of the comparison: OpenJPEG on an AMD Ryzen 9 7950X, on the same
frames, at the same file size and with the same measurement boundaries as the
two GPU codecs in `results/2026-08-31/`. The GPU codecs were not measured again;
their numbers are that run's.

One run, six stages, 105 minutes:

    python opj-run-05.py --do

| | |
|---|---|
| CPU | AMD Ryzen 9 7950X, 16 cores, 32 logical |
| OS | Windows 11, build 26200 |
| OpenJPEG | 2.5.4, ordinary Release build; a second build with `/arch:AVX2` for one stage |
| Energy | AMD uProf 5.3.521.0, package power, sampled every 50 ms |
| Run script | `bench/opj-run-05.py`, version `opj-run-05 от 14.09.2026` |
| Harness | `bench/opj_bench-03/`, version 03 |
| Frames | `2k_wild.ppm` and `4k_wild.ppm`, the same as in the GPU run |
| Repeats per point | 3 after a warm-up, median in the tables; a point whose repeats disagreed by more than 7 % was measured 2 more times |

Stream settings match the GPU run: code block 32×32, six resolution levels,
lossy (9/7) and lossless (5/3). For lossy coding the compression ratio was
searched for until the file came out at the size our GPU encoder produces:
601 599 bytes against 601 703 on 2K, 1 275 289 against 1 275 547 on 4K. Both
lossless round trips came back byte for byte.

The measured region is the same as on the GPU: the frame is read from disk once
before timing; inside the timer the program works from host memory to host
memory.

## Stages

| stage | what it answers |
|---|---|
| `check` | the compression ratio for the target size, the lossless round trip, PSNR |
| `grid` | speed and busy cores for every split of the threads: frames in flight × threads inside one frame |
| `energy` | joules per frame at the best point of each task, differential method: N and 2N frames |
| `curve` | how speed grows with threads; OpenJPEG's own thread pool against whole frames per thread |
| `mem4k` | on 4K, frames in flight against the library's pool at the same total, with peak memory |
| `build` | the `/arch:AVX2` build of the library against the ordinary one, point by point, order alternated |
| `ref` | one reference point at the start and at the end, to see the machine drift |

## Headline numbers

Frames per second at the best split. "Split" is frames in flight × threads
inside one frame.

| workload | encode | split | decode | split |
|---|---:|---|---:|---|
| 2K lossy | 76.8 | 32×1 | 149.3 | 48×1 |
| 2K lossless | 63.3 | 32×1 | 80.1 | 48×1 |
| 4K lossy | 14.5 | 8×4 | 30.5 | 48×1 |
| 4K lossless | 15.0 | 12×4 | 22.2 | 48×1 |

Energy per frame, joules, the whole processor package at the best split. The
second column subtracts the idle draw of the package, 20.9 W in this run,
measured separately at the start of the stage (`uprof/idle/`).

| workload | encode | encode, less idle | decode | decode, less idle |
|---|---:|---:|---:|---:|
| 2K lossy | 2.324 | 2.070 | 1.129 | 0.996 |
| 2K lossless | 2.760 | 2.464 | 2.393 | 2.140 |
| 4K lossy | 10.637 | 9.356 | 4.989 | 4.322 |
| 4K lossless | 11.449 | 10.115 | 7.950 | 7.122 |

The `/arch:AVX2` build of the library changes the eight best points by −9.0 to
+7.5 %, and the two builds produce the same files. The reference point drifted
by 1.7 % over the run (75.3 frames per second at the start, 76.6 at the end).

## What is in this folder

| file | what it is |
|---|---|
| `summary.txt` | the report the run printed, all tables; it is in Russian |
| `results.csv` | one row per measurement; take numbers from here, `summary.txt` rounds them |
| `results.jsonl` | one line per measurement, written as it was made: 211 lines, 203 measurements and 8 computed `energy_result` lines |
| `best.json` | the best split of each of the eight tasks, as the energy stage read it |
| `logs.zip` | the output of every single launch, 710 files |
| `uprof.zip` | the 17 AMD uProf sessions: 16 energy points and the idle measurement, each with its `timechart.csv` |

Every line of `results.jsonl` carries `cmd`, the exact command line of that
measurement, and `bench_version`.
