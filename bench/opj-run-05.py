# -*- coding: utf-8 -*-
"""
opj-run-05.py - version 05, 14 September 2026

The full OpenJPEG run: speed grid, best point, energy with AMD uProf, and the
shape of the thread curve. Same frames, same parameters and same boundaries as
the GPU runs, so that the three codecs end up on one scale.

  python opj-run-05.py        show: what was found and what will be measured
  python opj-run-05.py --do   measure; the plan prints the estimate

Two states and no more, the house rule of 46.04. Without keys the script looks
for everything it needs, says what it found and where, prints the plan with a
time estimate and measures nothing. With --do it measures.

Nothing has to be passed on the command line: the builds, the frames and the
profiler are looked for in the places they live, and the run folder is made
next to the script. The rare keys are still there (--only, --best, --baseline,
and an override for every path), but they are for rare cases.

Stages: check, grid, energy, curve, mem4k, build. --only takes any subset,
in this order.

WHAT IS NEW IN 05

  1. The grid is built by TOTAL THREADS, not by a hand-written list of pairs.
     The bench has two knobs - how many frames are kept in flight, and how
     many threads the library is given inside one frame - and they multiply:
     eight frames with four threads each is thirty-two threads in all. The
     old list measured alternative splits at ONE total only (thirty-two), so
     the phrase "best point" rested on one rung of six. Now every total on
     the ladder gets every sensible split, and the split that won is recorded
     next to the number.

  2. Every row carries "total" (frames x pool) and "splits_tried" - how many
     splits were measured at that total. A chart can then mark by itself the
     points where "best" is backed by one measurement only, instead of the
     author remembering to say so.

  3. Full sweeps are spent where they pay. The run of 14.09 showed that on
     DECODING the library's own pool never wins: forty-eight frames, one
     thread each, took every one of the four decoding tasks. So decoding
     keeps the one-thread-per-frame ladder plus the splits at thirty-two,
     and encoding gets the full sweep. GRID_SPLIT_DIRS at the top says so in
     one place; put "D" in it and decoding gets the full sweep too.

  4. The build stage alternates the ORDER of the builds from point to point.
     In the run of 14.09 the baseline was always measured first and always
     scattered - 13 to 24 per cent on encoding - while the build measured
     right after it scattered 1 to 12. The warm-up was being charged to
     whichever build went first. The stage now records the position in the
     order with every row and prints the spread by position, so the next run
     can show whether alternating fixed it.

  5. Accuracy is deliberately NOT chased. Seven encoding points on 4K in the
     run of 14.09 scattered more than the seven per cent limit even after
     five repeats. Decision of 14.09: leave it. The story is fourteen frames
     a second against six hundred on the card, and a few per cent change
     nothing in it. The spread is printed honestly instead, and the summary
     lists the points that did not settle.

WHAT WAS NEW IN 04

  Builds are a folder, not two command-line keys. --builds points at one
  directory whose subdirectories are the builds: each holds one executable
  and the openjp2.dll it belongs to, and the subdirectory name is the build's
  name. One key covers two builds or five, and tomorrow's avx512 or clang
  build needs no change to the script.

  The first build in alphabetical order is the baseline, or --baseline names
  it. Everything except the build stage runs on the baseline; the build stage
  compares every other build against it, point by point.

  The program's own build tag is checked against the folder name. They
  disagree when the wrong dll ended up beside an executable - the one failure
  of this comparison that is invisible from the outside - and the run stops
  instead of producing a tidy table of nonsense.

WHAT WAS NEW IN 03

  1. PSNR lands in the results, not only in the log. Version 02 printed the
     check PSNR into the log file and dropped it on the floor, so the quality
     comparison had to be dug out of logs by hand. Rule for the engine: what
     is measured goes into results.jsonl.
  2. Peak working set is recorded with every measurement. The article explains
     the 4K collapse by memory; an explanation about memory should carry a
     memory number.
  3. New stage "mem4k" - the direct test of that explanation. It walks frames
     in flight against the library's own pool at a constant total thread count
     and watches speed and peak memory together. If the explanation is right,
     few frames with many threads each beats many frames with one.
  4. New stage "build" - the A/B of two builds of the LIBRARY, the ordinary
     one and one compiled with /arch:AVX2. Pass --exe-avx2. The two are
     measured alternately, point by point, so that the machine warming up
     does not get charged to one of them. Each executable reports its own
     build tag and the harness records it with every row; if both report the
     same tag the stage stops, because then it would not be an A/B at all.
  5. Best points are written to best.json and can be read back with --best,
     so the energy stage no longer needs the grid to have run in the same
     process. That was the sore point of 14.09: interrupting the run meant
     recomputing the grid.
  6. A reference point is measured at the beginning and at the end, and the
     drift between them is printed. On 14.09 the grid and the curve disagreed
     by four to five per cent, and it took a day to work out that the machine
     had simply warmed up over the hour.

The energy stage needs administrator rights (uProf reads the processor's own
power counters). Everything else does not.

Leaves opj-run_<date>_<time>.zip next to itself: summary, results.jsonl,
results.csv and the full output of every single run.
"""

import argparse
import csv as csvmod
import datetime
import json
import os
import platform
import re
import shutil
import tempfile
import subprocess
import sys
import time
import zipfile

VERSION = "opj-run-05 от 14.09.2026"

# ---------------------------------------------------------------------------
# what is measured
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# where things live
# ---------------------------------------------------------------------------
# Nothing of this is passed on the command line. The script looks through the
# lists below, takes the first that exists, and says which one it took. If
# none exists it says what it looked for and where, and stops - a traceback in
# the author's face is always the script's fault, never his (41.11 §0).
#
# Moved the folders? Edit the lists here, not the command line.

HERE = os.path.dirname(os.path.abspath(__file__))

# A build is a FOLDER: one executable and the openjp2.dll it was built
# against. On Windows the library is taken from beside the executable, so two
# executables in one folder would both measure whichever dll happens to be
# there. Every subfolder of this one is a build, and its name is the build's
# name.
BUILD_ROOTS = [
    r"D:\_Test\opj\builds",
    r"D:\_Test\opj_bench\builds",
    os.path.join(HERE, "builds"),
]

# A single executable, for when there is no builds folder at all.
EXE_PLACES = [
    r"D:\_Test\opj\builds\plain\opj_bench.exe",
    r"D:\_Test\opj_bench\build\Release\opj_bench.exe",
]

IMG_PLACES = [
    (r"D:\_Test\fvSDK-0.23.1.0-Win64-CUDA-13.3-Trial-Exp-2027-08-03"
     r"\bin\x64\Release"),
    r"D:\_Test\frames",
    os.path.join(HERE, "frames"),
]

IMAGES = [("2k", "2k_wild.ppm"), ("4k", "4k_wild.ppm")]
ALGS = ["irrev", "rev"]                      # 9/7 with losses, 5/3 lossless
ALG_RU = {"irrev": "с потерями", "rev": "без потерь"}

# The byte counts fvJPEG2000 produced at quality 85, the same ones nvJPEG2000
# was calibrated onto. Lossless has no target: the size is whatever it is.
TARGETS = {"2k": 601703, "4k": 1275547}

# Tighter than the 0.001 of the GPU runs. The smoke test hit +0.098 % on 2K,
# which was the tolerance talking, not the codec; nvJPEG2000 landed within
# 0.04 %, and the sizes have to be equally close on all three sides.
CALIB_TOL = 0.0003

CODE_BLOCK = 32
LEVELS = 6

# The grid, built by TOTAL THREADS. The bench has two knobs and they multiply:
# frames kept in flight, times threads the library is given inside one frame.
# Eight frames with four threads each is thirty-two threads in all - the same
# demand on the machine as thirty-two frames with one thread each, and a very
# different speed. Total threads is the only number the two knobs add up to,
# and it is the one to compare with the machine's thirty-two logical cores.
#
# TOTALS is the ladder. It goes past the core count on purpose: a best point
# on the last rung is not a best point, it is where we stopped looking.
# POOLS lists the splits tried at every rung; a split is used when it divides
# the total evenly.
#
# (1, 1) is the single-frame reference: one frame at a time, nothing
# overlapping. It is the closest thing a processor codec has to the
# single-frame mode of the article.
TOTALS = [1, 2, 4, 8, 16, 32, 48, 64]
POOLS = [1, 2, 4]

