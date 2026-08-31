#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# j2k-nv-threads-and-states-02.py
# version 2026-08-31.2 of 31.08.2026
#
# How much of the nvJPEG2000 speed is the library, and how much is our way of
# driving it. Written from scratch; it replaces j2k-stock-threads-01..04, which
# should be deleted.
#
# WHAT CHANGED IN 02, AND WHY IT MATTERS
#
# Version 01 gave every launch the same 200 frames. Nearly all of a launch is
# the start of the process - CUDA setup, the licence check, the bus test - and
# the measurement itself was under a second: 200 frames at 1900 frames per
# second is a tenth of a second of measuring inside a 33 second launch. In a
# window that short the constant cost of the first frames weighs more than the
# codec, and the numbers scatter. The 344.8 of the first ladder run came from
# exactly there.
#
# A fixed larger number would not fix it either: 1000 frames is 17 seconds on
# the slowest point and half a second on the fastest. So the count is now
# computed per workload from the speed itself, the way bench-05.py does it:
# one short probe launch measures the speed, and every launch of that workload
# is then given as many frames as fill RUN_SECONDS, never fewer than
# MIN_FRAMES. The chosen counts are printed before the run and written into
# every result row.
#
# The two run lengths of ladder 1 grew with it, from 200 and 2000 to 1000 and
# 5000: that pair is a difference of two wall clock times, and the shorter of
# the two decides how much of the difference is noise.
#
# THE QUESTION
#
# nvJPEG2000 has no real batch: not one function of the library takes an array
# of images. To give it the same load on the card that our codec gets from a
# real batch, we create as many codec states and CUDA streams per thread as the
# batch size says. The trick is legal and uses nothing but the library itself -
# but the trick is ours, and NVIDIA's own programs do not do it.
#
# The old grid (8x1, 8x2, 16x2, 8x4) had no point where the threads are many
# and the frame in a thread is one. So it was never checked what the library
# does when it is simply given more CPU threads. Three ladders answer that,
# measured in one run because numbers from different runs cannot be compared:
#
#   1. NVIDIA's own programs, as they come      decoding and encoding,
#                                               batch 1, 4, 20
#   2. one codec state and one stream per thread   4, 8, 16, 32 threads
#   3. our trick, the combinations of the article  8x2, 16x2, 8x4
#
# LADDER 1 HAS TWO HALVES, AND THEY ARE NOT ALIKE
#
# Decoding. Their counter wraps the decode call only: the parsing of the
# compressed image on the CPU stays outside, the reading of the file stays
# outside, and there is no copy of the finished frame back to host memory in
# the measured loop at all. Their figure is therefore NOT comparable with ours
# directly; what is comparable is the speed taken by the wall clock from two
# runs of different length.
#
# Encoding. Here their boundary happens to be ours. Their counter, a pair of
# CUDA events around the batch loop, holds the encode call and the copy of the
# compressed stream into host memory, while the upload of the source frame is
# done before the timer starts, at file reading. That is exactly the boundary
# of our own single frame mode. The rest of the configuration matches too:
# their sample hard-codes six resolution levels and the LRCP progression,
# takes the code block size as an option (-cblk 32,32), and its quality knob
# -q_factor is the very same Q-factor scale we already set for nvJPEG2000 in
# the article. So the encoding half can be put beside our single frame column,
# and the preparation step checks the one thing that could still differ - that
# their program at our matched quality really makes a file of our size.
#
# In both halves their programs are strictly serial: one codec state, one
# stream, a synchronisation after every image. Their -b groups the reading of
# files and the timed span, and changes nothing about how the work is done.
#
# HOW IT DIFFERS FROM j2k-stock-threads-04, AND WHY
#
#   1. NOTHING LONG STARTS BY ITSELF. Run with no options the script prints how
#      it can be started and what has to be next to it, and measures nothing.
#      In version 04 a bare start went straight into the real run, guarded only
#      by a "Begin? [y/N]" question - and that guard was hollow: started
#      without a console the question raised end-of-input, which was caught and
#      ignored, so the hour-long run began anyway.
#
#   2. IT PREPARES ITS OWN REFERENCE STREAMS. Version 04 demanded eight .jp2
#      files left over from the run of 24 August and refused to start without
#      them. This one needs only the two source frames: it encodes the
#      references itself and matches the nvJPEG2000 file size to ours, under
#      the same conditions as bench-05. What it needs it makes; what it cannot
#      make it names.
#
#   3. THE NVIDIA PROGRAM GETS ONE FRAME, NOT A GROWING PILE. It reads the
#      whole input directory, and version 04 copied every reference into one
#      shared folder and never cleaned it: by the end of a run that folder held
#      2K and 4K, lossy and lossless, and a point called "2K lossless" was
#      measured on a mixture. Here every workload has its own directory with
#      exactly one file in it, checked before the program is started.
#
#   4. STEP 1 IS NOT SKIPPED IN SILENCE. Without NVIDIA's program there is no
#      answer to the question this run exists for, so --final refuses to start
#      unless the program is given with --nv-sample or its absence is stated
#      out loud with --no-nv-sample.
#
#   5. Ctrl-C STOPS IT. The program being measured is killed, the results file
#      is closed, and the script says what has been measured and where it is.
#      Version 04 had no handling at all.
#
#   6. A SIGN OF LIFE AT LEAST EVERY FIVE MINUTES, on a timer, with the wall
#      clock time. Version 04 declared the rule in a constant named HEARTBEAT
#      and never used it: a line appeared only after a run had finished, and a
#      run was given half an hour before it was called stuck.
#
#   7. THE VERSION IS IN THREE PLACES AND THEY AGREE - the file name, the line
#      above, and the constant printed into the results and the report. In
#      version 04 the file was called -04 while the constant inside said
#      "j2k-stock-threads-02", and that string went into the report: the run
#      would have claimed to be made by a version that did not make it.
#
#   8. WHICH BUILD MEASURED is read from the executables themselves, with
#      -version, instead of being guessed from a pair of runs whose numbers
#      were compared. nvj2k_bench-02.cpp answers that; an older build does not
#      know the option, which is answer enough.
#
# WHAT THIS RUN DOES NOT MEASURE, SAID PLAINLY
#
#   Energy, PSNR, file sizes beyond the preparation, the stage breakdown, PCRD,
#   chroma subsampling. None of them bear on "how many threads and how many
#   states", and every one of them makes the run longer.
#
# Standard library only. Python 3.6+.

"""
nvJPEG2000: what the library gives, and what our way of driving it adds.

    python j2k-nv-threads-and-states-02.py              prints this, measures nothing
    python j2k-nv-threads-and-states-02.py --selftest   checks only, about a minute
    python j2k-nv-threads-and-states-02.py --prepare    reference streams only
    python j2k-nv-threads-and-states-02.py --trial      short pass through every branch
    python j2k-nv-threads-and-states-02.py --frames-scan ten points at four run lengths
    python j2k-nv-threads-and-states-02.py --final      the run

Ctrl-C stops a run at any point: every measurement already made is on disk.
"""

import os
import re
import sys
import json
import time
import shutil
import argparse
import datetime
import platform
import threading
import subprocess
import statistics

SCRIPT_NAME = "j2k-nv-threads-and-states-02.py"   # must match the file name
VERSION = "2026-08-31.2"                          # goes into every result file

# ---------------------------------------------------------------------------
# conditions of the measurement: these must stay equal to bench-05, otherwise
# the numbers of this run cannot be put beside the numbers of the article
# ---------------------------------------------------------------------------

CODE_BLOCK = "32"
LEVELS = "6"
FV_QUALITY = "85"                    # quality knob of our encoder
CALIB_TOL = "0.003"                  # allowed miss when matching the file size
IMAGES = [("2k", "2k_wild.ppm"), ("4k", "4k_wild.ppm")]
ALGS = ["irrev", "rev"]              # lossy 9/7 and lossless 5/3
ALG_NAME = {"irrev": "lossy", "rev": "lossless"}

# Ladder 2: one codec state per thread. One and two threads are left out - the
# single frame mode is measured separately in the article, and the question
# here is about loading the card.
THREADS = [4, 8, 16, 32]
# Ladder 3: the combinations of the article. 8x1 is not repeated, it is in the
# ladder above.
CONTROL = [(8, 2), (16, 2), (8, 4)]
# NVIDIA's program: 1 and 20 are the batches of the chart in their own blog.
NV_SAMPLE_BATCH = [1, 4, 20]
# Two lengths of run. Their counter covers only the decode call, so their own
# figure is not comparable with ours; the difference of two runs by the wall
# clock gives the speed of the whole program without the cost of starting it.
NV_SAMPLE_TOTALS = [1000, 5000]

# How long one launch spends measuring. The number of frames is not fixed: it
# is computed per workload from the measured speed, so a fast point and a slow
# point both get a window of the same length instead of the same frame count.
# MIN_FRAMES is the floor asked for by Fyodor on 31.08 - no point is measured
# on fewer frames than this, even when that makes the window longer than
# RUN_SECONDS.
RUN_SECONDS = 6.0
MIN_FRAMES = 1000
MAX_FRAMES = 40000
PROBE_FRAMES = 200                   # the short launch that measures the speed
PROBE = "probe-stock.json"           # the counts, so a repeated run keeps them

