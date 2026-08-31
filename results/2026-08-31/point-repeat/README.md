# One point, twenty launches

`nvJPEG2000, decoding 2K lossy, 8 threads, batch 1` — the one cell of the run
whose repeats do not scatter but split in two.

Measured with `j2k-point-repeat-02.py --go`: twenty launches of the disputed
point and twenty of a control point, alternating, 4288 frames each — the same
length the main run used on this point.

    group        launches   fps     watts   cores   wall
    slow                9    309.1    135    4.04   14.1 s
    fast               11    539.4    171    4.85    8.1 s

Inside each group the values agree to a tenth of a frame per second. The state
is decided once when the process starts and holds for the whole launch, from the
first frame to the last. Order of the groups over the twenty rounds:
`ssFFssFsFssFFFFFssFF`.

## What it is not

**Not thermal throttling.** The SM clock is 2745 MHz in both states, the
temperature 46–52 °C, and the power draw is nowhere near the 450 W limit.

**Not another program on the machine.** The control point, 8×2, was measured
between every pair and ran evenly: one group, median 754. The rounds where the
disputed point was slow (1, 2, 5, 6, 8, 10, 11, 17, 18) barely overlap with the
rounds where the control dipped (3, 8, 11).

**Not a property of the grid.** In the main run of the same day, 23 of the 24
nvJPEG2000 decoding points repeat to within a couple of per cent. Only this one
splits.

## What differs

The slow state spends **45 % more CPU time per frame**: 13.3 against 9.2 ms of a
core (`cores × wall / frames`). GPU utilisation is 97 and 98 % — the card is busy
either way, but in the slow state it gets less work done and draws 135 W instead
of 171.

So it is the CPU side of decoding that slows down. For nvJPEG2000 that is
`nvjpeg2kStreamParse` — Tier-2, which NVIDIA's own documentation calls the first
stage of decoding and which runs on the CPU. With batch 1 every thread goes
strictly round the loop parse → decode → wait, so the whole thing is bound by
latency, not by throughput.

**A working guess, not a finding:** how the operating system placed eight threads
across a 32-core AMD processor built from several dies. Eight threads inside one
die and eight threads spread across dies are not the same memory latency, and it
is settled when the process starts — which matches what we see. Not verified. To
verify it, run the same point with the threads pinned to cores.

## Which number is right

The neighbouring cells argue for the fast state. On nvJPEG2000 decoding, 32
threads with one frame each give the same figure as 8 threads with one frame
each:

    workload          8x1    32x1   ratio
    2K lossless       360     369    1.03
    4K lossy          208     207    0.99
    4K lossless       108     108    1.00
    2K lossy          310     532    1.71   the odd one out
    2K lossy          539     532    0.99   in line

The same for the batch: 8×1 → 8×4 gives 1.22, 1.24 and 2.05 on the other
workloads; with 310 it would be 3.33, with 539 it is 1.91.

The published table keeps the measured median, 310, and says so. Fitting a
number to a rule is a reliable way to get a tidy table and a wrong result.

## Files

| file | what it is |
|---|---|
| `report.txt` | the run in order, with watts, MHz, °C and utilisation, and the verdict |
| `runs.jsonl` | one line per launch |
| `logs.zip` | the output of all forty launches |