# Where the full sweep is spent. On decoding the run of 14.09 gave every one
# of the four tasks to forty-eight frames with one thread each: the pool never
# won there. So decoding keeps the plain ladder plus the splits at the totals
# listed below, and encoding gets every split at every rung. Put "D" into
# GRID_SPLIT_DIRS and decoding gets the full sweep as well - at the cost of
# about half an hour.
GRID_SPLIT_DIRS = {"E"}
GRID_SPLIT_TOTALS = [32]


def splits_for(total, pools=POOLS):
    """Раскладки при данном числе потоков всего: (кадров в работе, пул)."""
    return [(total // p, p) for p in pools if p <= total and total % p == 0]


def grid_points(direction):
    """Точки сетки для одного направления, по возрастанию числа потоков."""
    out = []
    for t in TOTALS:
        splits = splits_for(t)
        if direction not in GRID_SPLIT_DIRS and t not in GRID_SPLIT_TOTALS:
            splits = splits[:1]          # только «по одному потоку на кадр»
        for th, pool in splits:
            out.append((t, th, pool))
    return out


# Оставлено для старого кода, который спрашивает про край сетки.
POINTS = [(th, pool) for _t, th, pool in grid_points("E")]

# The thread curve, measured on 2K with losses only - it is about the shape,
# and the shape does not change from frame to frame enough to pay for it four
# times over.
CURVE_THREADS = [1, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64]
CURVE_POOL = [1, 2, 4, 8, 16, 32]
CURVE_COMBO = [(2, 2), (4, 2), (8, 2), (16, 2), (4, 4), (8, 4), (16, 4), (8, 8)]

# How long one measurement should take. The GPU runs have a floor of a
# thousand frames; a codec twenty times slower cannot keep that floor without
# turning one point into four minutes, so here the length is set by time and
# the floor is low. This is a difference in method and it belongs in the
# article, not in a footnote.
RUN_S = 8.0
MIN_FRAMES = 4
MAX_FRAMES = 40000
REPEATS = 3
RESPREAD_LIMIT = 7.0        # per cent between best and worst
RESPREAD_EXTRA = 2

ENERGY_RUN_S = 6.0          # the N run; the second one is twice that
UPROF_INTERVAL_MS = 50      # the probe of 11.09 held this one honestly

TIMEOUT = 1800

UPROF_DIRS = [
    r"C:\Program Files\AMD\AMDuProf\bin",
    r"C:\Program Files (x86)\AMD\AMDuProf\bin",
    r"C:\Program Files\AMD\AMD uProf\bin",
]
UPROF_EXE = "AMDuProfCLI.exe"

# ---------------------------------------------------------------------------

RE_SDK = re.compile(r"SDK version:\s*(\S+)")
RE_SIZE = re.compile(r"size\s*=\s*(\d+)\s*KB\s*\(([\d.]+):1\)")
RE_CALIB = re.compile(
    r"Calibration:\s*q\s*=\s*([\d.]+);\s*size\s*=\s*(\d+)\s*bytes;"
    r"\s*target\s*=\s*(\d+)\s*bytes;\s*miss\s*=\s*([-+]?[\d.]+)")
RE_SUMMARY = re.compile(
    r"for\s+(\d+)\s+images\s+per\s+(\d+)\s+threads?"
    r"\s*=\s*([\d.]+)\s*ms;\s*([\d.]+)\s*FPS;")
RE_EXACT = re.compile(r"matches the source bit for bit")
RE_POOL_REFUSED = re.compile(r"opj_codec_set_threads\((\d+)\) was refused")
RE_HANDOVER = re.compile(r"giving the frame to the library.*?\(([\d.]+) %")
# opj_bench-02 prints the processor time of the MEASURED REGION alone. The
# whole-process figure counts the frame being read and the warm-up as well,
# and on a thirty-two thread encode that halves the answer.
RE_CORES = re.compile(r"logical cores busy:\s*([\d.]+)")
RE_REGION_CPU = re.compile(r"CPU time inside the measured region:\s*([\d.]+)")
# New in 03. Version 02 printed this line into the log and recorded nothing,
# so the quality comparison of the three codecs had to be dug out of log files
# by hand. What is measured goes into the results.
RE_PSNR = re.compile(r"Check:\s*PSNR\s*=\s*([\d.]+)\s*dB")
RE_PEAKMEM = re.compile(r"peak working set:\s*([\d.]+)\s*MB")
RE_BUILD = re.compile(r"Build:\s*(\S+?);\s*this file compiled with AVX2:\s*(.+)")

OUT = []
ROWS = []
LOGDIR = None
JSONL = None


def say(s=""):
    print(s, flush=True)
    OUT.append(s)


def argnum(x, digits=4):
    return ("%." + str(digits) + "f") % x


def num(x, digits=1):
    if x is None:
        return "-"
    return argnum(x, digits).replace(".", ",")


def plural(n, one, few, many):
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def threads_word(n):
    return "%d %s" % (n, plural(n, "поток", "потока", "потоков"))


def median(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def spread_pct(v):
    v = [x for x in v if x is not None]
    if len(v) < 2 or not min(v):
        return 0.0
    return (max(v) - min(v)) / min(v) * 100.0


# ---------------------------------------------------------------------------
# processor time of one child process
# ---------------------------------------------------------------------------
# Copied from bench-06.py deliberately, character for character: the number of
# busy cores has to be counted the same way on all three codecs, or the column
# cannot be put in one table.

def rusage_children():
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_CHILDREN)
        return r.ru_utime + r.ru_stime
    except Exception:
        return None


def child_cpu_seconds(popen, before=None):
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class FILETIME(ctypes.Structure):
                _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

            def as_seconds(ft):
                return ((ft.high << 32) | ft.low) / 1e7

            creation, exit_, kernel, user = (FILETIME(), FILETIME(),
                                             FILETIME(), FILETIME())
            ok = ctypes.windll.kernel32.GetProcessTimes(
                int(popen._handle), ctypes.byref(creation), ctypes.byref(exit_),
                ctypes.byref(kernel), ctypes.byref(user))
            if not ok:
                return None
            return as_seconds(kernel) + as_seconds(user)
        except Exception:
            return None
    after = rusage_children()
    if after is None or before is None:
        return None
    return max(0.0, after - before)


# ---------------------------------------------------------------------------
# running one measurement
# ---------------------------------------------------------------------------

class Cfg(object):
    exe = None
    dry = True
    # The tag of the executable currently being measured. Set once the program
    # has said what it is, and written into every row: two builds that look
    # alike must never be confused in a table.
    build = None
    # [(name, exe), ...] - one entry per build, in the order they were found.
    # The first one is the baseline unless --baseline says otherwise.
    builds = []


CFG = Cfg()


def parse_output(text):
    r = {}
    m = RE_SDK.search(text)
    if m:
        r["sdk"] = m.group(1)
    m = RE_SIZE.search(text)
    if m:
        r["size_kb"] = int(m.group(1))
        r["ratio"] = float(m.group(2))
    m = RE_CALIB.search(text)
    if m:
        r["calib_q"] = float(m.group(1))
        r["calib_size"] = int(m.group(2))
        r["calib_target"] = int(m.group(3))
        r["calib_miss"] = float(m.group(4))
    m = RE_SUMMARY.search(text)
    if m:
        r["frames"] = int(m.group(1))
        r["threads_said"] = int(m.group(2))
        r["ms"] = float(m.group(3))
        r["fps"] = float(m.group(4))
    m = RE_HANDOVER.search(text)
    if m:
        r["handover_pct"] = float(m.group(1))
    m = RE_CORES.search(text)
    if m:
        r["cores_region"] = float(m.group(1))
    m = RE_REGION_CPU.search(text)
    if m:
        r["cpu_region_s"] = float(m.group(1))
    m = RE_PSNR.search(text)
    if m:
        r["psnr_db"] = float(m.group(1))
    m = RE_PEAKMEM.search(text)
    if m:
        r["peak_mb"] = float(m.group(1))
    m = RE_BUILD.search(text)
    if m:
        r["build"] = m.group(1)
        r["build_avx2_file"] = m.group(2).strip()
    if RE_EXACT.search(text):
        r["lossless_exact"] = True
    m = RE_POOL_REFUSED.search(text)
    if m:
        r["pool_refused"] = True
    return r


def run(args, log_name, wrapper=None):
    """One run of opj_bench. wrapper, when given, is the uProf command that
    starts it - the profiler launches the program itself, so the collection
    window and the program's life are the same window (checked 11.09)."""
    cmd = ([CFG.exe] + [str(a) for a in args]) if not wrapper \
        else (wrapper + [CFG.exe] + [str(a) for a in args])
    if CFG.dry:
        print("   would run:", " ".join(cmd))
        return {}
    t0 = time.time()
    before = rusage_children() if os.name != "nt" else None
    p = None
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        out, _ = p.communicate(timeout=TIMEOUT)
        text = out.decode("utf-8", "replace")
        cpu_s = child_cpu_seconds(p, before)
    except FileNotFoundError:
        text, cpu_s = "ERROR: %s not found\n" % cmd[0], None
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        text, cpu_s = "ERROR: timed out\n", None
    except KeyboardInterrupt:
        if p is not None:
            try:
                p.kill()
                p.communicate()
            except Exception:
                pass
        raise
    wall = time.time() - t0
    if LOGDIR:
        with open(os.path.join(LOGDIR, log_name + ".log"), "w",
                  encoding="utf-8") as fh:
            fh.write("$ " + " ".join(cmd) + "\n\n" + text)
    r = parse_output(text)
    r["wall_s"] = wall
    if cpu_s is not None:
        r["cpu_s"] = cpu_s
        if wall > 0:
            r["cores"] = cpu_s / wall
    r["cmd"] = " ".join(cmd)
    return r


def record(**kw):
    kw.setdefault("bench_version", VERSION)
    if CFG.build and "build" not in kw:
        kw["build"] = CFG.build
    ROWS.append(kw)
    if JSONL:
        line = dict((k, v) for k, v in kw.items() if k != "raw")
        line["at"] = datetime.datetime.now().isoformat(timespec="seconds")
        JSONL.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        JSONL.flush()
        os.fsync(JSONL.fileno())


# ---------------------------------------------------------------------------
# arguments of one measurement
# ---------------------------------------------------------------------------

def enc_args(path, alg, ratio, frames, th, pool):
    a = ["-i", path, "-a", alg, "-c", CODE_BLOCK, "-l", LEVELS,
         "-repeat", frames, "-thread", th]
    if alg == "irrev" and ratio:
        a += ["-q", argnum(ratio, 4)]
    if pool > 1:
        a += ["-opjthreads", pool]
    return a


def dec_args(ref, frames, th, pool):
    a = ["-decode", "-i", ref, "-repeat", frames, "-thread", th]
    if pool > 1:
        a += ["-opjthreads", pool]
    return a


def frames_for(fps, th):
    """How many frames this run should do, from the speed seen at the previous
    point. A run should last about RUN_S seconds.

    Two floors push against that: a run needs a few frames to be timed at all,
    and every thread should get at least one. Both floors are themselves capped
    at three times RUN_S, because on a slow point they cost minutes and buy
    nothing - at a fifth of a frame per second even four frames is twenty
    seconds of measurement."""
    if not fps or fps <= 0:
        return max(MIN_FRAMES, th)
    want = int(fps * RUN_S)
    floor = max(MIN_FRAMES, 2 * th)
    ceiling = max(MIN_FRAMES, int(fps * RUN_S * 3))
    return min(MAX_FRAMES, max(want, min(floor, ceiling)))


# ---------------------------------------------------------------------------
# stage 1: the checks and the calibration
# ---------------------------------------------------------------------------

def stage_check(imgdir, refdir):
    say("=" * 72)
    say("СТАДИЯ 1. Проверки и подбор коэффициентов сжатия")
    say("=" * 72)
    ratios, refs, sdk = {}, {}, None

    for tag, name in IMAGES:
        path = os.path.join(imgdir, name)
        if not os.path.isfile(path):
            say("НЕТ КАДРА: %s" % path)
            return None, None, None
        for alg in ALGS:
            # The four compressed frames are working files, not results: they
            # go to a temporary folder of their own and are removed when the
            # run ends. Nothing but text is left in the run folder.
            ref = os.path.join(refdir, "opj_ref_%s_%s.jp2" % (tag, alg))
            args = ["-i", path, "-a", alg, "-c", CODE_BLOCK, "-l", LEVELS,
                    "-verify", "-info", "-o", ref, "-opjthreads", 8]
            if alg == "irrev":
                args += ["-targetsize", TARGETS[tag], "-tol", CALIB_TOL]
            r = run(args, "check_%s_%s" % (tag, alg))
            sdk = r.get("sdk") or sdk
            if alg == "irrev":
                ratios[tag] = r.get("calib_q")
            if CFG.dry:
                pass
            elif alg == "irrev":
                say("%s %s: коэффициент %s, вышло %s байт при цели %d, "
                    "промах %s %%"
                    % (tag.upper(), ALG_RU[alg], num(r.get("calib_q"), 4),
                       r.get("calib_size"), TARGETS[tag],
                       num(r.get("calib_miss"), 4)))
            elif r.get("lossless_exact"):
                say("%s %s: кадр вернулся байт в байт, %s байт"
                    % (tag.upper(), ALG_RU[alg], os.path.getsize(ref)
                       if os.path.isfile(ref) else "?"))
            else:
                say("%s %s: КАДР ИЗМЕНИЛСЯ - дальше мерить нельзя"
                    % (tag.upper(), ALG_RU[alg]))
            refs[(tag, alg)] = ref
            record(stage="check", image=tag, alg=alg, **r)
    say("")
    return ratios, refs, sdk


# ---------------------------------------------------------------------------
# stage 2: the grid
# ---------------------------------------------------------------------------

def measure_point(mk, log, th, start_fps=None):
    """One point of the grid: three counted runs, the median, and more runs if
    the three disagree. A point whose repeats scatter is a point that measured
    the machine's mood, not the codec.

    The FIRST run at a point is a warm-up and is not counted. Version 01 had no
    such run, and the first counted run was sized blind - one frame per thread -
    so at thirty-two threads it lasted four tenths of a second and came out two
    to three times slow. That poisoned the spread column (128 % where the real
    scatter was a few per cent) and sent every single point to five runs
    instead of three. The medians survived it; nothing else did.

    start_fps is the speed of the previous point of the ladder. It only sizes
    the warm-up, so a wrong guess costs seconds, not correctness."""
    prev = start_fps
    warm = run(mk(frames_for(prev, th)), log + "_warm")
    if warm.get("fps"):
        prev = warm["fps"]
    vals, rows = [], []
    for k in range(REPEATS + RESPREAD_EXTRA):
        if k >= REPEATS and spread_pct(vals) <= RESPREAD_LIMIT:
            break
        r = run(mk(frames_for(prev, th)), "%s_r%d" % (log, k + 1))
        f = r.get("fps")
        if f:
            vals.append(f)
            prev = f
        rows.append(r)
    return median(vals), spread_pct(vals), vals, rows


def stage_grid(imgdir, ratios, refs):
    say("=" * 72)
    say("СТАДИЯ 2. Сетка по числу потоков всего")
    say("=" * 72)
    say("Потоков всего - это кадры в работе, умноженные на потоки внутри "
        "кадра.")
    say("На кодировании при каждом числе потоков меряются все раскладки, "
        "на декодировании")
    say("только «по одному потоку на кадр» плюс раскладки при %s."
        % ", ".join(str(t) for t in GRID_SPLIT_TOTALS))
    say("")
    best = {}
    for tag, name in IMAGES:
        path = os.path.join(imgdir, name)
        for alg in ALGS:
            for d in ("E", "D"):
                say("")
                say("--- %s %s, %s ---"
                    % (tag.upper(), ALG_RU[alg],
                       "кодирование" if d == "E" else "декодирование"))
                say("  всего  кадров  пул   кадр/с   разброс   ядер")
                rows = []
                prev = None
                pts = grid_points(d)
                tried = {}
                for total, _th, _pool in pts:
                    tried[total] = tried.get(total, 0) + 1
                for total, th, pool in pts:
                    if d == "E":
                        def mk(n, th=th, pool=pool, alg=alg, path=path,
                               tag=tag):
                            return enc_args(path, alg, ratios.get(tag), n,
                                            th, pool)
                    else:
                        ref = refs[(tag, alg)]

                        def mk(n, th=th, pool=pool, ref=ref):
                            return dec_args(ref, n, th, pool)
                    log = "grid_%s_%s_%s_%dx%d" % (tag, alg, d, th, pool)
                    fps, sp, vals, raw = measure_point(mk, log, th, prev)
                    # cores_region comes from opj_bench itself and covers the
                    # measured region only; cores is the whole process, the way
                    # bench-06.py counts it for the two GPU codecs. Both are
                    # kept, the first is the one to put in a table.
                    cores = median([x.get("cores_region") for x in raw]) \
                        or median([x.get("cores") for x in raw])
                    cores_proc = median([x.get("cores") for x in raw])
                    hand = median([x.get("handover_pct") for x in raw])
                    mem = median([x.get("peak_mb") for x in raw])
                    if fps is None:
                        say("  %5d  %6d  %3d   прогон не дал числа"
                            % (total, th, pool))
                        continue
                    prev = fps
                    say("  %5d  %6d  %3d   %6s   %5s %%   %4s"
                        % (total, th, pool, num(fps, 1), num(sp, 1),
                           num(cores, 1)))
                    row = dict(stage="grid", image=tag, alg=alg, direction=d,
                               total=total, threads=th, pool=pool, fps=fps,
                               splits_tried=tried[total],
                               spread_pct=sp, runs=len(vals), cores=cores,
                               cores_process=cores_proc, handover_pct=hand,
                               peak_mb=mem,
                               frames=raw[-1].get("frames") if raw else None)
                    record(**row)
                    rows.append(row)
                if rows:
                    b = max(rows, key=lambda x: x["fps"])
                    best[(tag, alg, d)] = b
                    say("  лучшая точка: %s всего, %d %s по %d %s на кадр, "
                        "%s кадр/с"
                        % (threads_word(b["total"]), b["threads"],
                           plural(b["threads"], "кадр", "кадра", "кадров"),
                           b["pool"],
                           plural(b["pool"], "поток", "потока", "потоков"),
                           num(b["fps"], 1)))
                    # A best point sitting on the last rung of the ladder is
                    # not a best point, it is where we stopped looking.
                    if b["total"] == max(TOTALS):
                        say("  ВНИМАНИЕ: это край лестницы, потолок не назван "
                            "- сетку надо вести дальше")
                    if b["splits_tried"] == 1:
                        say("  ВНИМАНИЕ: при %d потоках измерена одна "
                            "раскладка - слово «лучшая» тут не обеспечено"
                            % b["total"])
                    thin = sorted(t for t, k in tried.items() if k == 1)
                    if thin and d in GRID_SPLIT_DIRS:
                        say("  одна раскладка измерена при: %s потоках"
                            % ", ".join(str(t) for t in thin))
    say("")
    return best


# ---------------------------------------------------------------------------
# stage 3: energy, with AMD uProf
# ---------------------------------------------------------------------------

def find_uprof():
    p = shutil.which(UPROF_EXE)
    if p:
        return p
    for d in UPROF_DIRS:
        q = os.path.join(d, UPROF_EXE)
        if os.path.isfile(q):
            return q
    return None


def read_timechart(path):
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    idx = None
    for i, l in enumerate(lines):
        if l.startswith("RecordId,Timestamp"):
            idx = i
            break
    if idx is None:
        return [], []
    rows = list(csvmod.reader(lines[idx:]))
    hdr = [h.strip() for h in rows[0]]
    j = None
    for k, h in enumerate(hdr):
        if "package-power" in h.lower():
            j = k
            break
    if j is None:
        return [], []
    t, p = [], []
    for r in rows[1:]:
        if len(r) != len(hdr):
            continue
        try:
            hh, mm, ss, ms = [int(x) for x in r[1].strip().split(":")]
            tt = hh * 3600 + mm * 60 + ss + ms / 1000.0
            pp = float(r[j])
        except Exception:
            continue
        t.append(tt)
        p.append(pp)
    return t, p


def integrate(t, p):
    """Joules, by the real time stamps rather than the nominal interval. The
    probe of 11.09 asked for 100 ms and got 105 with six per cent of scatter;
    integrating by the nominal number would build in a systematic error."""
    if len(t) < 2:
        return None, None
    j = 0.0
    for k in range(len(t) - 1):
        dt = t[k + 1] - t[k]
        if 0 < dt < 5:
            j += (p[k] + p[k + 1]) / 2.0 * dt
    return j, t[-1] - t[0]


def find_csv(d):
    for root, _x, files in os.walk(d):
        for f in files:
            if f.lower().endswith(".csv"):
                return os.path.join(root, f)
    return None


def uprof_run(uprof, args, log_name, outdir):
    sub = os.path.join(outdir, "uprof", log_name)
    if not CFG.dry:
        shutil.rmtree(sub, ignore_errors=True)
        os.makedirs(sub, exist_ok=True)
    wrapper = [uprof, "timechart", "--event", "power",
               "--interval", str(UPROF_INTERVAL_MS), "-o", sub]
    r = run(args, log_name, wrapper=wrapper)
    if CFG.dry:
        return r
    csvp = find_csv(sub)
    if csvp:
        t, p = read_timechart(csvp)
        j, span = integrate(t, p)
        r["energy_j"] = j
        r["uprof_span_s"] = span
        r["uprof_samples"] = len(t)
        if p:
            r["power_avg_w"] = (j / span) if (j and span) else None
            r["power_max_w"] = max(p)
    return r


def idle_power(uprof, outdir):
    """A few seconds of nothing, to know what the package draws when it is not
    working. The differential method removes the fixed cost of a run, but not
    the idle draw during it - so it has to be measured and named, not assumed."""
    sub = os.path.join(outdir, "uprof", "idle")
    if CFG.dry:
        return None
    shutil.rmtree(sub, ignore_errors=True)
    os.makedirs(sub, exist_ok=True)
    cmd = [uprof, "timechart", "--event", "power", "--interval",
           str(UPROF_INTERVAL_MS), "--duration", "8", "-o", sub]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=180)
    except Exception:
        return None
    csvp = find_csv(sub)
    if not csvp:
        return None
    t, p = read_timechart(csvp)
    return median(p)


def stage_energy(imgdir, ratios, refs, best, outdir):
    say("=" * 72)
    say("СТАДИЯ 3. Энергия процессора, AMD uProf, разностный способ")
    say("=" * 72)
    uprof = find_uprof()
    if not uprof:
        say("AMDuProfCLI.exe не найден - стадия пропущена.")
        say("Если uProf установлен в другом месте, задайте --uprof=...")
        say("")
        return []
    say("uProf: %s" % uprof)
    idle = idle_power(uprof, outdir)
    say("Простой пакета: %s Вт" % num(idle, 1))
    say("")
    say("  задача            напр  точка     Дж/кадр   за вычетом простоя")

    out = []
    for tag, name in IMAGES:
        path = os.path.join(imgdir, name)
        for alg in ALGS:
            for d in ("E", "D"):
                b = best.get((tag, alg, d))
                if not b:
                    continue
                th, pool, fps = b["threads"], b["pool"], b["fps"]
                n1 = max(MIN_FRAMES, int(fps * ENERGY_RUN_S))
                # the 2N run lasts twice as long, so a slow point is already
                # generous with samples at four frames
                pair = []
                for mult in (1, 2):
                    nn = n1 * mult
                    if d == "E":
                        args = enc_args(path, alg, ratios.get(tag), nn, th, pool)
                    else:
                        args = dec_args(refs[(tag, alg)], nn, th, pool)
                    log = "energy_%s_%s_%s_%dn" % (tag, alg, d, mult)
                    r = uprof_run(uprof, args, log, outdir)
                    record(stage="energy", image=tag, alg=alg, direction=d,
                           threads=th, pool=pool, note="%dn" % mult, **r)
                    pair.append(r)
                r1, r2 = pair
                f1 = r1.get("frames") or n1
                f2 = r2.get("frames") or (2 * n1)
                e1, e2 = r1.get("energy_j"), r2.get("energy_j")
                t1, t2 = r1.get("uprof_span_s"), r2.get("uprof_span_s")
                jf = net = None
                if None not in (e1, e2) and f2 > f1 and e2 > e1:
                    jf = (e2 - e1) / (f2 - f1)
                    if idle and None not in (t1, t2) and t2 > t1:
                        net = jf - idle * (t2 - t1) / (f2 - f1)
                say("  %-2s %-10s %-4s %2dx%-2d    %8s   %8s"
                    % (tag.upper(), ALG_RU[alg], d, th, pool,
                       num(jf, 3), num(net, 3)))
                row = dict(stage="energy_result", image=tag, alg=alg,
                           direction=d, threads=th, pool=pool,
                           frames_n=f1, frames_2n=f2,
                           j_per_frame=jf, j_per_frame_net=net,
                           idle_w=idle, fps=fps)
                record(**row)
                out.append(row)
    say("")
    return out


# ---------------------------------------------------------------------------
# stage 4: the shape of the curve
# ---------------------------------------------------------------------------

def stage_curve(imgdir, ratios):
    say("=" * 72)
    say("СТАДИЯ 4. Кривая по потокам, 2K с потерями, кодирование")
    say("=" * 72)
    path = os.path.join(imgdir, IMAGES[0][1])
    ratio = ratios.get("2k")
    out = {"threads": [], "pool": [], "combo": []}

    def sweep(title, pairs, key):
        say("")
        say(title)
        say("  потоки  пул   кадр/с   ускорение   ядер")
        base, prev = None, None
        for th, pool in pairs:
            r = run(enc_args(path, "irrev", ratio, frames_for(prev, th),
                             th, pool),
                    "curve_%s_%dx%d" % (key, th, pool))
            fps = r.get("fps")
            if fps is None:
                say("  %6d  %3d   прогон не дал числа" % (th, pool))
                continue
            prev = fps
            if base is None:
                base = fps
            say("  %6d  %3d   %6s   %8s   %4s"
                % (th, pool, num(fps, 1), num(fps / base, 2) + "x",
                   num(r.get("cores"), 1)))
            row = dict(stage="curve", part=key, threads=th, pool=pool,
                       fps=fps, cores=r.get("cores"),
                       handover_pct=r.get("handover_pct"))
            record(**row)
            out[key].append(row)

    sweep("Наши потоки (каждый кодирует целые кадры):",
          [(t, 1) for t in CURVE_THREADS], "threads")
    sweep("Собственный пул OpenJPEG (наш поток один):",
          [(1, k) for k in CURVE_POOL], "pool")
    sweep("Сочетания:", CURVE_COMBO, "combo")
    say("")
    return out



# ---------------------------------------------------------------------------
# stage 5: memory on 4K - the direct test of the article's explanation
# ---------------------------------------------------------------------------
# The article says the collapse on 4K comes from the number of frames alive in
# memory at once, not from the number of threads. Version 02 measured only two
# combinations out of eight points, which is thin evidence for a claim that
# carries a whole section.
#
# This stage keeps the total thread count at thirty-two and walks the split
# between frames in flight and the library's own pool, then adds a few points
# off that line. Peak working set is recorded next to the speed. If the
# explanation holds, few frames with many threads each beats many frames with
# one, and the memory column says why.

MEM4K_POINTS = [
    (1, 32), (2, 16), (4, 8), (8, 4), (16, 2), (32, 1),   # product is 32
    (8, 1), (8, 2), (8, 8), (16, 4), (32, 4),             # off that line
]


def stage_mem4k(imgdir, ratios):
    say("=" * 72)
    say("СТАДИЯ 5. Память на 4K: кадры в работе против собственного пула")
    say("=" * 72)
    say("Всего потоков в первых шести точках одинаково - тридцать два, "
        "меняется только")
    say("то, на сколько кадров они поделены. Если дело в кадрах, живущих "
        "в памяти,")
    say("скорость будет расти влево.")
    say("")
    path = os.path.join(imgdir, "4k_wild.ppm")
    if not os.path.isfile(path) and not CFG.dry:
        say("НЕТ КАДРА: %s" % path)
        return []
    say("  кадров  пул  всего   кадр/с   разброс   ядер   память, МБ")
    rows, prev = [], None
    for th, pool in MEM4K_POINTS:
        def mk(n, th=th, pool=pool, path=path):
            return enc_args(path, "irrev", ratios.get("4k"), n, th, pool)
        log = "mem4k_%dx%d" % (th, pool)
        fps, sp, vals, raw = measure_point(mk, log, th, prev)
        if fps is None:
            say("  %6d  %3d  %5d   прогон не дал числа" % (th, pool, th * pool))
            continue
        prev = fps
        cores = median([x.get("cores_region") for x in raw]) \
            or median([x.get("cores") for x in raw])
        mem = median([x.get("peak_mb") for x in raw])
        say("  %6d  %3d  %5d   %6s   %5s %%   %4s   %8s"
            % (th, pool, th * pool, num(fps, 1), num(sp, 1), num(cores, 1),
               num(mem, 0)))
        row = dict(stage="mem4k", image="4k", alg="irrev", direction="E",
                   total=th * pool, threads=th, pool=pool, fps=fps,
                   spread_pct=sp,
                   runs=len(vals), cores=cores, peak_mb=mem,
                   frames=raw[-1].get("frames") if raw else None)
        record(**row)
        rows.append(row)
    if rows:
        b = max(rows, key=lambda x: x["fps"])
        say("")
        say("  лучшая точка: %d %s в работе по %d %s на кадр, %s кадр/с, "
            "память %s МБ"
            % (b["threads"], plural(b["threads"], "кадр", "кадра", "кадров"),
               b["pool"], plural(b["pool"], "поток", "потока", "потоков"),
               num(b["fps"], 1), num(b.get("peak_mb"), 0)))
        line = [r for r in rows if r["threads"] * r["pool"] == 32]
        if len(line) > 1:
            lo = min(line, key=lambda x: x["fps"])
            hi = max(line, key=lambda x: x["fps"])
            say("  при одном и том же числе потоков скорость меняется "
                "от %s до %s кадр/с" % (num(lo["fps"], 1), num(hi["fps"], 1)))
            say("  память при этом: %s МБ против %s МБ"
                % (num(hi.get("peak_mb"), 0), num(lo.get("peak_mb"), 0)))
    say("")
    return rows


# ---------------------------------------------------------------------------
# stage 6: two builds of the library, plain against /arch:AVX2
# ---------------------------------------------------------------------------
# The article says the numbers come from an ordinary Release build, without
# vector instructions, and honestly lists that as unchecked. A reader will
# answer "then of course it is slow", and the honest list does not stop him.
# This stage answers with a number instead.
#
# The flag belongs to the LIBRARY, not to opj_bench, so what is compared here
# are two executables built against two OpenJPEG trees. Each one prints its
# own build tag; if both print the same tag, the stage refuses to run, because
# then it would be measuring one build twice.
#
# The two are measured alternately at every point. Measuring all of A and then
# all of B would charge the machine warming up to B - the very mistake that
# made the grid and the curve of 14.09 disagree by four to five per cent.

def pick_dir(places, what, need=None):
    """The first of the listed places that exists, or None with an explanation.

    'need' is the name of a file that has to be inside, for the cases where a
    folder existing is not the same as a folder being the right one."""
    for d in places:
        if not os.path.isdir(d):
            continue
        if need and not os.path.isfile(os.path.join(d, need)):
            continue
        return d
    say("Не нашлось: %s" % what)
    for d in places:
        mark = "нет папки" if not os.path.isdir(d) else "нет файла %s" % need
        say("   искал в %s — %s" % (d, mark))
    say("Поправьте список в начале скрипта, в разделе «where things live».")
    return None


def pick_file(places, what):
    for f in places:
        if os.path.isfile(f):
            return f
    say("Не нашлось: %s" % what)
    for f in places:
        say("   искал %s" % f)
    say("Поправьте список в начале скрипта, в разделе «where things live».")
    return None


def print_plan(want, builds):
    """What will be measured and roughly how long. Printed before the work,
    not after: an estimate that arrives at the end is not an estimate."""
    say("=" * 72)
    say("План")
    say("=" * 72)
    tasks = len(IMAGES) * len(ALGS) * 2
    n_other = max(0, len(builds) - 1)
    rows = [
        ("check", "проверки и подбор коэффициентов",
         len(IMAGES) * len(ALGS), 1),
        ("grid", "сетка по потокам: %d и %d %s на задачу"
                 % (len(grid_points("E")), len(grid_points("D")),
                    plural(len(grid_points("D")), "точка", "точки",
                           "точек")),
         (len(grid_points("E")) + len(grid_points("D")))
         * len(IMAGES) * len(ALGS), REPEATS + 1),
        ("energy", "энергия в лучших точках", tasks * 2, 1),
        ("curve", "кривая по числу потоков",
         len(CURVE_THREADS) + len(CURVE_POOL) + len(CURVE_COMBO), 1),
        ("mem4k", "память на 4K", len(MEM4K_POINTS), REPEATS + 1),
        ("build", "сборки: %d против основной" % n_other,
         tasks * (n_other + 1), REPEATS + 1),
    ]
    total = 0.0
    say("  стадия   что делает                                прогонов  минут")
    for name, what, points, per in rows:
        if name not in want:
            continue
        if name == "build" and n_other == 0:
            continue
        runs = points * per
        mins = runs * (RUN_S + 1.5) / 60.0
        if name == "energy":
            mins = points * (ENERGY_RUN_S * 1.5 + 4) / 60.0
        total += mins
        say("  %-8s %-40s %8d %6d" % (name, what, runs, int(mins + 0.5)))
    say("  %-8s %-40s %8s %6d" % ("всего", "", "", int(total + 0.5)))
    say("")
    say("Оценка грубая: она считает по самой длине прогона и не знает, что "
        "медленные")
    say("точки на 4K идут дольше. В прогоне 14.09 план обещал 66 минут, "
        "вышло 105 -")
    say("то есть примерно в полтора раза дольше. Смотреть на неё как "
        "на порядок величины.")
    say("")


def find_builds(root):
    """Read the builds folder. Every subdirectory is one build: its name is
    the build's name, and inside it lie one executable and the openjp2.dll
    that belongs to it.

    Why a folder and not a list of paths: on Windows the library is taken from
    beside the executable, so "one build" is a directory, not a file. Saying
    it that way in the layout means the mistake cannot be made - and it adds
    the next build (avx512, clang, another version of the library) without
    touching this script."""
    out = []
    if not os.path.isdir(root):
        say("Папки сборок нет: %s" % root)
        return out
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        exes = [f for f in sorted(os.listdir(d))
                if f.lower().startswith("opj_bench")
                and f.lower().endswith(".exe")]
        if not exes:
            exes = [f for f in sorted(os.listdir(d))
                    if f.lower().startswith("opj_bench") and "." not in f]
        if not exes:
            say("  в %s нет программы opj_bench - папка пропущена" % name)
            continue
        if len(exes) > 1:
            say("  в %s больше одной программы (%s) - папка пропущена"
                % (name, ", ".join(exes)))
            continue
        out.append((name, os.path.join(d, exes[0])))
    return out


def check_build_tags(builds):
    """Ask every build what it thinks it is and compare with the folder name.

    They disagree when the wrong openjp2.dll ended up beside an executable,
    and that is the one way this whole comparison can fail without leaving a
    trace: the numbers come out, the table looks fine, and both columns are
    the same library. Better to stop here."""
    ok, seen = True, {}
    for name, exe in builds:
        tag = probe_build(exe)
        say("  %-10s %-52s метка: %s" % (name, exe, tag or "не сказала"))
        if tag is None:
            ok = False
            continue
        if True:
            if tag != name:
                say("     метка не совпадает с именем папки - скорее всего "
                    "рядом чужая openjp2.dll")
                ok = False
            if tag in seen:
                say("     такая же метка уже была у %s" % seen[tag])
                ok = False
            seen[tag] = name
    return ok


def probe_build(exe):
    """Ask an executable what it is. Returns the tag, or None.

    Done for real even in show mode: it costs milliseconds, and the one thing
    the show is for is telling the truth about what was found."""
    try:
        out = subprocess.run([exe, "-version"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=60)
        text = out.stdout.decode("utf-8", "replace")
    except Exception as e:
        say("  не удалось спросить версию у %s: %s" % (exe, e))
        return None
    m = RE_BUILD.search(text)
    return m.group(1) if m else None


def same_work(imgdir, others):
    """Do the other builds produce the same bytes as the baseline? Lossless
    must come back bit for bit, and the lossy path must land on the same file
    size and the same PSNR. If it does not, the builds are not doing one job
    and their speeds are not comparable - that is a stop, not a footnote."""
    say("Проверка, что сборки делают одну работу:")
    ok = True
    base_exe, base_tag = CFG.exe, CFG.build
    for name, exe in others:
        for tag, fname in IMAGES:
            path = os.path.join(imgdir, fname)
            base = {}
            for r in ROWS:
                if r.get("stage") == "check" and r.get("image") == tag:
                    base[r.get("alg")] = r
            for alg in ALGS:
                args = ["-i", path, "-a", alg, "-c", CODE_BLOCK, "-l", LEVELS,
                        "-verify", "-info", "-opjthreads", 8]
                if alg == "irrev":
                    args += ["-targetsize", TARGETS[tag], "-tol", CALIB_TOL]
                CFG.exe, CFG.build = exe, name
                r = run(args, "buildcheck_%s_%s_%s" % (name, tag, alg))
                CFG.exe, CFG.build = base_exe, base_tag
                record(stage="buildcheck", part=name, image=tag, alg=alg, **r)
                b = base.get(alg, {})
                if CFG.dry:
                    continue
                if alg == "rev":
                    if r.get("lossless_exact"):
                        say("  %s, %s без потерь: байт в байт — сходится"
                            % (name, tag.upper()))
                    else:
                        say("  %s, %s без потерь: КАДР ИЗМЕНИЛСЯ"
                            % (name, tag.upper()))
                        ok = False
                else:
                    s1, s2 = b.get("calib_size"), r.get("calib_size")
                    p1, p2 = b.get("psnr_db"), r.get("psnr_db")
                    same_size = (s1 is not None and s1 == s2)
                    same_psnr = (p1 is not None and p2 is not None
                                 and abs(p1 - p2) <= 0.01)
                    if same_size and same_psnr:
                        say("  %s, %s с потерями: %s байт и %s дБ — сходится"
                            % (name, tag.upper(), s2, num(p2, 2)))
                    else:
                        say("  %s, %s с потерями: РАСХОЖДЕНИЕ — размер %s "
                            "против %s, PSNR %s против %s"
                            % (name, tag.upper(), s1, s2,
                               num(p1, 2), num(p2, 2)))
                        ok = False
    if not ok:
        say("")
        say("СБОРКИ ДАЮТ РАЗНЫЙ РЕЗУЛЬТАТ, скорости сравнивать нельзя.")
        say("Обычная причина — ключ, меняющий правила плавающей арифметики "
            "(/fp:fast).")
        say("Соберите вторую библиотеку только с /arch:AVX2 и повторите.")
    return ok


def stage_build(imgdir, ratios, refs, best):
    say("=" * 72)
    say("СТАДИЯ 6. Сборки библиотеки: сравнение с основной")
    say("=" * 72)
    others = [(n, e) for n, e in CFG.builds if e != CFG.exe]
    if not others:
        say("Сравнивать не с чем: в папке сборок только одна. Передайте "
            "--builds <папка>,")
        say("где в каждой подпапке своя программа со своей openjp2.dll.")
        say("")
        return []
    if not best:
        say("Стадия сборок без лучших точек не идёт: нужна стадия сетки или "
            "--best <файл>.")
        say("")
        return []

    say("Основная сборка: %s" % (CFG.build or CFG.exe))
    say("Сравниваются с ней: %s" % ", ".join(n for n, _e in others))
    say("")

    # Before comparing speeds, make sure the builds do the same work. A vector
    # flag that changed the output would make the comparison meaningless, and
    # /fp:fast is exactly the flag that would do it. This is cheap - four short
    # runs per build - and it is the difference between a measurement and a
    # number.
    if not same_work(imgdir, others):
        say("")
        return []

    say("")
    say("Точки измеряются по очереди, все сборки подряд на одной точке, "
        "и порядок сборок")
    say("на каждой точке меняется. В прогоне 14.09 первой всегда шла основная "
        "сборка,")
    say("и весь разогрев доставался ей: разброс у неё на кодировании был "
        "13-24 %,")
    say("а у следующей за ней - 1-12 %. Ниже печатается разброс по месту "
        "в очереди:")
    say("если места равны, значит чередование сработало.")
    say("")
    head = "  задача                      напр  точка   %8s" % "основная"
    for n, _e in others:
        head += " %8s %7s" % (n, "разница")
    say(head)

    rows = []
    by_pos = {}
    flip = [False]
    base_exe, base_tag = CFG.exe, CFG.build
    for (tag, alg, d), b in sorted(best.items()):
        th, pool = b["threads"], b["pool"]
        path = os.path.join(imgdir, dict(IMAGES)[tag])
        if d == "E":
            def mk(n, th=th, pool=pool, alg=alg, path=path, tag=tag):
                return enc_args(path, alg, ratios.get(tag), n, th, pool)
        else:
            ref = refs.get((tag, alg))
            if not ref:
                continue

            def mk(n, th=th, pool=pool, ref=ref):
                return dec_args(ref, n, th, pool)
        got = {}
        order = [(base_tag or "основная", base_exe)] + others
        # Порядок сборок меняется от точки к точке: иначе разогрев машины
        # каждый раз достаётся одной и той же сборке, и разница между
        # сборками мешается с разницей между «первый» и «второй».
        if flip[0]:
            order = list(reversed(order))
        flip[0] = not flip[0]
        for pos, (name, exe) in enumerate(order, start=1):
            CFG.exe, CFG.build = exe, name
            log = "build_%s_%s_%s_%s_%dx%d" % (name, tag, alg, d, th, pool)
            fps, sp, vals, raw = measure_point(mk, log, th,
                                               got.get(base_tag or "основная"))
            got[name] = fps
            record(stage="build", part=name, image=tag, alg=alg, direction=d,
                   total=th * pool, threads=th, pool=pool, fps=fps,
                   spread_pct=sp, order_pos=pos,
                   runs=len(vals), build=name,
                   cores=median([x.get("cores_region") for x in raw]),
                   peak_mb=median([x.get("peak_mb") for x in raw]),
                   frames=raw[-1].get("frames") if raw else None)
            by_pos.setdefault(pos, []).append(sp)
        CFG.exe, CFG.build = base_exe, base_tag
        a_fps = got.get(base_tag or "основная")
        if not a_fps:
            continue
        line = "  %-26s %-4s %2dx%-2d  %8s" % (
            "%s %s" % (tag.upper(), ALG_RU[alg]),
            "код" if d == "E" else "дек", th, pool, num(a_fps, 1))
        row = dict(image=tag, alg=alg, direction=d, base=a_fps)
        for name, _e in others:
            f = got.get(name)
            if f:
                diff = (f / a_fps - 1.0) * 100.0
                line += " %8s %+6s %%" % (num(f, 1), num(diff, 1))
                row[name] = f
                row[name + "_diff"] = diff
            else:
                line += " %8s %8s" % ("-", "-")
        say(line)
        rows.append(row)

    for name, _e in others:
        vals = [r[name + "_diff"] for r in rows if name + "_diff" in r]
        if vals:
            say("")
            say("  %s против основной по восьми задачам: от %s до %s %%"
                % (name, num(min(vals), 1), num(max(vals), 1)))
    if by_pos:
        say("")
        say("  разброс повторов по месту в очереди:")
        for pos in sorted(by_pos):
            vals = [v for v in by_pos[pos] if v is not None]
            if vals:
                say("    место %d: медиана %s %%, худший %s %%"
                    % (pos, num(median(vals), 1), num(max(vals), 1)))
        say("  если медианы близки, чередование сработало; если у первого "
            "места заметно хуже,")
        say("  значит разогрев всё ещё достаётся тому, кто идёт первым")
    if rows:
        say("")
        say("  это и есть ответ на вопрос «а если собрать с векторными "
            "командами»")
    say("")
    return rows


# ---------------------------------------------------------------------------
# the reference point: how much the machine drifted over the run
# ---------------------------------------------------------------------------
# On 14.09 the grid said 76.9 frames a second at thirty-two threads and the
# curve, an hour later, said 73.5. Working out that the machine had simply
# warmed up cost a day. One cheap point at each end of the run answers it in
# advance, and the number goes into the results where a table can quote it.

REF_POINT = (32, 1)


def reference_point(imgdir, ratios, when):
    path = os.path.join(imgdir, "2k_wild.ppm")
    if not os.path.isfile(path) and not CFG.dry:
        return None
    th, pool = REF_POINT

    def mk(n):
        return enc_args(path, "irrev", ratios.get("2k"), n, th, pool)
    fps, sp, vals, raw = measure_point(mk, "ref_%s" % when, th)
    record(stage="ref", part=when, image="2k", alg="irrev", direction="E",
           threads=th, pool=pool, fps=fps, spread_pct=sp, runs=len(vals),
           cores=median([x.get("cores_region") for x in raw]))
    return fps


# ---------------------------------------------------------------------------

def verdict(ratios, best, energy, curve):
    say("=" * 72)
    say("Что получилось")
    say("=" * 72)

    if best:
        say("")
        say("Лучшие точки:")
        row = "  %-13s %-14s %7s %-8s %8s %6s"
        say(row % ("задача", "направление", "всего", "точка", "кадр/с",
                   "ядер"))
        for (tag, alg, d), b in sorted(best.items()):
            say(row % (tag.upper() + " " + ALG_RU[alg],
                       "кодирование" if d == "E" else "декодирование",
                       b.get("total", b["threads"] * b["pool"]),
                       "%dx%d" % (b["threads"], b["pool"]),
                       num(b["fps"], 1), num(b.get("cores"), 1)))
        say("Столбец «всего» - это кадры в работе, умноженные на потоки "
            "внутри кадра.")

        shaky = [(k, b) for k, b in sorted(best.items())
                 if (b.get("spread_pct") or 0) > RESPREAD_LIMIT]
        if shaky:
            say("")
            say("Лучшие точки, которые не успокоились за %d повторов:"
                % (REPEATS + RESPREAD_EXTRA))
            for (tag, alg, d), b in shaky:
                say("  %-13s %-14s %s кадр/с, разброс %s %%"
                    % (tag.upper() + " " + ALG_RU[alg],
                       "кодирование" if d == "E" else "декодирование",
                       num(b["fps"], 1), num(b["spread_pct"], 1)))
            say("Точность здесь намеренно не догоняется: речь о единицах "
                "кадров в секунду")
            say("при сотнях у видеокарты, и проценты ничего в выводе "
                "не меняют. Разброс")
            say("печатается честно и переносится в статью там, где он велик.")

    if curve and curve.get("threads"):
        pts = curve["threads"]
        top = max(pts, key=lambda p: p["fps"])
        first = pts[0]["fps"]
        say("")
        say("Кривая по потокам: вершина - %s, %s кадр/с, "
            "это в %s раза быстрее одного потока."
            % (threads_word(top["threads"]), num(top["fps"], 1),
               num(top["fps"] / first, 2)))
        after = [p for p in pts if p["threads"] > top["threads"]]
        if not after:
            say("Вершина на краю сетки - потолок не назван, сетку надо вести "
                "дальше.")
        else:
            say("За вершиной кривая идёт вниз - потолок найден, это и есть "
                "предел кодека на этой машине.")

    if curve and curve.get("pool"):
        pts = curve["pool"]
        if any(p.get("pool_refused") for p in pts):
            say("Собственный пул OpenJPEG отказан: многопоточного кодирования "
                "в этой сборке нет.")
        else:
            top = max(pts, key=lambda p: p["fps"])
            say("Собственный пул: вершина на %d, ускорение %s раза."
                % (top["pool"], num(top["fps"] / pts[0]["fps"], 2)))

    if energy:
        say("")
        say("Энергия процессора на кадр, джоули:")
        row = "  %-13s %-14s %9s %9s"
        say(row % ("задача", "направление", "Дж/кадр", "без простоя"))
        for r in energy:
            say(row % (r["image"].upper() + " " + ALG_RU[r["alg"]],
                       "кодирование" if r["direction"] == "E"
                       else "декодирование",
                       num(r["j_per_frame"], 3),
                       num(r["j_per_frame_net"], 3)))
        say("")
        say("Это вся энергия процессора за время работы кадра, включая простой "
            "тех ядер, что не заняты. Так же считается энергия карты у двух "
            "других кодеков, поэтому числа сравнимы.")

    say("")
    say("Числа для статьи брать из results.csv, а не отсюда: здесь они "
        "округлены для чтения.")


# ---------------------------------------------------------------------------

def write_results(outdir):
    cols = ["bench_version", "stage", "part", "image", "alg", "direction",
            "threads", "pool", "fps", "spread_pct", "runs", "cores",
            "cores_process", "cores_region", "cpu_region_s",
            "handover_pct", "frames", "frames_n", "frames_2n",
            "j_per_frame", "j_per_frame_net", "idle_w", "energy_j",
            "power_avg_w", "power_max_w", "uprof_span_s", "uprof_samples",
            "calib_q", "calib_size", "calib_target", "calib_miss",
            "lossless_exact", "pool_refused", "size_kb", "ratio", "sdk",
            "psnr_db", "peak_mb", "build", "build_avx2_file",
            "wall_s", "cpu_s", "note", "cmd"]
    with open(os.path.join(outdir, "results.csv"), "w", encoding="utf-8",
              newline="") as f:
        w = csvmod.writer(f, delimiter=";")
        w.writerow(cols)
        for r in ROWS:
            w.writerow([r.get(c, "") for c in cols])


def main():
    global LOGDIR, JSONL
    ap = argparse.ArgumentParser(
        usage="opj-run-05.py [--do] [редкие ключи]",
        description="Без ключей — показать, что найдено и что будет "
                    "измерено. С --do — измерить.")
    ap.add_argument("--do", action="store_true",
                    help="измерять по-настоящему; без него ничего не меряется")
    # Редкие ключи. Обычно не нужны: пути скрипт находит сам.
    ap.add_argument("--only", default="check,grid,energy,curve,mem4k,build",
                    help="какие стадии; по умолчанию все")
    ap.add_argument("--baseline", default=None,
                    help="какая сборка основная; по умолчанию plain")
    ap.add_argument("--best", default=None,
                    help="best.json прежнего прогона: тогда энергия и сборки "
                         "идут без стадии сетки")
    ap.add_argument("--builds", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--exe", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--img", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--uprof", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--out", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args()

    CFG.dry = not a.do
    if a.uprof:
        UPROF_DIRS.insert(0, os.path.dirname(a.uprof))

    want = [s.strip() for s in a.only.split(",") if s.strip()]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.abspath(a.out) if a.out else here
    outdir = os.path.join(base, "opj-run_" + stamp)

    t0 = time.time()
    say(VERSION)
    say("Дата: %s" % datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
    say("Система: %s, логических ядер: %s"
        % (platform.platform(), os.cpu_count()))
    imgdir = a.img or pick_dir(IMG_PLACES, "папка с кадрами 2k_wild.ppm "
                               "и 4k_wild.ppm", "2k_wild.ppm")
    if not imgdir:
        return 1
    builds_root = a.builds or pick_dir(BUILD_ROOTS, None)
    if builds_root:
        say("Папка сборок: %s" % builds_root)
        CFG.builds = find_builds(builds_root)
        if not CFG.builds:
            say("Ни одной сборки не найдено. Ожидается по подпапке на сборку, "
                "в каждой")
            say("одна программа opj_bench*.exe и рядом её openjp2.dll.")
            return 1
        if not check_build_tags(CFG.builds):
            say("")
            say("СБОРКИ НЕ РАЗЛИЧАЮТСЯ НАДЁЖНО — дальше идти нельзя: "
                "измерения")
            say("окажутся подписаны не теми именами. Проверьте, что рядом "
                "с каждой")
            say("программой лежит её собственная openjp2.dll.")
            return 1
        names = [n for n, _e in CFG.builds]
        # The baseline is the ordinary build: everything except the build
        # stage is measured on it, and the article's numbers come from it.
        # "plain" by name if it is there, otherwise the first one - and
        # --baseline overrides both.
        baseline = a.baseline or ("plain" if "plain" in names else names[0])
        if baseline not in names:
            say("Сборки «%s» нет. Есть: %s" % (baseline, ", ".join(names)))
            return 1
        CFG.exe = dict(CFG.builds)[baseline]
        CFG.build = baseline
        say("Основная сборка: %s" % baseline)
    else:
        exe = a.exe or pick_file(EXE_PLACES, "программа opj_bench")
        if not exe:
            say("")
            say("Ни папки сборок, ни отдельной программы. Искал папки:")
            for d in BUILD_ROOTS:
                say("   %s" % d)
            return 1
        CFG.exe = exe
        CFG.build = probe_build(CFG.exe)
        CFG.builds = [(CFG.build or "основная", CFG.exe)]
        say("Программа: %s" % CFG.exe)
        if CFG.build:
            say("Сборка: %s" % CFG.build)
        say("Папки сборок нет — сравнивать не с чем, стадия build "
            "пропускается.")
    say("Кадры: %s" % imgdir)
    say("Стадии: %s" % ", ".join(want))
    say("")

    print_plan(want, CFG.builds)

    if not CFG.dry and not os.path.isfile(CFG.exe):
        say("НЕ НАЙДЕНО: %s" % CFG.exe)
        return 1

    if CFG.dry:
        say("=" * 72)
        say("Это показ: ничего не измерено и ничего не записано.")
        say("Папка прогона не заведена; при измерении она встанет сюда:")
        say("   %s" % outdir)
        say("")
        say("Мерить: python %s --do" % os.path.basename(__file__))
        say("=" * 72)
        return 0

    # Всё, что ниже, пишет на диск, и заводится только на настоящем прогоне.
    LOGDIR = os.path.join(outdir, "logs")
    os.makedirs(LOGDIR, exist_ok=True)
    # The compressed frames are working files and belong nowhere near the
    # folder the user keeps their own files in.
    refdir = tempfile.mkdtemp(prefix="opj-refs-")
    JSONL = open(os.path.join(outdir, "results.jsonl"), "a", encoding="utf-8")

    ratios, refs, best, energy, curve = {}, {}, {}, [], {}
    mem4k, builds, ref_a, ref_b = [], [], None, None

    # Best points from a previous run, so that the energy and build stages do
    # not need the grid to have run in the same process. This is the fix for
    # the sore point of 14.09: an interrupted run meant recomputing the grid.
    if a.best:
        try:
            with open(a.best, encoding="utf-8") as fh:
                raw = json.load(fh)
            best = dict((tuple(k.split("|")), v) for k, v in raw.items())
            say("Лучшие точки взяты из %s: %d %s"
                % (a.best, len(best),
                   plural(len(best), "точка", "точки", "точек")))
            say("")
        except Exception as e:
            say("Не читается %s: %s" % (a.best, e))
            return 1

    if "check" in want:
        ratios, refs, sdk = stage_check(imgdir, refdir)
        if ratios is None:
            shutil.rmtree(refdir, ignore_errors=True)
            return 1
        if sdk:
            say("Библиотека: %s" % sdk)
            say("")
        if ratios:
            ref_a = reference_point(imgdir, ratios, "start")
    if "grid" in want:
        if not refs:
            say("Стадия сетки без стадии проверок не идёт: нужны подобранные "
                "коэффициенты и файлы для декодирования.")
            return 1
        best = stage_grid(imgdir, ratios, refs)
        if best and not CFG.dry:
            with open(os.path.join(outdir, "best.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(dict(("|".join(k), v) for k, v in best.items()),
                          fh, ensure_ascii=False, indent=1)
    if "energy" in want and best:
        energy = stage_energy(imgdir, ratios, refs, best, outdir)
    elif "energy" in want:
        say("Стадия энергии без стадии сетки не идёт: нужны лучшие точки.")
        say("")
    if "curve" in want:
        if not ratios:
            say("Стадия кривой без стадии проверок не идёт: нужен подобранный "
                "коэффициент.")
        else:
            curve = stage_curve(imgdir, ratios)
    if "mem4k" in want:
        if not ratios:
            say("Стадия памяти без стадии проверок не идёт: нужен подобранный "
                "коэффициент для 4K.")
            say("")
        else:
            mem4k = stage_mem4k(imgdir, ratios)
    if "build" in want:
        builds = stage_build(imgdir, ratios, refs, best)

    if ref_a is not None:
        ref_b = reference_point(imgdir, ratios, "end")
        say("=" * 72)
        say("Дрейф машины за прогон")
        say("=" * 72)
        if ref_b:
            d = (ref_b / ref_a - 1.0) * 100.0
            say("Опорная точка 32x1 на 2K с потерями: в начале %s кадр/с, "
                "в конце %s, разница %s %%"
                % (num(ref_a, 1), num(ref_b, 1), num(d, 1)))
            if abs(d) > 3.0:
                say("Разница больше трёх процентов: числа, снятые в начале "
                    "и в конце прогона,")
                say("между собой впрямую не сравниваются. В таблице это "
                    "надо оговорить.")
        else:
            say("Вторая опорная точка не измерилась.")
        say("")

    verdict(ratios, best, energy, curve)
    say("")
    m = int((time.time() - t0) / 60.0 + 0.5)
    say("Всего заняло %d %s." % (m, plural(m, "минуту", "минуты", "минут")))

    with open(os.path.join(outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    shutil.rmtree(refdir, ignore_errors=True)
    if True:
        write_results(outdir)
        if JSONL:
            JSONL.close()
        zp = os.path.join(base, "opj-run_%s.zip" % stamp)
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _d, files in os.walk(outdir):
                for nm in files:
                    p = os.path.join(root, nm)
                    rel = os.path.relpath(p, outdir)
                    # belt and braces: nothing binary in the archive even if a
                    # future stage starts writing frames again
                    if rel.lower().endswith((".jp2", ".ppm", ".j2k")):
                        continue
                    z.write(p, rel)
        print("")
        print("Архив: %s" % zp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