# --frames-scan: how long a launch has to be before the number stops moving.
# Ten points, each measured at four lengths. The question is not academic -
# the first ladder run gave nvJPEG2000 encoding 344.8 at 32x1 on 200 frames,
# and under the conditions of the article the same point is 275-292.
FRAME_SCAN = [1000, 2000, 5000, 10000]
SCAN_POINTS = [
    ("enc", "2k", "irrev", 32, 1),      # where the 344.8 came from
    ("enc", "2k", "irrev", 16, 2),      # our trick, the same workload
    ("enc", "2k", "irrev", 8, 1),       # the base of the ladder
    ("enc", "2k", "rev", 32, 1),        # lossless: five times the data
    ("enc", "4k", "irrev", 32, 1),      # large frame, many threads
    ("dec", "2k", "irrev", 32, 1),      # the decoding point that gave 543/340
    ("dec", "2k", "irrev", 8, 4),       # our trick, decoding
    ("dec", "2k", "irrev", 8, 1),       # the base of the ladder
    ("dec", "4k", "irrev", 8, 4),       # large frame, our trick
    ("dec", "4k", "irrev", 32, 1),      # large frame, many threads
]
SCAN_RESULTS = "frames-scan.jsonl"
SCAN_LOGDIR = "logs-scan"

CODECS = {
    "fv": {"enc": "J2kEncoderSample", "dec": "J2kDecoderSample",
           "name": "Fastvideo"},
    "nv": {"enc": "nvj2kEncoderSample", "dec": "nvj2kDecoderSample",
           "name": "nvJPEG2000"},
}

# NVIDIA's own programs, ladder 1. They are looked for in the working folder by
# these names, so that nothing has to be passed on the command line: the run is
# asked for by one word and the script finds what it needs. The options are
# left as an override for a program kept somewhere else.
#
# Two spellings each. The name comes from add_executable in their CMakeLists;
# the second spelling is the one their own README uses, in case the file was
# renamed by hand to match it.
NV_SAMPLE_NAMES = {
    "dec": ["nvjpeg2000_decode_sample", "nvjpeg2k_decode_sample"],
    "enc": ["nvjpeg2k_encode", "nvjpeg2k_encode_sample"],
}


def find_nv_sample(folder, role, given=""):
    """NVIDIA's program: what was passed, or what lies in the folder."""
    if given:
        return given if os.path.isfile(given) else ""
    for name in NV_SAMPLE_NAMES[role]:
        p = exe_path(folder, name)
        if p:
            return p
    return ""

# Measured on this machine on 25.08.2026: about 33 seconds per launch on
# average, and nearly all of it is the start of the process - CUDA setup, the
# licence check, the bus test. The measurement itself takes under a second.
# So the length of a run is the number of launches, not the number of frames.
SEC_PER_RUN = 33.0
REFINE_TOP = 2                       # how many best points of a group to repeat
REFINE_RUNS = 3                      # up to how many launches those get
HEARTBEAT_S = 300.0                  # a sign of life at least this often
RUN_TIMEOUT = 900                    # one launch longer than this is wrong

RESULTS = "results-stock.jsonl"
SUMMARY = "summary-stock.txt"
LOGDIR = "logs-stock"
PREP = "prep-stock.json"
NVSAMPLE_DIR = "nvsample-in"
NVSAMPLE_OUT = "nvsample-out"
TRIAL_SUFFIX = "-trial"

# ---------------------------------------------------------------------------
# reading what the programs print
# ---------------------------------------------------------------------------

RE_SUMMARY = re.compile(
    r"for\s+(\d+)\s+images"
    r"(?:\s+per\s+(\d+)\s+threads?)?"
    r"\s*=\s*([\d.]+)\s*ms;"
    r"(?:\s*([\d.]+)\s*MB/s;)?"
    r"\s*([\d.]+)\s*FPS;")

RE_SIZE = re.compile(r"size\s*=\s*(\d+)\s*KB\s*\(([\d.]+):1\)")
RE_CALIB = re.compile(
    r"Calibration:\s*q\s*=\s*([\d.]+);\s*size\s*=\s*(\d+)\s*bytes;"
    r"\s*target\s*=\s*(\d+)\s*bytes;\s*miss\s*=\s*([-+]?[\d.]+)")
RE_SDK = re.compile(r"SDK version:\s*(\S+)")
RE_GPU = re.compile(r"Processing unit:\s*(.+?)\s*\(device id")
RE_HARNESS = re.compile(r"nvj2k_bench version\s+(\S+?),")

# NVIDIA's program prints in its own way, and we did not parse it before four
# spellings are tried; if none fits, the point is marked unparsed, the log is
# kept and the report says which one. Silent skipping is not allowed.
RE_NV_SAMPLE = [
    # Their encoder prints "Avg encode speed  (in images per sec): 39.2", with
    # a bracket between the words and the number; their decoder prints "Avg
    # images per sec: 33.5". One pattern that steps over whatever stands in
    # between is safer than two that each know one wording.
    re.compile(r"images\s*per\s*sec[^0-9]{0,8}([\d.]+)", re.I),
    re.compile(r"(?:images|imgs)\s*(?:per|/)\s*sec(?:ond)?s?\s*[:=]?\s*([\d.]+)",
               re.I),
    re.compile(r"([\d.]+)\s*(?:images|imgs)\s*(?:per|/)\s*sec(?:ond)?s?", re.I),
    re.compile(r"throughput\s*[:=]\s*([\d.]+)", re.I),
    re.compile(r"([\d.]+)\s*fps", re.I),
]

WINDOW_TEXT = {
    "all": "host memory to host memory, transfers counted",
    "no_d2h": "the decoded frame is not copied back to host memory",
    "no_h2d": "the source frame is on the card before the timer starts",
    "default": "the program did not say",
    "nvidia_decode_call": "NVIDIA's sample: the decode call only, without "
                          "Tier-2 and without any transfer",
    "nvidia_encode_events": "NVIDIA's sample: the encode call and the copy of "
                            "the compressed stream to host, the upload "
                            "outside - our single frame boundary",
}


def boundary_of(text):
    """What the program itself said went into the measured time.

    Both spellings are matched. The single frame path prints "excluding
    device-to-host transfer", the threads-and-batch path prints "excluding THE
    device-to-host transfer"; missing the second because of one word used to
    record such rows as "the program did not say".
    """
    if "excluding host-to-device" in text or "excluding the host-to-device" in text:
        return "no_h2d"
    if "excluding device-to-host" in text or "excluding the device-to-host" in text:
        return "no_d2h"
    if "including all transfers" in text:
        return "all"
    return "default"


def parse_ours(text):
    """The summary line of our two harnesses and of the Fastvideo samples."""
    best = None
    for line in text.splitlines():
        m = RE_SUMMARY.search(line)
        if m:
            best = (line, m)
    if not best:
        return None
    line, m = best
    return {"fps": float(m.group(5)), "images": int(m.group(1)),
            "ms_total": float(m.group(3)),
            "threads_printed": int(m.group(2)) if m.group(2) else None,
            "boundary": boundary_of(line)}


def parse_nv_sample(text, window="nvidia_decode_call"):
    """The speed line of NVIDIA's own samples.

    window says which of their two programs printed it, because the two
    measure between different points and the difference has to travel with
    the number rather than be remembered later.
    """
    for r in RE_NV_SAMPLE:
        m = r.search(text)
        if m:
            return {"fps": float(m.group(1)), "images": None,
                    "threads_printed": None, "boundary": window}
    return None


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def now():
    return datetime.datetime.now().strftime("%H:%M:%S")


def human(seconds):
    m, s = divmod(int(seconds + 0.5), 60)
    h, m = divmod(m, 60)
    if h:
        return "%d h %02d min" % (h, m)
    if m:
        return "%d min %02d s" % (m, s)
    return "%d s" % s


def median(values):
    """Only missing values are dropped, not zeros.

    A wall time of zero is a measurement - a short run on a fast workload
    rounds to nothing - and throwing it away as "empty" silently emptied whole
    rows of the report. Callers that want no zeros filter them themselves.
    """
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def spread(values):
    vals = [v for v in values if v]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    return "spread %.1f %%" % (100.0 * (hi - lo) / lo)


def exe_path(folder, name):
    """The program with or without the extension, whichever is on disk."""
    for cand in (name, name + ".exe"):
        p = os.path.join(folder, cand)
        if os.path.isfile(p):
            return p
    return None


def ref_name(codec, tag, alg):
    return "%s_ref_%s_%s.jp2" % (codec, tag, alg)


def ppm_size(path):
    """Geometry from the PPM header. Only used by the checks before a run."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(200)
    except IOError:
        return None
    if head[:1] != b"P":
        return None
    body = re.sub(rb"#[^\n]*\n", b" ", head[2:])
    parts = re.findall(rb"\d+", body[:120])
    if len(parts) >= 2:
        return int(parts[0]), int(parts[1])
    return None


# ---------------------------------------------------------------------------
# a sign of life
# ---------------------------------------------------------------------------

class Heartbeat(object):
    """Prints the wall clock time and what is running, on a timer.

    A long run with no output is indistinguishable from a stuck one. The rule
    comes from the pcrd-cost-01 run that sat silent for tens of minutes while
    nobody could tell whether it was working.
    """

    def __init__(self, period=HEARTBEAT_S):
        self.period = period
        self.what = "starting"
        self.since = time.time()
        self._stop = threading.Event()
        self._thread = None

    def set(self, what):
        self.what = what
        self.since = time.time()

    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(self.period):
            print("   %s  still working: %s, %s so far"
                  % (now(), self.what, human(time.time() - self.since)))
            sys.stdout.flush()


HEART = Heartbeat()


# ---------------------------------------------------------------------------
# running the programs
# ---------------------------------------------------------------------------

class Runner(object):
    def __init__(self, folder, logdir, results_path, timeout=RUN_TIMEOUT):
        self.folder = folder
        self.logdir = logdir
        self.timeout = timeout
        self.count = 0
        self.results_path = results_path
        if not os.path.isdir(logdir):
            os.makedirs(logdir)
        # Every measurement is written the moment it is made, and flushed. An
        # interrupted run keeps all of it; the report is assembled from this
        # file and can be assembled again at any time.
        self.out = open(results_path, "a", encoding="utf-8")
        self.rows = []

    def close(self):
        if self.out:
            self.out.close()
            self.out = None

    def run(self, prog, args, log_name):
        HEART.set(log_name)
        cmd = [prog] + [str(a) for a in args]
        t0 = time.time()
        p = None
        try:
            p = subprocess.Popen(cmd, cwd=self.folder, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            out, _ = p.communicate(timeout=self.timeout)
            code = p.returncode
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
            code = -9
        except OSError as e:
            out, code = ("did not start: %s" % e).encode("utf-8"), -1
        except KeyboardInterrupt:
            # Take the child down with us instead of leaving it holding the
            # card, then let main() finish tidily.
            if p is not None:
                try:
                    p.kill()
                    p.communicate()
                except Exception:
                    pass
            raise
        self.count += 1
        return {"cmd": " ".join(cmd), "code": code,
                "wall_s": round(time.time() - t0, 1),
                "text": out.decode("utf-8", "replace"), "log": log_name}

    def save_log(self, res, header):
        path = os.path.join(self.logdir, res["log"] + ".log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# %s\n# %s\n# exit code %s, %s s\n\n"
                     % (header, res["cmd"], res["code"], res["wall_s"]))
            fh.write(res["text"])

    def record(self, row):
        row = dict(row)
        row.setdefault("script_version", VERSION)
        row["at"] = datetime.datetime.now().isoformat(timespec="seconds")
        self.rows.append(row)
        self.out.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        self.out.flush()
        os.fsync(self.out.fileno())


# ---------------------------------------------------------------------------
# which build is doing the measuring
# ---------------------------------------------------------------------------

def harness_versions(folder):
    """What the two nvJPEG2000 executables answer to -version.

    Costs nothing and measures nothing: the program prints one line and stops
    without touching the card. An older build does not know the option and
    prints its usage instead, which is answer enough. This replaces the pair of
    runs that version 04 compared by their numbers - a version that says what
    it is does not depend on whether a difference happens to be visible.
    """
    out = {}
    for role in ("enc", "dec"):
        name = CODECS["nv"][role]
        path = exe_path(folder, name)
        if not path:
            out[name] = None
            continue
        try:
            p = subprocess.run([path, "-version"], cwd=folder,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=60)
            text = p.stdout.decode("utf-8", "replace")
            m = RE_HARNESS.search(text)
            if m:
                out[name] = m.group(1)
            elif text.strip():
                # It ran and said something else: that is an older build,
                # which answers an unknown option with its usage.
                out[name] = "before 02"
            else:
                # It printed nothing at all. That is not a version, that is a
                # program that did not start - a missing DLL, most often
                # nvjpeg2k or cudart. Saying "before 02" here would send the
                # rebuild down the wrong path.
                out[name] = "did not start"
        except Exception as e:
            out[name] = "did not start (%s)" % e.__class__.__name__
    return out


# ---------------------------------------------------------------------------
# preparation: the reference streams this run decodes
# ---------------------------------------------------------------------------

def prepare(runner, folder, force=False, nv_encode_sample=""):
    """Encodes the reference .jp2 streams from the two source frames.

    Only the two frames have to be in the folder. Everything else is made here,
    under the conditions of the article: our encoder at quality 85, and the
    nvJPEG2000 encoder at whatever quality gives a file of the same size. The
    lossless streams are simply each codec's own output - there is nothing to
    match there, and their sizes differ because the codecs differ.

    Ten launches, about five and a half minutes. The result is written to
    prep-stock.json and is not repeated on the next run unless --prepare
    is asked for again.
    """
    path = os.path.join(folder, PREP)
    if os.path.isfile(path) and not force:
        with open(path, encoding="utf-8") as fh:
            prep = json.load(fh)
        missing = [ref_name(c, tag, alg) for c in ("fv", "nv")
                   for tag, _ in IMAGES for alg in ALGS
                   if not os.path.isfile(os.path.join(folder,
                                                      ref_name(c, tag, alg)))]
        if not missing:
            print("\nPREPARATION: already done, %s is there" % PREP)
            print("   nvJPEG2000 quality matched to our file size: "
                  + ", ".join("%s %s" % (k, v)
                              for k, v in sorted(prep.get("nv_q", {}).items())))
            return prep
        print("\nPREPARATION: %s is there but %d reference streams are not: %s"
              % (PREP, len(missing), ", ".join(missing)))

    print("\nPREPARATION: making the reference streams from the two frames")
    print("About ten launches, %s." % human(10 * SEC_PER_RUN))
    prep = {"script_version": VERSION,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
            "conditions": {"code_block": CODE_BLOCK, "levels": LEVELS,
                           "fv_quality": FV_QUALITY, "calib_tol": CALIB_TOL},
            "nv_q": {}, "sizes": {}}

    fv_enc = exe_path(folder, CODECS["fv"]["enc"])
    nv_enc = exe_path(folder, CODECS["nv"]["enc"])

    # 1. our own references, quality 85 for the lossy ones
    for tag, img in IMAGES:
        for alg in ALGS:
            ref = ref_name("fv", tag, alg)
            a = ["-i", img, "-o", ref, "-a", alg,
                 "-c", CODE_BLOCK, "-l", LEVELS, "-info"]
            if alg == "irrev":
                a += ["-q", FV_QUALITY]
            res = runner.run(fv_enc, a, "prep_fv_%s_%s" % (tag, alg))
            runner.save_log(res, "preparation: our reference, %s %s"
                            % (tag, ALG_NAME[alg]))
            full = os.path.join(folder, ref)
            if not os.path.isfile(full):
                print("   %-24s NOT MADE - see the log" % ref)
                return None
            size = os.path.getsize(full)
            prep["sizes"][ref] = size
            print("   %-24s %9d bytes" % (ref, size))

    # 2. the quality that gives nvJPEG2000 a file of our size
    for tag, img in IMAGES:
        target = prep["sizes"].get(ref_name("fv", tag, "irrev"))
        res = runner.run(nv_enc, ["-i", img, "-targetsize", target,
                                  "-c", CODE_BLOCK, "-l", LEVELS,
                                  "-tol", CALIB_TOL],
                         "prep_nv_calib_%s" % tag)
        runner.save_log(res, "preparation: matching the file size, %s" % tag)
        m = RE_CALIB.search(res["text"])
        if not m:
            print("   %-3s matching the file size FAILED - see the log" % tag)
            print("       Without it the lossy encoding points of nvJPEG2000")
            print("       cannot be measured, and nothing else can be trusted")
            print("       either: the two codecs would be compared at")
            print("       different file sizes.")
            return None
        prep["nv_q"][tag] = float(m.group(1))
        print("   %-3s target %d bytes -> quality %.2f gives %s bytes, "
              "miss %.2f %%"
              % (tag, target, float(m.group(1)), m.group(2), float(m.group(4))))

    # 3. the nvJPEG2000 references at that quality
    for tag, img in IMAGES:
        for alg in ALGS:
            ref = ref_name("nv", tag, alg)
            a = ["-i", img, "-o", ref, "-a", alg,
                 "-c", CODE_BLOCK, "-l", LEVELS]
            if alg == "irrev":
                a += ["-q", prep["nv_q"][tag]]
            res = runner.run(nv_enc, a, "prep_nv_%s_%s" % (tag, alg))
            runner.save_log(res, "preparation: nvJPEG2000 reference, %s %s"
                            % (tag, ALG_NAME[alg]))
            full = os.path.join(folder, ref)
            if not os.path.isfile(full):
                print("   %-24s NOT MADE - see the log" % ref)
                return None
            size = os.path.getsize(full)
            prep["sizes"][ref] = size
            own = prep["sizes"][ref_name("fv", tag, alg)]
            note = ""
            if alg == "irrev":
                note = "  (ours %d bytes, %+.2f %%)" % (
                    own, 100.0 * (size - own) / own)
            print("   %-24s %9d bytes%s" % (ref, size, note))

    # 4. does NVIDIA's own encoder, at the quality we matched, really make a
    #    file of our size? Their sample and our harness set the library the
    #    same way - six resolution levels, LRCP, code block 32, the Q-factor
    #    scale - so it should. "Should" is not a measurement, and this is two
    #    launches.
    if nv_encode_sample:
        prep["nv_sample_sizes"] = {}
        print("   check: the file NVIDIA's own encoder makes, against ours")
        for tag, img in IMAGES:
            for alg in ALGS:
                d = nvsample_dir_enc(folder, tag, make=True)
                outd = os.path.join(folder, NVSAMPLE_OUT, "%s_%s" % (tag, alg))
                if os.path.isdir(outd):
                    for f in os.listdir(outd):
                        try:
                            os.remove(os.path.join(outd, f))
                        except OSError:
                            pass
                else:
                    os.makedirs(outd)
                pt = {"tag": tag, "alg": alg, "batch": 1, "total": 1}
                a = cmd_args_nv_sample_enc(pt, d, prep["nv_q"].get(tag),
                                           warmup=0, outdir=outd)
                if a is None:
                    continue
                res = runner.run(nv_encode_sample, a,
                                 "prep_nvsample_enc_%s_%s" % (tag, alg))
                runner.save_log(res, "preparation: size check of NVIDIA's "
                                     "encoder, %s %s" % (tag, ALG_NAME[alg]))
                made = [f for f in sorted(os.listdir(outd))
                        if f.lower().endswith(".jp2")]
                ours = prep["sizes"].get(ref_name("nv", tag, alg))
                if not made:
                    print("     %-3s %-9s their encoder wrote no file - "
                          "see the log" % (tag, ALG_NAME[alg]))
                    prep["nv_sample_sizes"]["%s_%s" % (tag, alg)] = None
                    continue
                size = os.path.getsize(os.path.join(outd, made[0]))
                prep["nv_sample_sizes"]["%s_%s" % (tag, alg)] = size
                print("     %-3s %-9s %9d bytes, ours %9d, difference "
                      "%+.2f %%"
                      % (tag, ALG_NAME[alg], size, ours or 0,
                         (100.0 * (size - ours) / ours) if ours else 0.0))

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(prep, fh, ensure_ascii=False, indent=2)
    print("   written: %s" % PREP)
    return prep


def nvsample_dir_enc(folder, tag, make=False):
    """The input of NVIDIA's encoder: one source frame, in a directory of its own.

    Their encoder reads a directory the same way their decoder does, so it gets
    the same treatment: one workload, one directory, one file in it.
    """
    d = os.path.join(folder, NVSAMPLE_DIR, "enc_%s" % tag)
    if make:
        if not os.path.isdir(d):
            os.makedirs(d)
        img = dict(IMAGES)[tag]
        src = os.path.join(folder, img)
        dst = os.path.join(d, img)
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.copyfile(src, dst)
    return d


def nvsample_dir(folder, tag, alg, make=False):
    """One directory per workload, with exactly one file in it.

    NVIDIA's program reads the whole input directory and loops over it when
    fewer images are there than were asked for. Version 04 copied every
    reference into one shared folder and never cleaned it, so by the end of a
    run the folder held all four and a point called "2K lossless" was measured
    on a mixture of 2K and 4K, lossy and lossless. The order of the points
    decided the numbers, which also made a repeated run give a different
    answer.
    """
    d = os.path.join(folder, NVSAMPLE_DIR, "%s_%s" % (tag, alg))
    if make:
        if not os.path.isdir(d):
            os.makedirs(d)
        src = os.path.join(folder, ref_name("nv", tag, alg))
        dst = os.path.join(d, ref_name("nv", tag, alg))
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.copyfile(src, dst)
    return d


def nvsample_ready(d, ext=".jp2"):
    """True only when the directory holds exactly the one file we put there."""
    if not os.path.isdir(d):
        return False, "the directory is not there"
    files = [f for f in sorted(os.listdir(d)) if f.lower().endswith(ext)]
    if len(files) == 1:
        return True, files[0]
    if not files:
        return False, "no %s in it" % ext
    return False, ("%d files in it: %s - the program reads all of them and "
                   "would measure a mixture" % (len(files), ", ".join(files)))


# ---------------------------------------------------------------------------
# the list of points
# ---------------------------------------------------------------------------

def points(with_fv, nv_sample, trial=False, nv_encode_sample=""):
    """Ordered so that the most needed thing is measured first: a run stopped
    half way still answers the main question."""
    out = []
    if nv_encode_sample:
        for tag, _ in IMAGES:
            for alg in ALGS:
                for b in (NV_SAMPLE_BATCH[:1] if trial else NV_SAMPLE_BATCH):
                    for total in (NV_SAMPLE_TOTALS[:1] if trial
                                  else NV_SAMPLE_TOTALS):
                        out.append({"step": 1, "codec": "nv",
                                    "prog": "nvsample_enc", "dir": "enc",
                                    "tag": tag, "alg": alg,
                                    "threads": 1, "batch": b, "total": total})
                if trial:
                    break
            if trial:
                break
    if nv_sample:
        for tag, _ in IMAGES:
            for alg in ALGS:
                for b in (NV_SAMPLE_BATCH[:1] if trial else NV_SAMPLE_BATCH):
                    for total in (NV_SAMPLE_TOTALS[:1] if trial
                                  else NV_SAMPLE_TOTALS):
                        out.append({"step": 1, "codec": "nv",
                                    "prog": "nvsample", "dir": "dec",
                                    "tag": tag, "alg": alg,
                                    "threads": 1, "batch": b, "total": total})
                if trial:
                    break
            if trial:
                break
    codecs = ["nv"] + (["fv"] if with_fv else [])
    grids = ((2, [(t, 1) for t in THREADS]), (3, CONTROL))
    if trial:
        # One point per branch of the code rather than the whole grid. Both
        # compression modes are needed: the lossless one takes another path,
        # where no quality knob is passed.
        grids = ((2, [(8, 1)]), (3, [(8, 2)]))
    for step, grid in grids:
        for codec in codecs:
            for d in ("enc", "dec"):
                for tag, _ in IMAGES:
                    for alg in ALGS:
                        for t, b in grid:
                            out.append({"step": step, "codec": codec,
                                        "prog": codec, "dir": d, "tag": tag,
                                        "alg": alg, "threads": t, "batch": b})
                    if trial:
                        break
    return out


def key(pt):
    tail = "|t%d" % pt["total"] if pt.get("total") else ""
    return "%s|%s|%s|%s|%d|%dx%d%s" % (pt["prog"], pt["dir"], pt["tag"],
                                       pt["alg"], pt["step"], pt["threads"],
                                       pt["batch"], tail)


def group_of(pt):
    return (pt["prog"], pt["dir"], pt["tag"], pt["alg"], pt["step"])


def workload_of(pt):
    """What decides how fast a launch goes: codec, direction, frame, mode.

    The grid point inside one workload changes the speed by a factor of three
    at most, so one count of frames per workload is enough and one probe
    launch pays for the whole group.
    """
    return (pt["codec"], pt["dir"], pt["tag"], pt["alg"])


def frames_for_speed(fps):
    """How many frames fill the measuring window at this speed."""
    if not fps or fps <= 0:
        return MIN_FRAMES
    n = int(round(RUN_SECONDS * fps))
    n = max(n, MIN_FRAMES)
    n = min(n, MAX_FRAMES)
    # A round number reads better in the report and in the logs.
    step = 100 if n < 5000 else 500
    return int(round(n / float(step))) * step


def frames_scan(folder, codecs, nv_q, harness, res_path, logdir):
    """Ten points, each measured at four run lengths.

    The point of the whole thing: a short launch measures the start of the
    process more than it measures the codec, and the number drifts with the
    length. Here the drift is measured instead of assumed. The last column is
    how far the shortest run is from the longest one; where that is a percent
    or two, the shortest length is enough.
    """
    runner = Runner(folder, logdir, res_path)
    rows = []
    total = len(codecs) * len(SCAN_POINTS) * len(FRAME_SCAN)
    print("")
    print("FRAME COUNT SCAN: %d points, %d lengths each - %d launches, %s."
          % (len(codecs) * len(SCAN_POINTS), len(FRAME_SCAN), total,
             human(total * SEC_PER_RUN)))
    print("Nothing here goes into the ladder results: this run answers how")
    print("long a launch has to be, not how fast a codec is.")
    print("")
    done = 0
    try:
        for codec in codecs:
            for (d, tag, alg, th, ba) in SCAN_POINTS:
                pt = {"step": 2, "codec": codec, "prog": codec, "dir": d,
                      "tag": tag, "alg": alg, "threads": th, "batch": ba}
                prog = exe_path(folder, CODECS[codec][d])
                got = {}
                for n in FRAME_SCAN:
                    done += 1
                    a = cmd_args(pt, n, nv_q)
                    if prog is None or a is None:
                        continue
                    name = "scan-%s-%s-%s-%s-%dx%d-n%d" % (codec, d, tag, alg,
                                                           th, ba, n)
                    res = runner.run(prog, a, name)
                    parsed = parse_ours(res["text"])
                    fps = parsed["fps"] if parsed else None
                    runner.save_log(res, "frame scan %s %s %s %s %dx%d, %d "
                                    "frames -> %s"
                                    % (codec, d, tag, alg, th, ba, n,
                                       fps if fps else "NOT PARSED"))
                    row = dict(pt)
                    row.update({"frames": n, "fps": fps, "log": name,
                                "wall_s": res["wall_s"], "code": res["code"]})
                    if codec == "nv":
                        row["nv_harness"] = harness.get(CODECS["nv"][d])
                    runner.record(row)
                    got[n] = fps
                    print("%s  %-2s %-3s %-5s %s %2dx%-2d %6d frames  %-12s "
                          "[%d/%d]"
                          % (now(), codec, tag, alg, d, th, ba, n,
                             ("%.1f fps" % fps) if fps else "NOT PARSED",
                             done, total))
                rows.append((codec, d, tag, alg, th, ba, got))
    except KeyboardInterrupt:
        runner.close()
        print("\nStopped by Ctrl-C. What was measured is in %s" % res_path)
        return rows
    runner.close()
    return rows


def frames_scan_table(rows):
    """The table the scan exists for."""
    out = []
    out.append("")
    out.append("=" * 78)
    out.append("HOW THE NUMBER DEPENDS ON THE LENGTH OF A LAUNCH")
    out.append("")
    head = "  point                        "
    for n in FRAME_SCAN:
        head += "%8d" % n
    head += "     drift"
    out.append(head)
    out.append("  " + "-" * (len(head) - 2))
    for codec, d, tag, alg, th, ba, got in rows:
        line = "  %-2s %-3s %-8s %s %2dx%-2d " % (
            codec, tag, ALG_NAME[alg], d, th, ba)
        for n in FRAME_SCAN:
            v = got.get(n)
            line += "%8s" % (("%.1f" % v) if v else "-")
        first, last = got.get(FRAME_SCAN[0]), got.get(FRAME_SCAN[-1])
        if first and last:
            line += "  %+7.1f %%" % (100.0 * (first - last) / last)
        else:
            line += "        -"
        out.append(line)
    out.append("")
    out.append("  The last column: the shortest run against the longest one.")
    out.append("  Within a percent or two the shortest length is enough and")
    out.append("  the ladder can use it. A large positive drift means the")
    out.append("  short run flatters the codec - that is where the 344.8 of")
    out.append("  the first ladder run came from.")
    out.append("")
    return out


def probe(runner, folder, todo, nv_q, harness, path):
    """One short launch per workload, to learn its speed.

    The probe is not a measurement and never goes into results-stock.jsonl:
    it is made on PROBE_FRAMES frames, a different length from everything
    else, and mixing it in would put two different windows under one point.
    Its log is kept, its answer is kept in probe-stock.json, and a repeated
    run reads that file instead of probing again.
    """
    plan = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                saved = json.load(fh)
            for k, v in saved.get("frames", {}).items():
                plan[tuple(k.split("|"))] = int(v)
        except Exception:
            plan = {}

    want = []
    for pt in todo:
        if pt["step"] == 1:          # NVIDIA's programs carry their own lengths
            continue
        w = workload_of(pt)
        if w not in plan and w not in [x[0] for x in want]:
            want.append((w, pt))
    if not want:
        return plan

    print("")
    print("SPEED PROBE: one short launch per workload, %d frames each."
          % PROBE_FRAMES)
    print("It sets how many frames every launch of that workload gets:")
    print("enough to measure for %.0f seconds, and never fewer than %d."
          % (RUN_SECONDS, MIN_FRAMES))
    print("%d launches, %s. Probes are not measurements and are not"
          % (len(want), human(len(want) * SEC_PER_RUN)))
    print("written to the results.")
    print("")
    for w, pt in want:
        probe_pt = dict(pt)
        probe_pt["threads"], probe_pt["batch"] = 8, 1
        prog = exe_path(folder, CODECS[probe_pt["codec"]][probe_pt["dir"]])
        a = cmd_args(probe_pt, PROBE_FRAMES, nv_q)
        if prog is None or a is None:
            plan[w] = MIN_FRAMES
            print("  %-24s program or arguments missing, %d frames"
                  % ("|".join(w), MIN_FRAMES))
            continue
        name = "probe-%s-%s-%s-%s" % w
        res = runner.run(prog, a, name)
        got = parse_ours(res["text"])
        runner.save_log(res, "speed probe %s -> %s"
                        % ("|".join(w), got["fps"] if got else "NOT PARSED"))
        fps = got["fps"] if got else None
        plan[w] = frames_for_speed(fps)
        print("  %-24s %-12s -> %d frames per launch"
              % ("|".join(w),
                 ("%.1f fps" % fps) if fps else "NOT PARSED",
                 plan[w]))

    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"script_version": VERSION,
                   "run_seconds": RUN_SECONDS,
                   "min_frames": MIN_FRAMES,
                   "probe_frames": PROBE_FRAMES,
                   "frames": dict(("|".join(k), v) for k, v in plan.items())},
                  fh, ensure_ascii=False, indent=2)
    return plan


def load_runs(path):
    """Every launch already made: (point, repeat) -> row."""
    done = {}
    if not os.path.isfile(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if "key" in row and "rep" in row:
                done[(row["key"], row["rep"])] = row
    return done


def aggregate(runs):
    """Median over the repeats of one point."""
    by_key = {}
    for (k, _), row in runs.items():
        by_key.setdefault(k, []).append(row)
    out = {}
    for k, rows in by_key.items():
        good = [r["fps"] for r in rows if r.get("fps")]
        base = dict(rows[0])
        base["fps"] = median(good)
        base["reps"] = len(rows)
        base["spread"] = (100.0 * (max(good) - min(good)) / min(good)
                          if len(good) > 1 else 0.0)
        base["walls"] = [r.get("wall_s") for r in rows]
        base["totals"] = [r.get("frames") for r in rows]
        out[k] = base
    return out


# ---------------------------------------------------------------------------
# command lines
# ---------------------------------------------------------------------------

def cmd_args(pt, frames, nv_q):
    """One launch of our harness or of a Fastvideo sample.

    Every point here is the threads-and-batch mode: the boundary is host
    memory to host memory on both sides, both programs say "including all
    transfers", and nothing is added to make them mirror each other. The single
    frame mode, where the boundary has to be brought together by hand, is not
    part of this run - it is measured by bench-05.
    """
    img = dict(IMAGES)[pt["tag"]]
    extra = ["-repeat", frames, "-async", "-thread", pt["threads"],
             "-b", pt["batch"]]
    if pt["dir"] == "enc":
        a = ["-i", img, "-o", "tmp-stock.jp2", "-a", pt["alg"],
             "-c", CODE_BLOCK, "-l", LEVELS]
        if pt["alg"] == "irrev":
            q = FV_QUALITY if pt["codec"] == "fv" else nv_q.get(pt["tag"])
            if q is None:
                return None
            a += ["-q", q]
    else:
        a = ["-i", ref_name(pt["codec"], pt["tag"], pt["alg"]),
             "-o", "tmp-stock.ppm"]
    return a + extra + ["-discard"]


def cmd_args_nv_sample(pt, refdir):
    """NVIDIA's decoding sample. Options from its own README:
    -i images_dir [-b batch_size] [-t total_images] [-w warmup_iterations]."""
    return ["-i", refdir, "-b", pt["batch"], "-t", pt["total"], "-w", 1]


def cmd_args_nv_sample_enc(pt, srcdir, q, warmup=1, outdir=None):
    """NVIDIA's encoding sample, set to our conditions.

    Everything that decides what is encoded is either given here or hard-coded
    in their program the way we need it:
      -cblk 32,32   the code block of the article, their -c 32
      six resolution levels and the LRCP progression are hard-coded in their
                    sample, and they are ours
      -I            the irreversible 9/7 wavelet, that is the lossy mode;
                    without it the reversible 5/3, that is lossless
      -q_factor Q   the Q-factor scale - the same one we set for nvJPEG2000
                    in the article, and Q is the value our own calibration
                    found for an equal file size
    """
    a = ["-i", srcdir, "-b", pt["batch"], "-t", pt["total"],
         "-cblk", "%s,%s" % (CODE_BLOCK, CODE_BLOCK)]
    if warmup:
        a += ["-w", warmup]
    if outdir:
        a += ["-o", outdir]
    if pt["alg"] == "irrev":
        if q is None:
            return None
        a += ["-I", "-q_factor", q]
    return a


# ---------------------------------------------------------------------------
# one launch
# ---------------------------------------------------------------------------

def outcome(row):
    """One short word about a launch, for the progress line.

    A point that was refused before it started is not the same thing as a
    point whose output did not parse, and calling both "not parsed" hides
    which of the two happened.
    """
    if row is None:
        return "NOT RUN"
    if row.get("skipped"):
        return "NOT MEASURED"
    if row.get("fps"):
        return "%.1f fps" % row["fps"]
    return "NOT PARSED"


def measure(runner, folder, pt, rep, frames, nv_q, nv_sample, harness,
            nv_encode_sample=""):
    if pt["prog"] == "nvsample_enc":
        d = nvsample_dir_enc(folder, pt["tag"], make=True)
        ok, why = nvsample_ready(d, ".ppm")
        if not ok:
            row = dict(pt)
            row.update({"key": key(pt), "rep": rep, "fps": None,
                        "skipped": why})
            runner.record(row)
            return row
        a = cmd_args_nv_sample_enc(pt, d, nv_q.get(pt["tag"]))
        if a is None:
            row = dict(pt)
            row.update({"key": key(pt), "rep": rep, "fps": None,
                        "skipped": "no matched quality for this frame, the "
                                   "lossy point cannot be set"})
            runner.record(row)
            return row
        prog = nv_encode_sample
    elif pt["prog"] == "nvsample":
        d = nvsample_dir(folder, pt["tag"], pt["alg"], make=True)
        ok, why = nvsample_ready(d)
        if not ok:
            row = dict(pt)
            row.update({"key": key(pt), "rep": rep, "fps": None,
                        "skipped": why})
            runner.record(row)
            return row
        prog, a = nv_sample, cmd_args_nv_sample(pt, d)
    else:
        prog = exe_path(folder, CODECS[pt["codec"]][pt["dir"]])
        a = cmd_args(pt, frames, nv_q)
        if a is None or prog is None:
            return None
    name = "%s-%s-%s-%s-%dx%d%s-r%d" % (
        pt["prog"], pt["dir"], pt["tag"], pt["alg"], pt["threads"],
        pt["batch"], "-t%d" % pt["total"] if pt.get("total") else "", rep)
    res = runner.run(prog, a, name)
    if pt["prog"] == "nvsample":
        got = parse_nv_sample(res["text"], "nvidia_decode_call")
    elif pt["prog"] == "nvsample_enc":
        got = parse_nv_sample(res["text"], "nvidia_encode_events")
    else:
        got = parse_ours(res["text"])
    runner.save_log(res, "%s -> %s"
                    % (key(pt), got["fps"] if got else "NOT PARSED"))
    row = dict(pt)
    row.update({"key": key(pt), "rep": rep, "log": name,
                "frames": pt.get("total") or frames,
                "fps": got["fps"] if got else None,
                "boundary": got.get("boundary") if got else None,
                "threads_printed": got["threads_printed"] if got else None,
                "code": res["code"], "wall_s": res["wall_s"]})
    if pt["codec"] == "nv" and pt["prog"] != "nvsample":
        row["nv_harness"] = harness.get(CODECS["nv"][pt["dir"]])
    runner.record(row)
    return row


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------

def nv_sample_by_clock(pts):
    """The speed of NVIDIA's program from the difference of two run lengths.

    Their counter covers the decode call only, so their own figure is not
    comparable with ours. Two runs of different length, measured by the wall
    clock, give (n2 - n1) / (t2 - t1): everything that does not depend on the
    number of frames - starting the process, setting up CUDA, reading the file
    - cancels out.
    """
    out = {}
    for k, r in pts.items():
        # A wall time of zero is a measurement, not a missing value: a short
        # run on a fast workload rounds to nothing. Testing it for truth
        # dropped half of every pair and the table lost whole rows.
        if r.get("step") != 1 or r.get("wall_s") is None:
            continue
        g = (r.get("prog"), r["tag"], r["alg"], r["batch"])
        out.setdefault(g, {})[r.get("total")] = r
    done, why = {}, {}
    for g, per in out.items():
        n1, n2 = NV_SAMPLE_TOTALS[0], NV_SAMPLE_TOTALS[-1]
        a, b = per.get(n1), per.get(n2)
        if not (a and b):
            why[g] = "only one of the two run lengths was measured"
            continue
        wa = median([w for w in (a.get("walls") or [a.get("wall_s")])
                     if w is not None])
        wb = median([w for w in (b.get("walls") or [b.get("wall_s")])
                     if w is not None])
        # A zero is a number here, not a missing value: on a fast workload the
        # short run can round to nothing. Testing it for truth silently dropped
        # whole rows out of the table.
        if wa is None or wb is None:
            why[g] = "the clock was not recorded"
            continue
        if wb <= wa:
            why[g] = ("the long run was not slower than the short one "
                      "(%.1f s against %.1f s): the difference says nothing"
                      % (wb, wa))
            continue
        done[g] = {"fps_clock": (n2 - n1) / (wb - wa),
                   "fps_own": b.get("fps"), "wall_s": (wa, wb)}
    return done, why


def write_summary(folder, res_path, out_path, prep, harness, note=""):
    runs = load_runs(res_path)
    pts = aggregate(runs)
    L = []
    add = L.append
    add("%s, version %s" % (SCRIPT_NAME, VERSION))
    add("nvJPEG2000: what the library gives, and what our way of driving it "
        "adds")
    add("made: " + datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
    add("")
    if note:
        add(note)
        add("")
    add("Which build measured")
    for name, v in sorted(harness.items()):
        add("   %-24s %s" % (name, v or "not found"))
    add("")
    if prep:
        add("Conditions")
        add("   code block %s, levels %s, our quality %s"
            % (CODE_BLOCK, LEVELS, FV_QUALITY))
        add("   measuring window %.0f s per launch, never fewer than %d "
            "frames" % (RUN_SECONDS, MIN_FRAMES))
        for tag in sorted(prep.get("nv_q", {})):
            add("   nvJPEG2000 quality matched to our file size, %s: %.2f"
                % (tag, prep["nv_q"][tag]))
        if prep.get("nv_sample_sizes"):
            add("")
            add("   The file NVIDIA's own encoder makes at that quality,")
            add("   against our reference of the same workload:")
            for k in sorted(prep["nv_sample_sizes"]):
                got = prep["nv_sample_sizes"][k]
                tag, alg = k.split("_", 1)
                ours = prep.get("sizes", {}).get(ref_name("nv", tag, alg))
                if got is None:
                    add("     %-12s their encoder wrote no file" % k)
                elif ours:
                    add("     %-12s %9d bytes against %9d, %+.2f %%"
                        % (k, got, ours, 100.0 * (got - ours) / ours))
                else:
                    add("     %-12s %9d bytes" % (k, got))
        add("")

    bad = [r for r in pts.values() if not r.get("fps")]
    boundaries = {}
    for r in pts.values():
        if r.get("boundary"):
            boundaries.setdefault(r["boundary"], 0)
            boundaries[r["boundary"]] += 1

    add("What went into the measured time")
    for b in sorted(boundaries):
        add("   %-20s %4d points   %s"
            % (b, boundaries[b],
               WINDOW_TEXT.get(b, "NVIDIA's program: the decode call only")))
    # NVIDIA's own samples measure between their own points, and that is said
    # about them in their own section. The boundary that has to be one and the
    # same is the boundary of ladders 2 and 3, where the two codecs are put
    # side by side.
    mixed = [b for b in boundaries if not b.startswith("nvidia_")]
    if len(mixed) > 1:
        add("")
        add("   ATTENTION: the points of ladders 2 and 3 do not share one")
        add("   boundary. Numbers measured between different points are not")
        add("   comparable and must not go into the article.")
    add("")

    # --- ladder 1 ---------------------------------------------------------
    clock, clock_why = nv_sample_by_clock(pts)
    for prog, title, note in (
            ("nvsample", "LADDER 1, DECODING. NVIDIA's own program, as it comes",
             ["Their counter wraps the decode call only: the parsing of the",
              "compressed image on the CPU stays outside, and there is no copy",
              "of the finished frame back to host memory in the measured loop",
              "at all. Their figure is therefore NOT comparable with ours",
              "directly - the column to compare is the one taken by the clock."]),
            ("nvsample_enc", "LADDER 1, ENCODING. NVIDIA's own program, as it "
                             "comes",
             ["Here their boundary is ours: their counter holds the encode call",
              "and the copy of the compressed stream into host memory, while",
              "the upload of the source frame happens before the timer starts.",
              "That is the boundary of our own single frame mode, and the rest",
              "of the configuration matches too - six resolution levels, LRCP,",
              "code block %s, and the Q-factor scale. So this half CAN be put"
              % CODE_BLOCK,
              "beside our single frame column. The clock column is given as",
              "well, and the two should agree within a few per cent."])):
        rows = [r for r in pts.values() if r.get("prog") == prog]
        if not rows:
            continue
        add(title)
        for line in note:
            add(line)
        add("")
        add("   frame mode      batch   their figure   by the clock")
        for tag, _ in IMAGES:
            for alg in ALGS:
                for b in NV_SAMPLE_BATCH:
                    g = (prog, tag, alg, b)
                    r = clock.get(g)
                    if r:
                        add("   %-3s   %-9s %5d %13.1f %14.1f"
                            % (tag, ALG_NAME[alg], b, r["fps_own"] or 0,
                               r["fps_clock"]))
                    elif g in clock_why:
                        add("   %-3s   %-9s %5d   not computed: %s"
                            % (tag, ALG_NAME[alg], b, clock_why[g]))
        add("")
    if not clock and not clock_why:
        add("LADDER 1 WAS NOT MEASURED. Neither of NVIDIA's own programs was")
        add("given, so what the library does as NVIDIA ships it is not")
        add("answered by this run.")
        add("")
    elif not any(r.get("prog") == "nvsample_enc" for r in pts.values()):
        add("LADDER 1 IS HALF MEASURED: the encoding half has no program here,")
        add("so what NVIDIA's own encoder does is not answered by this run.")
        add("")
    elif not any(r.get("prog") == "nvsample" for r in pts.values()):
        add("LADDER 1 IS HALF MEASURED: the decoding half has no program here,")
        add("so what NVIDIA's own decoder does is not answered by this run.")
        add("")

    # --- ladders 2 and 3 --------------------------------------------------
    for step, title in ((2, "LADDER 2. One codec state and one stream per "
                            "thread"),
                        (3, "LADDER 3. Our trick: several states per thread")):
        rows = [r for r in pts.values() if r.get("step") == step
                and r.get("fps")]
        if not rows:
            continue
        add(title)
        add("")
        add("   codec dir frame mode      combination      fps   repeats "
            "spread")
        for c in ("nv", "fv"):
            for d in ("enc", "dec"):
                for tag, _ in IMAGES:
                    for alg in ALGS:
                        sel = [r for r in rows if r["codec"] == c
                               and r["dir"] == d and r["tag"] == tag
                               and r["alg"] == alg]
                        for r in sorted(sel, key=lambda x: (x["threads"],
                                                            x["batch"])):
                            add("   %-5s %-3s %-3s   %-9s %6s %10.1f %6d "
                                "%6.1f %%"
                                % (c, d, tag, ALG_NAME[alg],
                                   "%dx%d" % (r["threads"], r["batch"]),
                                   r["fps"], r.get("reps", 1),
                                   r.get("spread", 0.0)))
        add("")

    # --- what the trick adds ----------------------------------------------
    add("WHAT THE TRICK ADDS")
    add("The best point of ladder 3 against the best point of ladder 2, on the")
    add("same workload. Below one means the trick adds nothing and the library")
    add("only needed more threads.")
    add("")
    add("   codec dir frame mode      ladder 2        ladder 3        ratio")
    for c in ("nv", "fv"):
        for d in ("enc", "dec"):
            for tag, _ in IMAGES:
                for alg in ALGS:
                    best = {}
                    for step in (2, 3):
                        sel = [r for r in pts.values()
                               if r.get("step") == step and r.get("fps")
                               and r["codec"] == c and r["dir"] == d
                               and r["tag"] == tag and r["alg"] == alg]
                        if sel:
                            best[step] = max(sel, key=lambda x: x["fps"])
                    if 2 in best and 3 in best:
                        add("   %-5s %-3s %-3s   %-9s %6s %7.1f %6s %7.1f "
                            "%7.2f"
                            % (c, d, tag, ALG_NAME[alg],
                               "%dx%d" % (best[2]["threads"],
                                          best[2]["batch"]),
                               best[2]["fps"],
                               "%dx%d" % (best[3]["threads"],
                                          best[3]["batch"]),
                               best[3]["fps"],
                               best[3]["fps"] / best[2]["fps"]))
    add("")

    if bad:
        add("NOT PARSED: %d points. Nothing is skipped in silence - here they"
            % len(bad))
        add("are, and their logs are in %s:" % LOGDIR)
        for r in sorted(bad, key=lambda x: x.get("key", "")):
            add("   %-44s %s" % (r.get("key"),
                                 r.get("skipped") or "the output did not parse"))
        add("")

    skipped = [r for r in pts.values() if r.get("skipped")]
    add("Points in the report: %d, of them without a number: %d"
        % (len(pts), len(bad)))
    if skipped:
        add("Not measured at all: %d" % len(skipped))

    text = "\n".join(L) + "\n"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return len(pts), len(bad)


# ---------------------------------------------------------------------------
# checks before anything is measured
# ---------------------------------------------------------------------------

def selftest(folder, args):
    """Checks before anything is measured.

    Two kinds of outcome, kept apart on purpose. A blocker stops the run and
    goes into a numbered list at the end, with the command that clears it -
    "something to fix" without saying what is not a message, it is a shrug.
    A warning is printed where it belongs and does not stop anything.
    """
    ok = True
    todo = []
    print("\nCHECKS BEFORE THE RUN")
    print("Folder: %s" % folder)
    print("Python %s on %s" % (platform.python_version(), platform.platform()))
    if sys.version_info < (3, 6):
        print("  ! Python 3.6 or newer is needed")
        ok = False

    codecs = ["nv", "fv"]     # the Fastvideo encoder is needed even for a
                              # nvJPEG2000-only run: it makes the reference
                              # streams and sets the file size to match
    print("\n  Programs")
    for c in codecs:
        for role in ("enc", "dec"):
            name = CODECS[c][role]
            p = exe_path(folder, name)
            need = "needed" if (c == "nv" or args.with_fv
                                or role == "enc") else "not needed here"
            print("    %-24s %-28s %s"
                  % (name, p if p else "NOT FOUND", need))
            if not p and (c == "nv" or role == "enc" or args.with_fv):
                todo.append(("%s is not in this folder" % name,
                             ["put the script next to the sample programs, or",
                              "point at that folder:  --dir <path>"]))
                ok = False

    print("\n  Source frames")
    for tag, img in IMAGES:
        p = os.path.join(folder, img)
        if os.path.isfile(p):
            g = ppm_size(p)
            print("    %-24s %s" % (img, ("%d x %d" % g) if g
                                    else "the header did not read"))
        else:
            print("    %-24s NOT FOUND" % img)
            todo.append(("the source frame %s is not in this folder" % img,
                         ["both frames are needed: the run encodes its own",
                          "reference streams out of them"]))
            ok = False

    print("\n  Reference streams")
    made = [ref_name(c, tag, alg) for c in ("fv", "nv")
            for tag, _ in IMAGES for alg in ALGS]
    there = [r for r in made
             if os.path.isfile(os.path.join(folder, r))]
    if len(there) == len(made):
        print("    all %d are there" % len(made))
    else:
        print("    %d of %d are there - the rest will be made by the"
              % (len(there), len(made)))
        print("    preparation step, from the two frames. Nothing has to be")
        print("    brought from an earlier run.")

    print("\n  Which build is in the executables")
    harness = harness_versions(folder)
    for name, v in sorted(harness.items()):
        print("    %-24s %s" % (name, v or "not found"))
    old = [k for k, v in harness.items() if v == "before 02"]
    dead = [k for k, v in harness.items()
            if v and str(v).startswith("did not start")]
    if old:
        print("    ! Built from a source older than nvj2k_bench-02: it does")
        print("      not know -version. Until 28.08.2026 that build did not")
        print("      copy the decoded frame back to host memory while still")
        print("      printing that it did, so its throughput numbers cannot")
        print("      be compared with ours.")
        todo.append(
            ("the executables are built from an older source: %s"
             % ", ".join(sorted(old)),
             ["build the new one - this only builds, measures nothing:",
              "  python bench-05.py --build",
              "or by hand, from an x64 Native Tools Command Prompt:",
              "  del nvj2kEncoderSample.exe nvj2kDecoderSample.exe",
              "  cl /nologo /EHsc /O2 /MD /std:c++14 nvj2k_bench-02.cpp ...",
              "then check:  nvj2kDecoderSample.exe -version"]))
        ok = False
    if dead:
        print("    ! Did not start at all: %s" % ", ".join(sorted(dead)))
        print("      That is not an old build - the program could not run.")
        print("      Most often a missing DLL: nvjpeg2k or cudart.")
        todo.append(
            ("these programs do not start: %s" % ", ".join(sorted(dead)),
             ["run one by hand and read what Windows says:",
              "  nvj2kDecoderSample.exe -version",
              "usually nvjpeg2k.dll or cudart is not next to it or not on PATH"]))
        ok = False

    # Ladder 1 never stops a run. Missing programs are said out loud here and
    # again in the report; that is not silence, and it is not a reason to make
    # somebody type another option to get a run started.
    print("\n  NVIDIA's own programs, ladder 1")
    missing = []
    for role, what, given in (("dec", "decoding", args.nv_sample),
                              ("enc", "encoding", args.nv_encode_sample)):
        found = find_nv_sample(folder, role, given)
        if found:
            print("    %-9s %s" % (what, found))
        elif given:
            print("    %-9s NOT FOUND at the given path: %s" % (what, given))
            missing.append(what)
        else:
            print("    %-9s not found: %s"
                  % (what, " or ".join(NV_SAMPLE_NAMES[role])))
            missing.append(what)
    if missing:
        print("")
        print("    LADDER 1 %s: %s"
              % ("WILL NOT BE MEASURED" if len(missing) == 2
                 else "WILL BE HALF MEASURED", ", ".join(missing)))
        print("    The run goes on, and the report says the same in the same")
        print("    words. But what the library gives as NVIDIA ships it stays")
        print("    unanswered, and the note at the end of the article cannot")
        print("    be written from this run.")
        print("    To measure it: build both programs and put them in this")
        print("    folder - they are then found by themselves, no options")
        print("    needed. Sources and build commands:")
        print("       python get-nvidia-sample-02.py --dir D:\\nvj2k")

    if ok:
        print("\nChecks passed.")
        return True
    print("\n" + "=" * 62)
    print(" WHAT TO FIX - nothing was measured")
    print("=" * 62)
    for i, (what, how) in enumerate(todo, 1):
        print(" %d. %s" % (i, what))
        for line in how:
            print("      %s" % line)
        print("")
    if not todo:
        print(" See the lines marked NOT FOUND above.")
    print(" Then run the checks again:")
    print("   python %s --selftest" % SCRIPT_NAME)
    return False


# ---------------------------------------------------------------------------
# what a bare start prints
# ---------------------------------------------------------------------------

def usage(folder):
    print("=" * 72)
    print(" %s, version %s" % (SCRIPT_NAME, VERSION))
    print(" nvJPEG2000: what the library gives, and what our way of driving")
    print(" it adds. Three ladders in one run.")
    print("=" * 72)
    print("")
    print(" Nothing was measured: a run has to be asked for by name.")
    print("")
    print(" HOW TO RUN IT")

    def how(opt, first, second=""):
        left = "   python %s %s" % (SCRIPT_NAME, opt)
        print("%-58s %s" % (left, first))
        if second:
            print("%-58s %s" % ("", second))

    how("--selftest", "checks only, measures nothing")
    how("--trial", "one point per branch of the code,",
        "about 7 minutes")
    how("--frames-scan", "ten points at 1000, 2000, 5000 and",
        "10000 frames: how long a launch has to be")
    how("--final", "THE RUN")
    how("--summary", "rebuilds the report, measures nothing")
    print("")
    print("   Add --with-fv to measure our codec on ladders 2 and 3 as well;")
    print("   the run then takes about twice as long.")
    print("")
    print("   Nothing else has to be passed. The reference streams are made")
    print("   by the run itself, and NVIDIA's own programs are found in this")
    print("   folder by name. (--prepare, --frames, --dir, --nv-sample and")
    print("   --nv-encode-sample exist for the odd case; -h lists them.)")
    print("")
    print("   Ctrl-C stops a run at any point. The program being measured is")
    print("   killed, and every measurement already made stays in %s."
          % RESULTS)
    print("")
    print(" WHAT HAS TO BE IN THIS FOLDER")
    print("   folder: %s" % folder)
    need = [(CODECS["fv"]["enc"], "Fastvideo encoder: makes the references"),
            (CODECS["fv"]["dec"], "Fastvideo decoder: only with --with-fv"),
            (CODECS["nv"]["enc"], "nvJPEG2000 encoder"),
            (CODECS["nv"]["dec"], "nvJPEG2000 decoder")]
    for tag, img in IMAGES:
        need.append((img, "source frame, %s" % tag.upper()))
    missing = 0
    for name, what in need:
        there = (exe_path(folder, name) if not name.endswith(".ppm")
                 else (os.path.join(folder, name)
                       if os.path.isfile(os.path.join(folder, name)) else None))
        if not there:
            missing += 1
        print("   %-24s %-42s %s" % (name, what,
                                     "found" if there else "NOT FOUND"))
    print("")
    print("   The reference .jp2 streams are NOT needed beforehand: the")
    print("   preparation step makes all eight of them out of the two frames,")
    print("   at our quality 85 and at the nvJPEG2000 quality that gives a")
    print("   file of the same size.")
    print("")
    if missing:
        print(" %d of the above are not here. Put the script next to the"
              % missing)
        print(" programs and the frames, or point at that folder with --dir.")
    else:
        print(" Everything needed is here. Start with --selftest.")
    return 1


# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) == 1:
        return usage(os.path.dirname(os.path.abspath(__file__)))

    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)),
                    help="folder with the programs and the frames")
    ap.add_argument("--frames", type=int, default=0,
                    help="fixed frames per launch; by default the count is "
                         "computed per workload from the measured speed")
    ap.add_argument("--with-fv", action="store_true",
                    help="measure our codec on ladders 2 and 3 as well")
    ap.add_argument("--nv-sample", default="",
                    help="path to NVIDIA's own decoding program, ladder 1")
    ap.add_argument("--nv-encode-sample", default="",
                    help="path to NVIDIA's own encoding program, ladder 1")
    ap.add_argument("--selftest", action="store_true",
                    help="checks only, measures nothing")
    ap.add_argument("--prepare", action="store_true",
                    help="make the reference streams and stop")
    ap.add_argument("--trial", action="store_true",
                    help="one point per branch of the code, about 7 minutes")
    ap.add_argument("--final", action="store_true", help="the run")
    ap.add_argument("--summary", action="store_true",
                    help="rebuild the report, measure nothing")
    ap.add_argument("--frames-scan", action="store_true",
                    help="ten points at 1000, 2000, 5000 and 10000 frames: "
                         "how long a launch has to be")
    args = ap.parse_args()

    folder = os.path.abspath(args.dir)
    print("%s, version %s" % (SCRIPT_NAME, VERSION))
    print("Started: %s" % datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    print("Folder:  %s" % folder)

    suffix = TRIAL_SUFFIX if args.trial else ""
    res_path = os.path.join(folder, RESULTS.replace(".jsonl",
                                                    suffix + ".jsonl"))
    sum_path = os.path.join(folder, SUMMARY.replace(".txt", suffix + ".txt"))
    logdir = os.path.join(folder, LOGDIR + suffix)
    fixed_frames = 20 if args.trial else args.frames

    prep_path = os.path.join(folder, PREP)
    prep = None
    if os.path.isfile(prep_path):
        with open(prep_path, encoding="utf-8") as fh:
            prep = json.load(fh)
    harness = harness_versions(folder)

    if args.summary:
        n, bad = write_summary(folder, res_path, sum_path, prep, harness)
        print("Report rebuilt: %s\nPoints %d, without a number %d"
              % (sum_path, n, bad))
        return 0

    if args.selftest:
        return 0 if selftest(folder, args) else 1

    if not (args.prepare or args.trial or args.final or args.frames_scan):
        print("")
        print("Nothing was asked for. Add --selftest, --prepare, --trial,")
        print("--frames-scan, --final or --summary. Run without options for")
        print("the full list.")
        return 1

    if not selftest(folder, args):
        return 1

    nv_dec_sample = find_nv_sample(folder, "dec", args.nv_sample)
    nv_enc_sample = find_nv_sample(folder, "enc", args.nv_encode_sample)

    HEART.start()

    if args.frames_scan:
        prep_only = None
        if prep is None:
            print("")
            print("The reference streams are not made yet. Run --prepare or")
            print("--final once; the scan needs the same streams.")
            HEART.stop()
            return 1
        nv_q = dict((k, v) for k, v in prep.get("nv_q", {}).items())
        codecs = ["nv"] + (["fv"] if args.with_fv else [])
        rows = frames_scan(folder, codecs, nv_q, harness,
                           os.path.join(folder, SCAN_RESULTS),
                           os.path.join(folder, SCAN_LOGDIR))
        for line in frames_scan_table(rows):
            print(line)
        HEART.stop()
        return 0

    runner = Runner(folder, logdir, res_path)
    t0 = time.time()

    try:
        prep = prepare(runner, folder, force=args.prepare,
                       nv_encode_sample=nv_enc_sample)
        if prep is None:
            print("\nPreparation did not finish. Nothing was measured.")
            return 1
        if args.prepare:
            print("\nPreparation done. Next: --trial, then --final.")
            return 0
        nv_q = dict((k, v) for k, v in prep.get("nv_q", {}).items())

        todo = points(args.with_fv, nv_dec_sample, args.trial, nv_enc_sample)

        # How many frames each launch gets. A fixed count was version 01's
        # mistake: the same 200 frames made a tenth of a second of measuring
        # on the fastest point and three seconds on the slowest.
        if fixed_frames:
            plan = {}
        else:
            plan = probe(runner, folder, todo, nv_q, harness,
                         os.path.join(folder, PROBE))

        def frames_of(pt):
            if fixed_frames:
                return fixed_frames
            return plan.get(workload_of(pt), MIN_FRAMES)

        runs = load_runs(res_path)
        pass1 = [p for p in todo if (key(p), 1) not in runs]
        refine_est = 0 if args.trial else (
            REFINE_TOP * (REFINE_RUNS - 1)
            * len({group_of(p) for p in todo if p["step"] != 1}))
        est = len(pass1) + refine_est

        print("\n%s" % ("TRIAL RUN - mistakes are found here, not two hours in."
                        if args.trial else "THE RUN"))
        print("Points: %d, of them already measured: %d"
              % (len(todo), len(todo) - len(pass1)))
        if fixed_frames:
            print("Frames per launch: %d, fixed by --frames." % fixed_frames)
        else:
            counts = sorted(set(plan.values()))
            print("Frames per launch: from %d to %d, by workload - enough to"
                  % (counts[0] if counts else MIN_FRAMES,
                     counts[-1] if counts else MIN_FRAMES))
            print("measure for %.0f seconds, and never fewer than %d."
                  % (RUN_SECONDS, MIN_FRAMES))
        print("About %d launches, %s." % (est, human(est * SEC_PER_RUN)))
        if not args.trial:
            print("Order: the whole grid once, then the two best points of")
            print("each group are taken to three launches. The conclusion is")
            print("drawn from the best point, so that is what needs repeating.")
        print("Results are written as they are made: %s" % res_path)

        for i, pt in enumerate(pass1, 1):
            row = measure(runner, folder, pt, 1, frames_of(pt), nv_q,
                          nv_dec_sample, harness, nv_enc_sample)
            el = (time.time() - t0) / 60.0
            print("%s  %-46s %-14s [%d/%d, about %.0f min left]"
                  % (now(), key(pt), outcome(row), i, len(pass1),
                     el / max(i, 1) * (len(pass1) - i)))

        if not args.trial:
            pts = aggregate(load_runs(res_path))
            groups = {}
            for k, r in pts.items():
                # Ladder 1 is not repeated: there a pair of run lengths is
                # what is needed, not repeats of one length.
                if r.get("fps") and r.get("step") != 1:
                    groups.setdefault(group_of(r), []).append(r)
            refine = []
            for g, rr in groups.items():
                for r in sorted(rr, key=lambda x: -x["fps"])[:REFINE_TOP]:
                    for rep in range(2, REFINE_RUNS + 1):
                        if (r["key"], rep) not in runs:
                            refine.append((r, rep))
            if refine:
                print("\nTaking the best points to three launches: %d launches,"
                      " %s." % (len(refine), human(len(refine) * SEC_PER_RUN)))
            for i, (r, rep) in enumerate(refine, 1):
                pt = dict((k, r[k]) for k in ("step", "codec", "prog", "dir",
                                              "tag", "alg", "threads", "batch")
                          if k in r)
                if r.get("total"):
                    pt["total"] = r["total"]
                row = measure(runner, folder, pt, rep, frames_of(pt), nv_q,
                              nv_dec_sample, harness, nv_enc_sample)
                print("%s  %-46s %-14s [%d/%d, repeat %d]"
                      % (now(), key(pt), outcome(row), i, len(refine),
                         rep))
    except KeyboardInterrupt:
        HEART.stop()
        runner.close()
        print("")
        print("Stopped by Ctrl-C after %s." % human(time.time() - t0))
        print("Measured so far: %d launches, all of them in" % runner.count)
        print("   %s" % res_path)
        print("Logs of every launch: %s" % logdir)
        print("The report was not written; rebuild it at any time with")
        print("   python %s --summary%s"
              % (SCRIPT_NAME, " --trial" if args.trial else ""))
        print("Starting the run again continues from here: what has been")
        print("measured is not measured twice.")
        return 130

    HEART.stop()
    runner.close()
    note = ("This is a TRIAL run: %d frames per launch, one launch per point. "
            "The numbers are good for checking that everything works, nothing "
            "else." % fixed_frames) if args.trial else ""
    n, bad = write_summary(folder, res_path, sum_path, prep, harness, note)
    print("\nDone. Launches: %d, time %s."
          % (runner.count, human(time.time() - t0)))
    print("Points in the report: %d, without a number: %d" % (n, bad))
    print("Results: %s" % res_path)
    print("Report:  %s" % sum_path)
    print("Logs:    %s" % logdir)
    if args.trial:
        print("")
        print("If the report has no NOT PARSED lines and the numbers look")
        print("sane, start the real run: --final.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
