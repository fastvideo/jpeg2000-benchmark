#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# bench-04.py
# version 2026-08-24.2 of 24.08.2026
# what is new since bench-03: the dry run no longer crashes when the folder
# already holds the reference streams of an earlier real run. Bench.run()
# returned an empty STRING in dry mode while the caller asked it for .get(),
# and the branch is only reached when those files exist. The bug came from the
# published version, not from the energy work; it is fixed by returning an
# empty dict. Older change, since bench-02: a second, independent energy meter - the card's
# own cumulative energy counter (NVML) - and the differential method: the same
# point is measured on N and on 2N frames, and the energy of one frame is the
# difference divided by N, so everything that does not depend on the number of
# frames cancels out. The two meters are printed side by side. The version now
# goes into summary.txt, into the first column of results.csv and into
# results.json, so any old result can be traced back to the code that made it.
"""
JPEG2000 codec comparison, one file, one command.

    python bench.py

Runs both codecs - Fastvideo and nvJPEG2000 - measures the latency figure and
the best throughput point for every configuration, and prints a comparison
table. Writes results.csv, summary.txt and every raw log into a dated folder.

The run is time-budgeted: the script first probes the speed of each codec on
each workload, then chooses how many frames each measurement needs so that the
whole thing fits into the budget. Ten minutes by default, on any card.

If the nvJPEG2000 executables are missing or older than nvj2k_bench.cpp, the
script builds them itself with the Microsoft compiler - no separate build step.

    python bench.py --budget 300      five minutes
    python bench.py --codec fv        one codec only
    python bench.py --no-build        never invoke the compiler
    python bench.py --dry-run         print the plan, measure nothing

Standard library only. Python 3.6+.
"""

import argparse
import csv
import datetime
import json
import textwrap
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------------------
# what is measured
# ---------------------------------------------------------------------------

BENCH_VERSION = "2026-08-24.2"              # printed into every result file

# how long one energy measurement takes, seconds; the second one is twice that
ENERGY_RUN_S = 6.0

EXE = ".exe" if os.name == "nt" else ""     # Windows or Linux, incl. Jetson

CODECS = {
    "fv": {"enc": "J2kEncoderSample" + EXE, "dec": "J2kDecoderSample" + EXE,
           "name": "Fastvideo"},
    "nv": {"enc": "nvj2kEncoderSample" + EXE, "dec": "nvj2kDecoderSample" + EXE,
           "name": "nvJPEG2000"},
}

IMAGES = [("2k", "2k_wild.ppm"), ("4k", "4k_wild.ppm")]
ALGS = ["irrev", "rev"]                  # lossy 9/7, lossless 5/3
ALG_RU = {"irrev": "lossy", "rev": "lossless"}
POINTS = [(8, 1), (8, 2), (16, 2), (8, 4)]

# Compression ratios at which the comparison is repeated. Decoding time depends
# on how many coding passes the stream carries, so a single ratio is one point
# on a curve, not the curve.
RATIOS = [5.0, 10.0, 20.0]

# Chroma subsampling reference points. Measured for the Fastvideo codec only:
# nvJPEG2000 expects components that are already subsampled, so on that side the
# downsampling would have to be done outside the codec, and the comparison would
# measure our resampling filter rather than either codec.
SUBSAMPLING = ["444", "422", "420"]

# The quality ladder of the Fastvideo codec, printed as a table: the same knob
# gives very different compression on different frames, and the article needs
# the evidence rather than the claim.
QUALITY_LADDER = [80, 83, 85, 87, 90]

# Check of the correspondence between the two quality scales: the same search
# repeated at several quality levels and from two different starting intervals.
SCALE_CHECK_Q = [80, 85, 90]
SCALE_CHECK_TOL = 0.0005                 # 0.05 % by size, twice as tight
CALIB_TOL = 0.001

CODE_BLOCK = 32
LEVELS = 6
FV_QUALITY = 85                          # Fastvideo quality scale
PROBE_FRAMES = 200                       # frames used to estimate the speed
PROBE_POINT = (8, 2)
MIN_RUN_S = 1.5
MAX_RUN_S = 6.0
STARTUP_S = 0.8                          # process start, driver init, per run

# ---------------------------------------------------------------------------
# reading the output of the sample programs
# ---------------------------------------------------------------------------

RE_SDK = re.compile(r"SDK version:\s*(\S+)")
RE_GPU = re.compile(r"Processing unit:\s*(.+?)\s*\(device id")
RE_PCIE = re.compile(r"PCI-Express bandwidth test \(host to device\):\s*([\d.]+)")
RE_MEM = re.compile(r"Requested GPU memory size:\s*([\d.]+)\s*(GB|MB|KB)")
RE_AVAIL = re.compile(r"Available GPU memory size:\s*([\d.]+)\s*(GB|MB|KB)")
RE_SIZE = re.compile(r"size\s*=\s*(\d+)\s*KB\s*\(([\d.]+):1\)")
RE_CALIB = re.compile(r"Calibration:\s*q\s*=\s*([\d.]+)")
RE_CALIB_FULL = re.compile(
    r"Calibration:\s*q\s*=\s*([\d.]+);\s*size\s*=\s*(\d+)\s*bytes;"
    r"\s*target\s*=\s*(\d+)\s*bytes;\s*miss\s*=\s*([\d.]+)")
RE_STAGE = re.compile(r"^\s*([\d.]+)\s*ms\s+(\d+)\)\s*(.+?)\s*$", re.M)
RE_SUMMARY = re.compile(
    r"for\s+(\d+)\s+images"
    r"(?:\s+per\s+(\d+)\s+threads?)?"
    r"\s*=\s*([\d.]+)\s*ms;"
    r"(?:\s*([\d.]+)\s*MB/s;)?"
    r"\s*([\d.]+)\s*FPS;")

UNIT_MB = {"GB": 1024.0, "MB": 1.0, "KB": 1.0 / 1024.0}


def boundary_of(text):
    if "excluding host-to-device" in text:
        return "no_h2d"
    if "excluding device-to-host" in text:
        return "no_d2h"
    if "including all transfers" in text:
        return "all"
    return "default"


def parse_output(text):
    out = {}
    m = RE_SDK.search(text)
    if m:
        out["sdk"] = m.group(1)
    m = RE_GPU.search(text)
    if m:
        out["gpu"] = m.group(1)
    m = RE_PCIE.search(text)
    if m:
        out["pcie_mb_s"] = m.group(1)
    m = RE_MEM.search(text)
    if m:
        out["gpu_mem_mb"] = float(m.group(1)) * UNIT_MB[m.group(2)]
    m = RE_AVAIL.search(text)
    if m:
        out["gpu_avail_mb"] = float(m.group(1)) * UNIT_MB[m.group(2)]
    m = RE_SIZE.search(text)
    if m:
        out["out_kb"] = int(m.group(1))
        out["cr"] = float(m.group(2))
    m = RE_CALIB.search(text)
    if m:
        out["calib_q"] = float(m.group(1))
    m = RE_CALIB_FULL.search(text)
    if m:
        out["calib_bytes"] = int(m.group(2))
        out["calib_target"] = int(m.group(3))
        out["calib_miss"] = float(m.group(4))

    best = None
    for line in text.splitlines():
        sm = RE_SUMMARY.search(line)
        if sm:
            best = (line, sm)
    if best:
        line, sm = best
        frames = int(sm.group(1))
        total = float(sm.group(3))
        out["frames"] = frames
        out["total_ms"] = total
        out["ms_per_frame"] = total / frames if frames else 0.0
        out["fps"] = float(sm.group(5))
        out["mb_s"] = sm.group(4) or ""
        out["boundary"] = boundary_of(line)
    return out


# ---------------------------------------------------------------------------
# power draw of the card, sampled while a measurement runs
# ---------------------------------------------------------------------------

RE_TEGRA_POWER = re.compile(r"(VDD_GPU_SOC|GPU_SOC|VDD_GPU)\s+(\d+)mW")


def has_tegrastats():
    return os.path.exists("/usr/bin/tegrastats") or \
        shutil.which("tegrastats") is not None


class TegraPower(object):
    """Same interface as Power, but for Jetson: there is no nvidia-smi there,
    the numbers come from tegrastats. The GPU rail on Orin is VDD_GPU_SOC, so
    the figure includes the memory controller and part of the SoC - it is not
    the same quantity as the board power of a desktop card, and the two must
    not be compared with each other."""

    def __init__(self, device=0, interval_ms=100):
        self.interval_ms = interval_ms
        self.proc = None
        self.samples = []
        self._thread = None
        self.idle_w = None

    def _reader(self):
        for line in self.proc.stdout:
            m = RE_TEGRA_POWER.search(line.decode("ascii", "replace"))
            if m:
                self.samples.append(float(m.group(2)) / 1000.0)

    def start(self):
        self.samples = []
        try:
            self.proc = subprocess.Popen(
                ["tegrastats", "--interval", str(self.interval_ms)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.proc = None
            return
        self._thread = threading.Thread(target=self._reader)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        if not self.proc:
            return None
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2)
        if not self.samples:
            return None
        return sum(self.samples) / len(self.samples)

    def measure_idle(self, seconds=3.0):
        self.start()
        time.sleep(seconds)
        self.idle_w = self.stop()
        return self.idle_w


class EnergyCounter(object):
    """The card's own cumulative energy counter, read through NVML.

    A second meter, independent of the power sampler above. The card counts
    the millijoules it has spent since the driver was loaded, so nothing is
    lost between samples - unlike sampling the power ten times a second, which
    misses short peaks. Needs the nvidia-ml-py package; without it the counter
    is simply reported as unavailable and the run goes on with one meter.
    """

    def __init__(self, device=0):
        self.device = device
        self.handle = None
        self.source = None
        self.error = None
        self._nv = None
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(device)
            pynvml.nvmlDeviceGetTotalEnergyConsumption(handle)   # probe
            self._nv, self.handle = pynvml, handle
            self.source = "NVML cumulative energy counter"
        except Exception as exc:
            self.handle = None
            self.error = str(exc) or exc.__class__.__name__

    @property
    def available(self):
        return self.handle is not None

    def read_j(self):
        """Joules spent by the card since the driver was loaded, or None."""
        if not self.available:
            return None
        try:
            return self._nv.nvmlDeviceGetTotalEnergyConsumption(
                self.handle) / 1000.0
        except Exception:
            return None


class Power(object):
    """Samples GPU power with nvidia-smi in the background."""

    def __init__(self, device=0, interval_ms=100):
        self.device = device
        self.interval_ms = interval_ms
        self.proc = None
        self.samples = []
        self._thread = None
        self.idle_w = None

    def _reader(self):
        for line in self.proc.stdout:
            try:
                self.samples.append(float(line.decode("ascii", "replace")
                                          .strip()))
            except ValueError:
                pass

    def start(self):
        self.samples = []
        try:
            self.proc = subprocess.Popen(
                ["nvidia-smi", "-i", str(self.device),
                 "--query-gpu=power.draw",
                 "--format=csv,noheader,nounits",
                 "-lms", str(self.interval_ms)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.proc = None
            return
        self._thread = threading.Thread(target=self._reader)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        if not self.proc:
            return None
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2)
        if not self.samples:
            return None
        return sum(self.samples) / len(self.samples)

    def measure_idle(self, seconds=3.0):
        self.start()
        time.sleep(seconds)
        self.idle_w = self.stop()
        return self.idle_w


# ---------------------------------------------------------------------------
# processor time actually spent by a child process
# ---------------------------------------------------------------------------

def rusage_children():
    """Cumulative processor time of all finished children, POSIX only."""
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_CHILDREN)
        return r.ru_utime + r.ru_stime
    except Exception:
        return None


def child_cpu_seconds(popen, before=None):
    """User + kernel time of one child process. Immune to other load on the
    machine, unlike system-wide utilisation."""
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
# running one program
# ---------------------------------------------------------------------------

class Bench(object):
    def __init__(self, outdir, dry_run=False):
        self.outdir = outdir
        self.logdir = os.path.join(outdir, "logs")
        self.dry_run = dry_run
        self.rows = []
        os.makedirs(self.logdir, exist_ok=True)

    def run(self, exe, args, log_name, power=None, counter=None):
        # resolve to an absolute path: on Windows a bare name in the current
        # folder works, elsewhere it does not
        if os.path.exists(exe):
            exe = os.path.abspath(exe)
        cmd = [exe] + [str(a) for a in args]
        if self.dry_run:
            print("   would run:", " ".join(cmd))
            # пустой СЛОВАРЬ, а не строка: вызывающий код зовёт r.get(...),
            # и на строке это падало. Ловится только пробным прогоном в папке,
            # где лежат файлы от прошлого боевого запуска.
            return {}
        t0 = time.time()
        cpu_s = None
        cpu_before = rusage_children() if os.name != "nt" else None
        e_before = counter.read_j() if counter else None
        if power:
            power.start()
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            out, _ = p.communicate(timeout=900)
            text = out.decode("utf-8", "replace")
            cpu_s = child_cpu_seconds(p, cpu_before)
        except FileNotFoundError:
            text = "ERROR: %s not found\n" % exe
        except subprocess.TimeoutExpired:
            text = "ERROR: timed out\n"
        wall = time.time() - t0
        avg_w = power.stop() if power else None
        e_after = counter.read_j() if counter else None
        with open(os.path.join(self.logdir, log_name + ".log"), "w",
                  encoding="utf-8") as fh:
            fh.write("$ " + " ".join(cmd) + "\n\n" + text)
        res = parse_output(text)
        res["wall_s"] = wall
        if cpu_s is not None:
            res["cpu_s"] = cpu_s
            if wall > 0:
                res["cores"] = cpu_s / wall
        if avg_w:
            res["power_w"] = avg_w
            frames = res.get("frames") or 0
            if frames:
                res["j_per_frame"] = avg_w * wall / frames
                if power.idle_w:
                    res["j_per_frame_net"] = ((avg_w - power.idle_w) * wall
                                              / frames)
        if e_before is not None and e_after is not None:
            spent = e_after - e_before
            if spent >= 0:
                res["energy_j_counter"] = spent
                frames = res.get("frames") or 0
                if frames:
                    res["j_per_frame_counter"] = spent / frames
        res["cmd"] = " ".join(cmd)
        res["raw"] = text
        return res

    def record(self, **kw):
        kw.setdefault("bench_version", BENCH_VERSION)
        self.rows.append(kw)


# ---------------------------------------------------------------------------
# building the nvJPEG2000 harness
# ---------------------------------------------------------------------------

NV_SOURCE = "nvj2k_bench.cpp"


def _vcvars():
    """Path to vcvars64.bat, or None if Visual Studio cannot be located."""
    pf = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    vswhere = os.path.join(pf, "Microsoft Visual Studio", "Installer",
                           "vswhere.exe")
    if os.path.exists(vswhere):
        try:
            out = subprocess.run([vswhere, "-latest", "-products", "*",
                                  "-requires",
                                  "Microsoft.VisualStudio.Component.VC.Tools."
                                  "x86.x64",
                                  "-property", "installationPath"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=60)
            root = out.stdout.decode("utf-8", "replace").strip().splitlines()
            if root:
                cand = os.path.join(root[0], "VC", "Auxiliary", "Build",
                                    "vcvars64.bat")
                if os.path.exists(cand):
                    return cand
        except Exception:
            pass
    return None


def _cuda_paths():
    cuda = os.environ.get("CUDA_PATH", "")
    inc = os.path.join(cuda, "include")
    lib = os.path.join(cuda, "lib", "x64")
    if not os.path.exists(os.path.join(inc, "nvjpeg2k.h")):
        alt = os.environ.get("NVJPEG2K_PATH", "")
        if alt and os.path.exists(os.path.join(alt, "include", "nvjpeg2k.h")):
            return cuda, os.path.join(alt, "include"), \
                   os.path.join(alt, "lib", "12"), lib
    return cuda, inc, lib, lib


def _posix_cuda_paths():
    """Include and library directories of CUDA and nvJPEG2000 on Linux,
    including Jetson, where everything lives under /usr/local/cuda."""
    roots = [os.environ.get("CUDA_HOME", ""), os.environ.get("CUDA_PATH", ""),
             "/usr/local/cuda"]
    inc, lib = None, []
    for r in roots:
        if r and os.path.exists(os.path.join(r, "include", "cuda_runtime.h")):
            inc = os.path.join(r, "include")
            for sub in ("lib64", "lib", os.path.join("targets",
                                                     "aarch64-linux", "lib")):
                cand = os.path.join(r, sub)
                if os.path.isdir(cand):
                    lib.append(cand)
            break
    nvinc = None
    for cand in [os.path.join(os.environ.get("NVJPEG2K_PATH", ""), "include"),
                 inc, "/usr/include"]:
        if cand and os.path.exists(os.path.join(cand, "nvjpeg2k.h")):
            nvinc = cand
            break
    for cand in [os.path.join(os.environ.get("NVJPEG2K_PATH", ""), "lib"),
                 "/usr/lib/aarch64-linux-gnu", "/usr/lib/x86_64-linux-gnu"]:
        if cand and os.path.isdir(cand):
            lib.append(cand)
    return inc, nvinc, lib


def build_nv_posix(logdir):
    """Same as build_nv, with g++ instead of the Microsoft compiler."""
    targets = [(CODECS["nv"]["enc"], []),
               (CODECS["nv"]["dec"], ["-DBUILD_DECODER"])]
    src_time = os.path.getmtime(NV_SOURCE)
    if all(os.path.exists(t) and os.path.getmtime(t) >= src_time
           for t, _ in targets):
        return "already built and up to date"

    inc, nvinc, libs = _posix_cuda_paths()
    if not inc:
        return ("CUDA not found. Set CUDA_HOME, or install the toolkit into "
                "/usr/local/cuda.")
    if not nvinc:
        return ("nvjpeg2k.h not found. On Jetson install the nvJPEG2000 "
                "package of JetPack, or point NVJPEG2K_PATH at it.")
    cxx = os.environ.get("CXX") or ("g++" if shutil.which("g++") else None)
    if not cxx:
        return "g++ not found, install build-essential"

    for target, extra in targets:
        cmd = [cxx, "-O2", "-std=c++14", "-pthread"] + extra + [
            "-I" + inc, "-I" + nvinc, NV_SOURCE, "-o", target]
        for l in libs:
            cmd += ["-L" + l, "-Wl,-rpath," + l]
        cmd += ["-lnvjpeg2k", "-lcudart"]
        p = subprocess.run(cmd, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=600)
        text = p.stdout.decode("utf-8", "replace")
        with open(os.path.join(logdir, "build_%s.log" % target), "w",
                  encoding="utf-8") as fh:
            fh.write(" ".join(cmd) + "\n\n" + text)
        if not os.path.exists(target):
            return "build of %s failed, see the log" % target
    return "built %s and %s" % (targets[0][0], targets[1][0])


def build_nv(logdir):
    """Build the two nvJPEG2000 executables if they are missing or stale."""
    if os.name != "nt":
        if not os.path.exists(NV_SOURCE):
            return "%s not found, nothing to build" % NV_SOURCE
        return build_nv_posix(logdir)
    if not os.path.exists(NV_SOURCE):
        return "%s not found, nothing to build" % NV_SOURCE

    targets = [(CODECS["nv"]["enc"], []),
               (CODECS["nv"]["dec"], ["/DBUILD_DECODER"])]
    src_time = os.path.getmtime(NV_SOURCE)
    if all(os.path.exists(t) and os.path.getmtime(t) >= src_time
           for t, _ in targets):
        return "already built and up to date"

    cuda, nvinc, nvlib, cudalib = _cuda_paths()
    if not os.path.exists(os.path.join(nvinc, "nvjpeg2k.h")):
        return ("nvjpeg2k.h not found. nvJPEG2000 is distributed separately "
                "from the CUDA Toolkit: install it from the NVIDIA site or via "
                "pip install nvidia-nvjpeg2k-cu12, then point NVJPEG2K_PATH "
                "at it.")

    cl_ready = shutil.which("cl") is not None
    vcvars = None if cl_ready else _vcvars()
    if not cl_ready and not vcvars:
        return ("the Microsoft compiler was not found. Run this from an "
                "'x64 Native Tools Command Prompt for VS', or build "
                "nvj2k_bench.cpp by hand.")

    for target, extra in targets:
        cl = ["cl", "/nologo", "/EHsc", "/O2", "/MD", "/std:c++14"] + extra + [
            '/I%s' % os.path.join(cuda, "include"),
            '/I%s' % nvinc,
            NV_SOURCE,
            "/Fe:" + target,
            "/link",
            "/LIBPATH:%s" % cudalib,
            "/LIBPATH:%s" % nvlib,
            "cudart.lib", "nvjpeg2k.lib"]
        if cl_ready:
            cmd = cl
            shell = False
        else:
            cmd = 'call "%s" >nul && %s' % (vcvars, subprocess.list2cmdline(cl))
            shell = True
        p = subprocess.run(cmd, shell=shell, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=600)
        text = p.stdout.decode("utf-8", "replace")
        with open(os.path.join(logdir, "build_%s.log" % target), "w",
                  encoding="utf-8") as fh:
            fh.write(text)
        if not os.path.exists(target):
            return "build of %s failed, see the log" % target

    for junk in ("nvj2k_bench.obj",):
        if os.path.exists(junk):
            try:
                os.remove(junk)
            except OSError:
                pass
    return "built %s and %s" % (targets[0][0], targets[1][0])


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

def enc_args(codec, image, alg, quality, extra):
    a = ["-i", image, "-o", "tmp.jp2", "-a", alg,
         "-c", CODE_BLOCK, "-l", LEVELS]
    if alg == "irrev":
        a += ["-q", quality]
    return a + extra + ["-discard"]


def dec_args(ref, extra):
    return ["-i", ref, "-o", "tmp.ppm"] + extra + ["-discard"]


def human(seconds):
    m, s = divmod(int(seconds + 0.5), 60)
    return "%d:%02d" % (m, s)


def spread(values):
    """How far apart repeats of the same measurement came out."""
    if len(values) < 2:
        return ""
    m = median(values)
    if not m:
        return ""
    return "(spread %.1f %%)" % (100.0 * (max(values) - min(values)) / m)


def best_point(rows, codec, direction, image, alg):
    """The (threads, batch, fps) of the fastest grid point already measured."""
    acc = {}
    for r in rows:
        if (r.get("mode") != "throughput" or r.get("note")
                or not r.get("fps")):
            continue
        if (r["codec"], r["direction"], r["image"], r["alg"]) != (
                codec, direction, image, alg):
            continue
        acc.setdefault((r["threads"], r["batch"]), []).append(r["fps"])
    if not acc:
        return None
    (th, ba), v = max(acc.items(), key=lambda kv: median(kv[1]))
    return th, ba, median(v)


def median(values):
    v = sorted(values)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def ppm_geometry(path):
    """Width, height and number of components of a binary PPM/PGM."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
    except IOError:
        return None
    if not head.startswith(b"P5") and not head.startswith(b"P6"):
        return None
    comps = 1 if head.startswith(b"P5") else 3
    nums = []
    i = 2
    while len(nums) < 3 and i < len(head):
        ch = head[i:i + 1]
        if ch == b"#":
            while i < len(head) and head[i:i + 1] != b"\n":
                i += 1
        elif ch.isdigit():
            j = i
            while j < len(head) and head[j:j + 1].isdigit():
                j += 1
            nums.append(int(head[i:j]))
            i = j
        else:
            i += 1
    if len(nums) < 2:
        return None
    return {"w": nums[0], "h": nums[1], "comps": comps}


def bits_per_pixel(kb, geom):
    if not kb or not geom:
        return None
    return kb * 1024.0 * 8.0 / (geom["w"] * geom["h"])


def environment(device=0):
    """Everything that has to be published next to the numbers."""
    env = {"date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "os": "%s %s" % (platform.system(), platform.release()),
           "python": platform.python_version(),
           "cpu": platform.processor() or platform.machine()}
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "-i", str(device),
             "--query-gpu=name,driver_version,memory.total,power.limit",
             "--format=csv,noheader"],
            stderr=subprocess.DEVNULL).decode("utf-8", "replace").strip()
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 4:
            env["gpu"] = parts[0]
            env["driver"] = parts[1]
            env["gpu_mem"] = parts[2]
            env["power_limit"] = parts[3]
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["nvidia-smi"], stderr=subprocess.DEVNULL).decode("utf-8", "replace")
        m = re.search(r"CUDA Version:\s*([\d.]+)", out)
        if m:
            env["cuda_driver"] = m.group(1)
    except Exception:
        pass
    if not env.get("gpu"):
        # Jetson: no nvidia-smi there, the details live in other places
        for path, key in (("/proc/device-tree/model", "board"),
                          ("/etc/nv_tegra_release", "jetpack")):
            try:
                with open(path, "rb") as fh:
                    env[key] = fh.read().decode("utf-8", "replace") \
                        .strip("\x00\n ")
            except IOError:
                pass
        for cmd, key in ((["nvpmodel", "-q"], "power_mode"),
                         (["uname", "-m"], "arch")):
            try:
                out = subprocess.check_output(
                    cmd, stderr=subprocess.DEVNULL).decode("utf-8", "replace")
                env[key] = " ".join(out.split())[:80]
            except Exception:
                pass
        if env.get("board"):
            env["gpu"] = env["board"]
    if os.name == "nt":
        try:
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = MEMSTAT()
            st.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            env["ram_gb"] = st.ullTotalPhys / (1024.0 ** 3)
            env["cores"] = os.cpu_count()
        except Exception:
            pass
    else:
        env["cores"] = os.cpu_count()
    return env


def phase_scales(b, geom, dry):
    """Do the two quality scales really correspond to each other?

    On both frames the search landed on the same nvJPEG2000 quality, although
    the frames compress very differently. That is either a property of the two
    scales or a footprint of the search itself: bisection on a fixed interval
    with a loose stop condition lands in the same node no matter where the true
    answer is. The two are told apart cheaply - tighten the tolerance, start
    from a different interval, and repeat at several quality levels.
    """
    rows = []
    for tag, path in IMAGES:
        for q in SCALE_CHECK_Q:
            ref = "fv_scale_%s_q%d.jp2" % (tag, q)
            b.run(CODECS["fv"]["enc"],
                  ["-i", path, "-o", ref, "-a", "irrev", "-c", CODE_BLOCK,
                   "-l", LEVELS, "-q", q, "-info"],
                  "fv_scale_%s_q%d" % (tag, q))
            if dry:
                continue
            if not os.path.exists(ref):
                continue
            target = os.path.getsize(ref)
            row = {"image": tag, "fv_q": q, "target": target}
            for name, lo, hi in (("wide", 1.0, 100.0), ("narrow", 50.0, 99.0)):
                r = b.run(CODECS["nv"]["enc"],
                          ["-i", path, "-targetsize", target,
                           "-c", CODE_BLOCK, "-l", LEVELS,
                           "-tol", SCALE_CHECK_TOL, "-qlo", lo, "-qhi", hi],
                          "nv_scale_%s_q%d_%s" % (tag, q, name))
                row[name] = r.get("calib_q")
                row[name + "_miss"] = r.get("calib_miss")
            try:
                os.remove(ref)
            except OSError:
                pass
            rows.append(row)
            print("   %-3s fv q %-3d  target %8d bytes   wide search %8s   "
                  "narrow %8s"
                  % (tag, q, target,
                     ("%.4f" % row["wide"]) if row.get("wide") else "-",
                     ("%.4f" % row["narrow"]) if row.get("narrow") else "-"))
    return rows


def scales_verdict(rows):
    """Plain words for what the scale check came out with."""
    if not rows:
        return []
    out = []
    drift = [abs(r["wide"] - r["narrow"]) for r in rows
             if r.get("wide") and r.get("narrow")]
    if drift:
        worst = max(drift)
        if worst < 0.05:
            out.append("The starting interval of the search does not change "
                       "the result (difference up to %.3f)." % worst)
        else:
            out.append("The starting interval of the search changes the "
                       "result by up to %.3f - so the value found carries a "
                       "trace of the quality search itself, not only a "
                       "property of the scales." % worst)
    for q in SCALE_CHECK_Q:
        vals = [r["wide"] for r in rows if r["fv_q"] == q and r.get("wide")]
        if len(vals) > 1:
            d = max(vals) - min(vals)
            if d < 0.05:
                out.append("Quality %d: both images gave the same value "
                           "(difference %.3f) - the scales convert into each "
                           "other no matter what the frame is." % (q, d))
            else:
                out.append("Quality %d: the values differ by %.3f - the "
                           "correspondence between the scales depends on the "
                           "frame, there is no constant conversion." % (q, d))
    return out


def phase_stages(b, codecs, quality, dry, runs=5):
    """Where the time goes inside one frame.

    Taken on single frames with -info: that key inserts synchronisations
    between the stages, so the total comes out higher than a real run - the
    breakdown may be read as shares, never as a sum. Several runs, median per
    stage: on one frame the spread reaches thirteen per cent.
    """
    out = {}
    for c in codecs:
        for tag, path in IMAGES:
            ref = "%s_ref_%s_irrev.jp2" % (c, tag)
            jobs = (("E", CODECS[c]["enc"],
                     ["-i", path, "-o", "tmp.jp2", "-a", "irrev",
                      "-c", CODE_BLOCK, "-l", LEVELS,
                      "-q", quality[(c, tag)], "-info"]),
                    ("D", CODECS[c]["dec"],
                     ["-i", ref, "-o", "tmp.ppm", "-info"]))
            for d, exe, a in jobs:
                acc = {}
                order = []
                for i in range(runs):
                    r = b.run(exe, a, "%s_stages_%s_%s_%d" % (c, d, tag, i))
                    if dry:
                        break
                    for ms, _, name in RE_STAGE.findall(r.get("raw", "")):
                        name = re.sub(r"\s*\(.*\)\s*$", "", name)
                        if name not in acc:
                            acc[name] = []
                            order.append(name)
                        acc[name].append(float(ms))
                if dry or not acc:
                    continue
                stages = [(n, median(acc[n])) for n in order]
                total = sum(v for _, v in stages) or 1.0
                out[(c, d, tag)] = [(n, v, 100.0 * v / total)
                                    for n, v in stages]
                top = ", ".join("%s %.0f %%" % (n, s) for n, _, s
                                in sorted(out[(c, d, tag)],
                                          key=lambda x: -x[2])[:3])
                print("   %-2s %-3s %s  %s" % (c, tag, d, top))
    return out


def phase_noupload(b, quality, best_point, dry):
    """How much of the nvJPEG2000 encoder time is the per-frame upload.

    The library shows almost no gain from threads. This check separates our
    harness from the library: with -noupload the pixels are put on the card
    once and the loop only encodes.
    """
    rows = []
    th, ba = best_point
    for tag, path in IMAGES:
        base = ["-i", path, "-o", "tmp.jp2", "-a", "irrev",
                "-c", CODE_BLOCK, "-l", LEVELS, "-q", quality[("nv", tag)],
                "-repeat", 400, "-async", "-thread", th, "-b", ba, "-discard"]
        r1 = b.run(CODECS["nv"]["enc"], base, "nv_noupload_off_%s" % tag)
        r2 = b.run(CODECS["nv"]["enc"], base + ["-noupload"],
                   "nv_noupload_on_%s" % tag)
        if dry:
            continue
        a, c_ = r1.get("fps"), r2.get("fps")
        rows.append({"image": tag, "with_upload": a, "without": c_,
                     "gain": (100.0 * (c_ / a - 1.0)) if (a and c_) else None})
        print("   %-3s  with upload %7.1f fps   without upload %7.1f fps  %s"
              % (tag, a or 0, c_ or 0,
                 ("+%.0f %%" % rows[-1]["gain"]) if rows[-1]["gain"] else ""))
    return rows


def phase_subsampling(b, quality, speed, per_run, power, dry, baseline=None):
    """Reference points for chroma subsampling, Fastvideo codec only.

    nvJPEG2000 takes components that are already subsampled, so on that side
    the downsampling would happen outside the codec and the comparison would
    measure a resampling filter rather than either codec.
    """
    rows = []
    exe_e = CODECS["fv"]["enc"]
    exe_d = CODECS["fv"]["dec"]
    for tag, path in IMAGES:
        for s in SUBSAMPLING:
            q = quality[("fv", tag)]
            ref = "fv_sub_%s_%s.jp2" % (tag, s)
            common = ["-a", "irrev", "-c", CODE_BLOCK, "-l", LEVELS,
                      "-q", q, "-s", s]
            r0 = b.run(exe_e, ["-i", path, "-o", ref] + common + ["-info"],
                       "fv_sub_prep_%s_%s" % (tag, s))
            if dry:
                continue
            base = speed.get(("fv", "E", tag, "irrev"), 200.0)
            n_lat = max(20, int(base * per_run / 4.0))
            n_thr = max(20, int(base * per_run))
            th, ba = PROBE_POINT

            rl = b.run(exe_e, ["-i", path, "-o", "tmp.jp2"] + common +
                       ["-repeat", n_lat, "-discard"],
                       "fv_sub_E_%s_%s_L2" % (tag, s), power=power)
            rt = b.run(exe_e, ["-i", path, "-o", "tmp.jp2"] + common +
                       ["-repeat", n_thr, "-async", "-thread", th, "-b", ba,
                        "-discard"],
                       "fv_sub_E_%s_%s_t%db%d" % (tag, s, th, ba), power=power)
            base_d = speed.get(("fv", "D", tag, "irrev"), 200.0)
            rd = b.run(exe_d, dec_args(ref, ["-repeat",
                                             max(20, int(base_d * per_run
                                                         / 4.0))]),
                       "fv_sub_D_%s_%s_L2" % (tag, s), power=power)

            out = "check_sub_%s_%s.ppm" % (tag, s)
            b.run(exe_d, ["-i", ref, "-o", out],
                  "fv_sub_check_%s_%s" % (tag, s))
            src = (baseline or {}).get(("fv", tag), path)
            qual = compare_images(src, out) if os.path.exists(out) \
                else {"kind": "no output file"}
            try:
                os.remove(out)
            except OSError:
                pass

            for r, mode, thb in ((rl, "latency", (1, 1)),
                                 (rt, "throughput", (th, ba))):
                b.record(codec="fv", direction="E", image=tag, alg="irrev",
                         mode=mode, threads=thb[0], batch=thb[1],
                         note="sub " + s, **r)
            b.record(codec="fv", direction="D", image=tag, alg="irrev",
                     mode="latency", threads=1, batch=1, note="sub " + s, **rd)

            row = {"image": tag, "sub": s, "kb": r0.get("out_kb"),
                   "cr": r0.get("cr"), "enc_lat": rl.get("fps"),
                   "enc_thr": rt.get("fps"), "dec_lat": rd.get("fps"),
                   "psnr": qual.get("psnr"), "kind": qual.get("kind")}
            rows.append(row)
            print("   %-3s %-4s  %6s KB  %6s:1  enc %7.1f / %7.1f fps  "
                  "dec %7.1f fps  PSNR %s"
                  % (tag, s, row["kb"] or "?", row["cr"] or "?",
                     row["enc_lat"] or 0, row["enc_thr"] or 0,
                     row["dec_lat"] or 0,
                     ("%.1f" % row["psnr"]) if row.get("psnr") else "-"))
    return rows


def phase_ratios(b, codecs, speed, per_run, power, dry):
    """The same comparison at several compression ratios.

    Decoding time follows the number of coding passes in the stream, not the
    size of the file, so one ratio is one point on a curve and not the curve.
    Fastvideo reaches a given ratio with rate control (-cr, PCRD); nvJPEG2000
    has no such knob, so its quality is bisected onto the resulting size.
    """
    rows = []
    for tag, path in IMAGES:
        for ratio in RATIOS:
            row = {"image": tag, "ratio": ratio}
            ref = {}
            fv_ref = "fv_cr%d_%s.jp2" % (int(ratio), tag)
            r0 = b.run(CODECS["fv"]["enc"],
                       ["-i", path, "-o", fv_ref, "-a", "irrev",
                        "-c", CODE_BLOCK, "-l", LEVELS, "-cr", ratio, "-info"],
                       "fv_cr%d_prep_%s" % (int(ratio), tag))
            if dry:
                continue
            row["fv_kb"] = r0.get("out_kb")
            ref["fv"] = fv_ref
            fv_extra = ["-cr", ratio]
            nv_q = None
            if "nv" in codecs and row["fv_kb"]:
                rc = b.run(CODECS["nv"]["enc"],
                           ["-i", path, "-targetsize", row["fv_kb"] * 1024,
                            "-c", CODE_BLOCK, "-l", LEVELS],
                           "nv_cr%d_calib_%s" % (int(ratio), tag))
                nv_q = rc.get("calib_q")
                if nv_q:
                    nv_ref = "nv_cr%d_%s.jp2" % (int(ratio), tag)
                    rn = b.run(CODECS["nv"]["enc"],
                               ["-i", path, "-o", nv_ref, "-a", "irrev",
                                "-c", CODE_BLOCK, "-l", LEVELS,
                                "-q", nv_q, "-info"],
                               "nv_cr%d_prep_%s" % (int(ratio), tag))
                    row["nv_kb"] = rn.get("out_kb")
                    row["nv_q"] = nv_q
                    ref["nv"] = nv_ref

            for c in codecs:
                if c not in ref:
                    continue
                extra = fv_extra if c == "fv" else ["-q", nv_q]
                base_e = speed.get((c, "E", tag, "irrev"), 200.0)
                base_d = speed.get((c, "D", tag, "irrev"), 200.0)
                ne = max(20, int(base_e * per_run / 4.0))
                nd = max(20, int(base_d * per_run / 4.0))
                re_ = b.run(CODECS[c]["enc"],
                            ["-i", path, "-o", "tmp.jp2", "-a", "irrev",
                             "-c", CODE_BLOCK, "-l", LEVELS] + extra +
                            ["-repeat", ne, "-discard"],
                            "%s_cr%d_E_%s" % (c, int(ratio), tag), power=power)
                rd_ = b.run(CODECS[c]["dec"], dec_args(ref[c], ["-repeat", nd]),
                            "%s_cr%d_D_%s" % (c, int(ratio), tag), power=power)
                row[c + "_enc"] = re_.get("fps")
                row[c + "_dec"] = rd_.get("fps")
                for r, d in ((re_, "E"), (rd_, "D")):
                    b.record(codec=c, direction=d, image=tag, alg="irrev",
                             mode="latency", threads=1, batch=1,
                             note="cr %g" % ratio, **r)
            rows.append(row)
            print("   %-3s %5.1f:1  fv %6s KB  nv %6s KB (q %s)  "
                  "enc %7.1f / %7.1f  dec %7.1f / %7.1f"
                  % (tag, ratio, row.get("fv_kb") or "?",
                     row.get("nv_kb") or "?",
                     ("%.2f" % row["nv_q"]) if row.get("nv_q") else "-",
                     row.get("fv_enc") or 0, row.get("nv_enc") or 0,
                     row.get("fv_dec") or 0, row.get("nv_dec") or 0))
    return rows


def phase_energy(b, codecs, quality, power, counter):
    """Energy of one frame by two meters, with the differential method.

    Energy of one frame is not simply "power times time divided by frames":
    a run also pays for starting the process, filling the buffers and the
    card's own idle draw, and none of that depends on how many frames were
    coded. So the same point is measured twice, on N and on 2N frames, and
    the energy of one frame is the difference divided by N - everything that
    does not scale with the number of frames cancels out.

    Two meters run at once: the card's cumulative counter (nothing is lost
    between samples) and the older power sampler. Their disagreement is a
    result in itself, so it is printed.
    """
    energy = []
    for c in codecs:
        for tag, path in IMAGES:
            for alg in ALGS:
                ref = "%s_ref_%s_%s.jp2" % (c, tag, alg)
                for d in ("E", "D"):
                    pt = best_point(b.rows, c, d, tag, alg)
                    if not pt:
                        continue
                    th, ba, fps = pt
                    n1 = max(20, int(fps * ENERGY_RUN_S))
                    if d == "E":
                        exe = CODECS[c]["enc"]

                        def mk(nn, th=th, ba=ba, path=path, alg=alg, c=c):
                            return enc_args(c, path, alg,
                                            quality[(c, tag)],
                                            ["-repeat", nn, "-async",
                                             "-thread", th, "-b", ba])
                    else:
                        exe = CODECS[c]["dec"]

                        def mk(nn, th=th, ba=ba, ref=ref):
                            return dec_args(ref, ["-repeat", nn, "-async",
                                                  "-thread", th, "-b", ba])
                    pair = []
                    for mult in (1, 2):
                        nn = n1 * mult
                        r = b.run(exe, mk(nn),
                                  "%s_%s_%s_%s_energy_%dn"
                                  % (c, d, tag, alg, mult),
                                  power=power, counter=counter)
                        b.record(codec=c, direction=d, image=tag, alg=alg,
                                 mode="energy", threads=th, batch=ba,
                                 note="%dn" % mult, **r)
                        pair.append(r)
                    r1, r2 = pair
                    f1 = r1.get("frames") or n1
                    f2 = r2.get("frames") or (2 * n1)
                    e1 = r1.get("energy_j_counter")
                    e2 = r2.get("energy_j_counter")
                    diff = None
                    if (e1 is not None and e2 is not None
                            and f2 > f1 and e2 > e1):
                        diff = (e2 - e1) / (f2 - f1)
                        r2["j_per_frame_diff"] = diff
                    row = {"codec": c, "direction": d, "image": tag,
                           "alg": alg, "threads": th, "batch": ba,
                           "frames_n": f1, "frames_2n": f2,
                           "j_per_frame_diff": diff,
                           "j_per_frame_counter":
                               r2.get("j_per_frame_counter"),
                           "j_per_frame_sampled": r2.get("j_per_frame"),
                           "j_per_frame_sampled_net":
                               r2.get("j_per_frame_net"),
                           "cores": r2.get("cores"),
                           "fps": r2.get("fps")}
                    energy.append(row)
                    print("   %-2s %-3s %-5s %s %2dx%-2d  counter %s  "
                          "sampled %s"
                          % (c, tag, alg, d, th, ba,
                             ("%.3f" % diff) if diff else "   -  ",
                             ("%.3f" % row["j_per_frame_sampled"])
                             if row["j_per_frame_sampled"] else "   -  "))
    return energy


def selftest(device=0):
    """Checks the file itself and both energy meters. Measures nothing,
    needs no codec and no card: a few seconds to see that the file runs and
    to learn whether the second meter will be there during the real run."""
    print("=" * 62)
    print(" bench-04.py, version %s - selftest" % BENCH_VERSION)
    print("=" * 62)
    print(" python:   %s" % platform.python_version())
    print(" platform: %s" % platform.platform())

    # 1. the arithmetic of the differential method
    n1, n2 = 100, 200
    e1, e2 = 12.0, 20.0          # joules: 4 J fixed cost + 0.08 J per frame
    per_frame = (e2 - e1) / (n2 - n1)
    assert abs(per_frame - 0.08) < 1e-9, "differential arithmetic is wrong"
    naive = e2 / n2
    print("\n differential method on a made-up example:")
    print("   %d frames -> %.1f J, %d frames -> %.1f J" % (n1, e1, n2, e2))
    print("   per frame, difference: %.4f J   (correct)" % per_frame)
    print("   per frame, naive:      %.4f J   (%.0f %% too high: it still"
          % (naive, 100.0 * (naive / per_frame - 1.0)))
    print("   carries the fixed cost of the run)")

    # 2. picking the best grid point out of recorded rows
    rows = [{"codec": "fv", "direction": "E", "image": "2k", "alg": "irrev",
             "mode": "throughput", "threads": t, "batch": bb, "fps": f}
            for t, bb, f in ((8, 1, 1000.0), (8, 2, 1800.0), (16, 2, 1600.0))]
    got = best_point(rows, "fv", "E", "2k", "irrev")
    assert got == (8, 2, 1800.0), "best point picked wrong: %r" % (got,)
    print("\n best grid point out of three: %dx%d, %.0f fps - correct"
          % got)

    # 3. the counter
    counter = EnergyCounter(device)
    print("\n energy counter (NVML):")
    if counter.available:
        a = counter.read_j()
        time.sleep(1.0)
        bj = counter.read_j()
        print("   available: %s" % counter.source)
        print("   reading:   %.1f J, one second later %.1f J (%+.2f J)"
              % (a, bj, bj - a))
        if bj == a:
            print("   WARNING: the counter did not move in a second")
    else:
        print("   NOT available: %s" % (counter.error or "unknown reason"))
        print("   install it with:  pip install nvidia-ml-py")
        print("   the run will still work, with one meter instead of two")

    # 4. the power sampler
    print("\n power sampling (nvidia-smi):")
    if has_tegrastats():
        print("   Jetson board: tegrastats will be used")
    elif shutil.which("nvidia-smi"):
        pw = Power(device)
        idle = pw.measure_idle(2.0)
        print("   idle draw: %s"
              % (("%.0f W" % idle) if idle else "no reading"))
    else:
        print("   nvidia-smi not found - no power sampling on this machine")

    print("\n selftest finished, nothing was measured.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=600.0,
                    help="time budget in seconds, default 600")
    ap.add_argument("--codec", choices=["fv", "nv", "both"], default="both")
    ap.add_argument("--no-build", action="store_true",
                    help="never invoke the compiler")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--device", type=int, default=0)
    ap.add_argument("--no-sub", action="store_true",
                    help="skip the chroma subsampling reference points")
    ap.add_argument("--ratios", action="store_true",
                    help="also sweep the compression ratio (adds a few minutes)")
    ap.add_argument("--reps", type=int, default=1,
                    help="how many times every measurement is repeated")
    ap.add_argument("--label", default="",
                    help="suffix for the output folder, e.g. the power mode "
                         "on Jetson: --label 15W")
    ap.add_argument("--no-energy", action="store_true",
                    help="skip the separate energy phase (two meters, "
                         "N and 2N frames)")
    ap.add_argument("--selftest", action="store_true",
                    help="check the file and the energy meters and exit; "
                         "measures nothing, needs no card")
    ap.add_argument("--final", action="store_true",
                    help="the run the article is written from: everything on, "
                         "three repeats, half an hour")
    args = ap.parse_args()

    if args.selftest:
        return selftest(args.device)

    if args.final:
        args.ratios = True
        args.no_sub = False
        if args.reps < 3:
            args.reps = 3
        if args.budget <= 600.0:
            args.budget = 1800.0
    reps = max(1, args.reps)

    codecs = ["fv", "nv"] if args.codec == "both" else [args.codec]

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = "cmp_" + stamp + (("_" + args.label) if args.label else "")
    b = Bench(outdir, args.dry_run)

    print("=" * 62)
    print(" JPEG2000 comparison")
    print(" codecs: " + ", ".join(CODECS[c]["name"] for c in codecs))
    print(" output: " + outdir)
    print(" budget: " + human(args.budget) + ("  (final run)" if args.final
                                              else ""))
    print(" repeats: %d" % reps)
    print("=" * 62)

    env = environment(args.device) if not args.dry_run else {}
    geom = {}
    for tag, path in IMAGES:
        g = ppm_geometry(path)
        if g:
            geom[tag] = g

    # --- 0. build the nvJPEG2000 harness if needed -----------------------
    if "nv" in codecs and not args.dry_run and not args.no_build:
        print("\n[0] nvJPEG2000 harness")
        print("   " + build_nv(b.logdir))

    missing = []
    for c in codecs:
        for role in ("enc", "dec"):
            exe = CODECS[c][role]
            if not (os.path.exists(exe) or args.dry_run):
                missing.append(exe)
    if missing:
        print("\nNot found in this folder: " + ", ".join(missing))
        print("Put the script next to the sample programs and the test images.")
        return 1
    for tag, path in IMAGES:
        if not (os.path.exists(path) or args.dry_run):
            print("\nTest image not found: " + path)
            return 1

    # quality knob per codec and per image: the scales are different, and the
    # value that matches our file size differs from image to image
    power = TegraPower(args.device) if has_tegrastats() else Power(args.device)
    counter = EnergyCounter(args.device)
    if not args.dry_run:
        idle = power.measure_idle(3.0)
        if idle:
            print("\n   the card's idle draw: %.0f W" % idle)
        if counter.available:
            print("   second energy meter: " + counter.source)
        else:
            print("   second energy meter unavailable (%s)"
                  % (counter.error or "no NVML"))
            print("   install it with:  pip install nvidia-ml-py")

    quality = {}
    for c in codecs:
        for tag, _ in IMAGES:
            quality[(c, tag)] = FV_QUALITY

    # --- 1a. the quality ladder of the Fastvideo codec --------------------
    ladder = []
    if "fv" in codecs:
        print("\n[1a] quality ladder, Fastvideo codec")
        for q in QUALITY_LADDER:
            row = {"q": q}
            for tag, path in IMAGES:
                out = "fv_ladder_%s_q%d.jp2" % (tag, q)
                r = b.run(CODECS["fv"]["enc"],
                          ["-i", path, "-o", out, "-a", "irrev",
                           "-c", CODE_BLOCK, "-l", LEVELS, "-q", q, "-info"],
                          "fv_ladder_%s_q%d" % (tag, q))
                if args.dry_run:
                    continue
                row[tag + "_kb"] = r.get("out_kb")
                row[tag + "_cr"] = r.get("cr")
                row[tag + "_bpp"] = bits_per_pixel(r.get("out_kb"),
                                                   geom.get(tag))
                try:
                    os.remove(out)
                except OSError:
                    pass
            if args.dry_run:
                continue
            ladder.append(row)
            print("   q %-3d  2K %6s KB %6s:1   4K %6s KB %6s:1"
                  % (q, row.get("2k_kb") or "?", row.get("2k_cr") or "?",
                     row.get("4k_kb") or "?", row.get("4k_cr") or "?"))

    # --- 1b. reference streams, and the size each codec must match --------
    print("\n[1b] reference streams")
    ref_size = {}
    ref_bytes = {}
    for c in codecs:
        for tag, path in IMAGES:
            for alg in ALGS:
                ref = "%s_ref_%s_%s.jp2" % (c, tag, alg)
                a = ["-i", path, "-o", ref, "-a", alg,
                     "-c", CODE_BLOCK, "-l", LEVELS, "-info"]
                if alg == "irrev":
                    a += ["-q", quality[(c, tag)]]
                r = b.run(CODECS[c]["enc"], a, "%s_prep_%s_%s" % (c, tag, alg))
                if args.dry_run:
                    continue
                kb = r.get("out_kb")
                cr = r.get("cr")
                ref_size[(c, tag, alg)] = kb
                if os.path.exists(ref):
                    ref_bytes[(c, tag, alg)] = os.path.getsize(ref)
                bpp = bits_per_pixel(kb, geom.get(tag))
                print("   %-2s %-3s %-5s  %6s KB  %5s:1  %s bit/pixel"
                      % (c, tag, alg, kb if kb else "?", cr if cr else "?",
                         ("%.2f" % bpp) if bpp else "?"))

    # --- 2. match the compressed size between the codecs -----------------
    calib = []
    if "fv" in codecs and "nv" in codecs and not args.dry_run:
        print("\n[2] matching the compressed size")
        for tag, path in IMAGES:
            target = ref_bytes.get(("fv", tag, "irrev"))
            if not target:
                kb = ref_size.get(("fv", tag, "irrev"))
                target = kb * 1024 if kb else None
            if not target:
                continue
            r = b.run(CODECS["nv"]["enc"],
                      ["-i", path, "-targetsize", target,
                       "-c", CODE_BLOCK, "-l", LEVELS, "-tol", CALIB_TOL],
                      "nv_calib_%s" % tag)
            q = r.get("calib_q")
            if q:
                quality[("nv", tag)] = q
                calib.append({"image": tag, "target": target, "q": q,
                              "got": r.get("calib_bytes"),
                              "miss": r.get("calib_miss")})
                print("   %-3s target %d bytes -> q %.2f gives %s bytes "
                      "(miss %s %%)"
                      % (tag, target, q, r.get("calib_bytes") or "?",
                         ("%.2f" % r["calib_miss"])
                         if r.get("calib_miss") is not None else "?"))
                # re-make the lossy reference at the matched quality
                ref = "nv_ref_%s_irrev.jp2" % tag
                rr = b.run(CODECS["nv"]["enc"],
                           ["-i", path, "-o", ref, "-a", "irrev",
                            "-c", CODE_BLOCK, "-l", LEVELS, "-q", q, "-info"],
                           "nv_prep_%s_irrev" % tag)
                if rr.get("out_kb"):
                    ref_size[("nv", tag, "irrev")] = rr["out_kb"]
                if os.path.exists(ref):
                    ref_bytes[("nv", tag, "irrev")] = os.path.getsize(ref)
            else:
                print("   %-3s calibration produced nothing, keeping q %s"
                      % (tag, quality[("nv", tag)]))
    else:
        print("\n[2] size matching skipped (one codec only)")

    # --- 3. probe: how fast is each workload, and how much memory --------
    print("\n[3] probing speed and memory")
    speed = {}
    mem_slot = {}
    avail = {}
    T, B_ = PROBE_POINT
    for c in codecs:
        for tag, path in IMAGES:
            for alg in ALGS:
                ref = "%s_ref_%s_%s.jp2" % (c, tag, alg)
                extra = ["-repeat", PROBE_FRAMES, "-async",
                         "-thread", T, "-b", B_]
                re_ = b.run(CODECS[c]["enc"],
                            enc_args(c, path, alg, quality[(c, tag)], extra),
                            "%s_probe_E_%s_%s" % (c, tag, alg))
                rd = b.run(CODECS[c]["dec"], dec_args(ref, extra),
                           "%s_probe_D_%s_%s" % (c, tag, alg))
                if args.dry_run:
                    continue
                for d, r in (("E", re_), ("D", rd)):
                    fps = r.get("fps", 0.0)
                    speed[(c, d, tag, alg)] = fps if fps else 1.0
                    if r.get("gpu_mem_mb"):
                        mem_slot[(c, d, tag, alg)] = r["gpu_mem_mb"] / (T * B_)
                    if r.get("gpu_avail_mb"):
                        avail[c] = min(avail.get(c, 1e12), r["gpu_avail_mb"])
                print("   %-2s %-3s %-5s  encode %7.1f fps   decode %7.1f fps"
                      % (c, tag, alg,
                         speed.get((c, "E", tag, alg), 0),
                         speed.get((c, "D", tag, alg), 0)))

    # --- how long may one measurement take -------------------------------
    n_runs = (len(codecs) * len(IMAGES) * len(ALGS) * 2
              * (1 + len(POINTS)) * reps)
    if "fv" in codecs and not args.no_sub:
        n_runs += len(IMAGES) * len(SUBSAMPLING) * 3
    if args.ratios and "fv" in codecs:
        n_runs += len(IMAGES) * len(RATIOS) * 2 * len(codecs)
    left = args.budget - (time.time() - START)
    per_run = (left / max(n_runs, 1)) - STARTUP_S
    per_run = max(MIN_RUN_S, min(MAX_RUN_S, per_run))
    print("\n   %d measurements left, %.1f s each -> about %s"
          % (n_runs, per_run, human(n_runs * (per_run + STARTUP_S))))

    # --- 4. measure -------------------------------------------------------
    print("\n[4] measuring")
    for c in codecs:
        for tag, path in IMAGES:
            for alg in ALGS:
                ref = "%s_ref_%s_%s.jp2" % (c, tag, alg)

                def frames(direction, div=1.0):
                    fps = speed.get((c, direction, tag, alg), 100.0)
                    return max(20, int(fps * per_run / div))

                # latency: synchronous, no overlap
                for d, exe, mk in (("E", CODECS[c]["enc"],
                                    lambda n: enc_args(c, path, alg,
                                                       quality[(c, tag)],
                                                       ["-repeat", n])),
                                   ("D", CODECS[c]["dec"],
                                    lambda n: dec_args(ref, ["-repeat", n]))):
                    n = frames(d, div=4.0)     # sync is several times slower
                    got = []
                    for rep in range(1, reps + 1):
                        r = b.run(exe, mk(n),
                                  "%s_%s_%s_%s_L2_r%d" % (c, d, tag, alg, rep),
                                  power=power)
                        if not args.dry_run:
                            b.record(codec=c, direction=d, image=tag, alg=alg,
                                     mode="latency", threads=1, batch=1, **r)
                            if r.get("fps"):
                                got.append(r["fps"])
                    print("   %-2s %-3s %-5s %s single         %8.1f fps %s"
                          % (c, tag, alg, d, median(got) or 0, spread(got)))

                # throughput: the grid, skipping what does not fit
                for (th, ba) in POINTS:
                    for d, exe, mk in (("E", CODECS[c]["enc"],
                                        lambda n, th=th, ba=ba:
                                        enc_args(c, path, alg,
                                                 quality[(c, tag)],
                                                 ["-repeat", n, "-async",
                                                  "-thread", th, "-b", ba])),
                                       ("D", CODECS[c]["dec"],
                                        lambda n, th=th, ba=ba:
                                        dec_args(ref, ["-repeat", n, "-async",
                                                       "-thread", th,
                                                       "-b", ba]))):
                        need = mem_slot.get((c, d, tag, alg), 0.0) * th * ba
                        have = avail.get(c, 0.0)
                        if need and have and need > 0.9 * have:
                            print("   %-2s %-3s %-5s %s %2dx%-2d  skipped, "
                                  "needs %.0f MB of %.0f MB"
                                  % (c, tag, alg, d, th, ba, need, have))
                            continue
                        n = frames(d)
                        got = []
                        for rep in range(1, reps + 1):
                            r = b.run(exe, mk(n),
                                      "%s_%s_%s_%s_t%d_b%d_r%d"
                                      % (c, d, tag, alg, th, ba, rep),
                                      power=power)
                            if not args.dry_run:
                                b.record(codec=c, direction=d, image=tag,
                                         alg=alg, mode="throughput",
                                         threads=th, batch=ba, **r)
                                if r.get("fps"):
                                    got.append(r["fps"])
                        print("   %-2s %-3s %-5s %s %2dx%-2d          %8.1f fps"
                              " %s"
                              % (c, tag, alg, d, th, ba, median(got) or 0,
                                 spread(got)))

    # --- 4b. energy: two meters, N and 2N frames --------------------------
    if args.dry_run or args.no_energy:
        energy = []
    else:
        print("\n[4b] energy: two meters, N and 2N frames")
        energy = phase_energy(b, codecs, quality, power, counter)

    # --- 5. does the decoder really produce the picture -------------------
    #
    # A demo build draws a watermark on the frame BEFORE encoding. Comparing a
    # decoded frame with the original file would then measure the watermark and
    # not the codec. The way out: the reference for the lossy check is the
    # frame that came back through the LOSSLESS round trip on the same build.
    # Lossless keeps every bit, so that frame is exactly what the encoder was
    # given, watermark included - and PSNR then measures the loss of lossy
    # coding alone. This only holds if the watermark is applied the same way
    # every run, so the script checks that first: two independent lossless
    # round trips must come out byte for byte identical.
    print("\n[5] round trip: encode, decode, compare with the source")
    checks = []
    watermark = []
    baseline = {}
    for c in codecs:
        for tag, path in IMAGES:
            ref_rev = "%s_ref_%s_rev.jp2" % (c, tag)
            first = "base_%s_%s.ppm" % (c, tag)
            second = "base2_%s_%s.ppm" % (c, tag)
            b.run(CODECS[c]["dec"], ["-i", ref_rev, "-o", first],
                  "%s_base_%s_1" % (c, tag))
            # a second, independent pass through the whole chain
            again = "again_%s_%s.jp2" % (c, tag)
            b.run(CODECS[c]["enc"],
                  ["-i", path, "-o", again, "-a", "rev",
                   "-c", CODE_BLOCK, "-l", LEVELS],
                  "%s_base_%s_enc2" % (c, tag))
            b.run(CODECS[c]["dec"], ["-i", again, "-o", second],
                  "%s_base_%s_2" % (c, tag))
            if args.dry_run:
                continue
            info = {"codec": c, "image": tag}
            if os.path.exists(first) and os.path.exists(second):
                same = compare_images(first, second)
                info["stable"] = (same.get("kind") == "exact")
                vs_src = compare_images(path, first)
                info["vs_source"] = vs_src
                info["has_mark"] = (vs_src.get("kind") != "exact")
                if info["has_mark"] and info["stable"]:
                    baseline[(c, tag)] = first
                elif not info["has_mark"]:
                    baseline[(c, tag)] = path
            else:
                info["stable"] = None
            for junk in (second, again):
                try:
                    os.remove(junk)
                except OSError:
                    pass
            watermark.append(info)
            if info.get("has_mark"):
                print("   %-2s %-3s  the frame carries a watermark, applied "
                      "%s"
                      % (c, tag, "the same way every run" if info["stable"]
                         else "DIFFERENTLY every run"))
            else:
                print("   %-2s %-3s  lossless round trip matches the original"
                      % (c, tag))

    for c in codecs:
        for tag, path in IMAGES:
            for alg in ALGS:
                ref = "%s_ref_%s_%s.jp2" % (c, tag, alg)
                out = "check_%s_%s_%s.ppm" % (c, tag, alg)
                b.run(CODECS[c]["dec"], ["-i", ref, "-o", out],
                      "%s_check_%s_%s" % (c, tag, alg))
                if os.path.exists(out):
                    q = compare_images(path, out)
                    base = baseline.get((c, tag))
                    if base and base != path and alg == "irrev":
                        q2 = compare_images(base, out)
                        q["psnr_vs_base"] = q2.get("psnr")
                        q["base"] = "lossless round trip"
                    try:
                        os.remove(out)
                    except OSError:
                        pass
                else:
                    q = {"kind": "no output file"}
                checks.append((c, tag, alg, q))
                print("   %-2s %-3s %-5s  %s" % (c, tag, alg, describe(q)))


    # --- 6. cross decode: each decoder on the other codec's stream --------
    cross = []
    if len(codecs) == 2:
        print("\n[6] cross decode")
        other = {codecs[0]: codecs[1], codecs[1]: codecs[0]}
        for c in codecs:
            for tag, path in IMAGES:
                for alg in ALGS:
                    ref = "%s_ref_%s_%s.jp2" % (other[c], tag, alg)
                    if not os.path.exists(ref):
                        continue
                    fps = speed.get((c, "D", tag, alg), 100.0)
                    n = max(20, int(fps * per_run / 4.0))
                    r = b.run(CODECS[c]["dec"],
                              dec_args(ref, ["-repeat", n]),
                              "%s_cross_%s_%s" % (c, tag, alg))
                    own = None
                    for row in b.rows:
                        if (row["codec"] == c and row["direction"] == "D"
                                and row["image"] == tag and row["alg"] == alg
                                and row["mode"] == "latency"):
                            own = row.get("fps")
                    cross.append((c, tag, alg, own, r.get("fps")))
                    print("   %-2s decoder on %s stream, %-3s %-5s  "
                          "own %7.1f  other %7.1f fps"
                          % (c, CODECS[other[c]]["name"], tag, alg,
                             own or 0, r.get("fps") or 0))

    # --- 7. chroma subsampling, Fastvideo codec only ----------------------
    subs = []
    if "fv" in codecs and not args.no_sub:
        print("\n[7] chroma subsampling, Fastvideo codec only")
        subs = phase_subsampling(b, quality, speed, per_run, power,
                                 args.dry_run, baseline)

    # --- 8. the same comparison at several compression ratios -------------
    ratios = []
    if args.ratios and "fv" in codecs:
        print("\n[8] compression ratio sweep")
        ratios = phase_ratios(b, codecs, speed, per_run, power, args.dry_run)

    # --- 8b. do the two quality scales really correspond ------------------
    scales = []
    if len(codecs) == 2:
        print("\n[9] check that the two quality scales correspond")
        scales = phase_scales(b, geom, args.dry_run)
        for line in scales_verdict(scales):
            for piece in textwrap.wrap(line, 74):
                print("   " + piece)

    # --- 9. where the time goes inside one frame --------------------------
    print("\n[10] stage breakdown (single frames, -info)")
    stages = phase_stages(b, codecs, quality, args.dry_run)

    # --- 10. is the flat scaling of the nv encoder ours or theirs ---------
    noupload = []
    if "nv" in codecs:
        print("\n[11] nvJPEG2000 encoder: cost of the per-frame upload")
        best_nv = PROBE_POINT
        cand = [r for r in b.rows if r.get("codec") == "nv"
                and r.get("direction") == "E"
                and r.get("mode") == "throughput" and r.get("fps")]
        if cand:
            top = max(cand, key=lambda r: r["fps"])
            best_nv = (top["threads"], top["batch"])
        noupload = phase_noupload(b, quality, best_nv, args.dry_run)

    # the frames from the lossless round trip were needed by phases 5 and 7
    for f in list(baseline.values()):
        if f not in [pth for _, pth in IMAGES]:
            try:
                os.remove(f)
            except OSError:
                pass

    for junk in ("tmp.jp2", "tmp.ppm"):
        if os.path.exists(junk):
            try:
                os.remove(junk)
            except OSError:
                pass

    if args.dry_run:
        print("\ndry run, nothing measured")
        return 0

    write_results(b, outdir, codecs, quality, ref_size, checks, cross,
                  subs, ratios, env=env, geom=geom, ladder=ladder,
                  calib=calib, stages=stages, noupload=noupload, reps=reps,
                  scales=scales, watermark=watermark, energy=energy,
                  counter=counter)
    print("\nTotal time: %s" % human(time.time() - START))
    return 0


# ---------------------------------------------------------------------------
# checking that a decoder really produced the picture
# ---------------------------------------------------------------------------

def describe(q):
    """One readable line about the round trip."""
    kind = q.get("kind")
    if kind == "exact":
        return "exact match"
    if kind != "psnr":
        return kind
    share = q.get("diff_share", 0.0) * 100.0
    psnr = q.get("psnr")
    txt = "differences %.2f%%" % share
    if q.get("box"):
        x0, y0, x1, y1 = q["box"]
        txt += ", in the rectangle %d,%d-%d,%d" % (x0, y0, x1, y1)
    if psnr:
        txt += ", PSNR %.2f dB" % psnr
    if q.get("psnr_vs_base"):
        txt += " (vs the lossless round trip %.2f dB)" % q["psnr_vs_base"]
    if not q.get("exact"):
        txt += " (on a 1/%d sample)" % q.get("sample_stride", 1)
    return txt


def read_ppm(path):
    """Return (width, height, comps, bytes_per_sample, pixel bytes)."""
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 10 or data[0:1] != b"P":
        return None
    comps = 3 if data[1:2] == b"6" else 1
    pos = 2
    fields = []
    while len(fields) < 3 and pos < len(data):
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while pos < len(data) and data[pos:pos + 1] != b"\n":
                pos += 1
            continue
        start = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        fields.append(int(data[start:pos]))
    pos += 1
    w, h, maxval = fields
    bps = 2 if maxval > 255 else 1
    return w, h, comps, bps, data[pos:]


def compare_images(src_path, out_path, stride=13):
    """Compare a decoded image with the source.

    Returns a dict with the share of differing samples, the rectangle that
    contains them, and PSNR over the rest. That separates three cases at a
    glance: an exact round trip, a demo build that draws a watermark on a small
    part of the frame, and a codec that is actually broken, where the
    differences are spread over the whole picture.
    """
    import math
    a = read_ppm(src_path)
    b = read_ppm(out_path)
    if not a or not b:
        return {"kind": "unreadable"}
    if a[:4] != b[:4]:
        return {"kind": "different geometry"}
    w, h, comps, bps = a[:4]
    da, db = a[4], b[4]
    n = min(len(da), len(db))
    if n == 0:
        return {"kind": "empty"}
    if da[:n] == db[:n]:
        return {"kind": "exact", "diff_share": 0.0}

    peak = 255.0 if bps == 1 else 65535.0

    # exact figures when numpy happens to be installed; the script itself needs
    # only the standard library, so without numpy the same numbers are taken on
    # a uniform sample of the frame and the summary says so
    try:
        import numpy as _np
    except ImportError:
        _np = None
    if _np is not None:
        dt = _np.uint8 if bps == 1 else _np.dtype("<u2")
        va = _np.frombuffer(da[:n], dtype=dt).astype(_np.int64)
        vb = _np.frombuffer(db[:n], dtype=dt).astype(_np.int64)
        d = va - vb
        mse = float(_np.mean(d * d))
        nz = d != 0
        share = float(nz.mean())
        out = {"kind": "psnr", "diff_share": share, "exact": True,
               "psnr": (10.0 * math.log10(peak * peak / mse))
               if mse > 0 else None}
        idx = _np.nonzero(nz)[0]
        if idx.size:
            pix = idx // comps
            ys, xs = pix // w, pix % w
            out["box"] = (int(xs.min()), int(ys.min()),
                          int(xs.max()), int(ys.max()))
            out["box_share"] = ((out["box"][2] - out["box"][0] + 1)
                                * (out["box"][3] - out["box"][1] + 1)
                                / float(w * h))
        return out

    step = bps * comps * max(1, stride)
    total = 0.0
    count = 0
    diff = 0
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    samples_per_row = w * comps * bps
    for i in range(0, n - bps, step):
        if bps == 1:
            d = da[i] - db[i]
        else:
            d = ((da[i] | (da[i + 1] << 8)) - (db[i] | (db[i + 1] << 8)))
        count += 1
        if d:
            diff += 1
            y = i // samples_per_row
            x = (i % samples_per_row) // (comps * bps)
            if x < x0:
                x0 = x
            if x > x1:
                x1 = x
            if y < y0:
                y0 = y
            if y > y1:
                y1 = y
        else:
            total += 0.0
        total += d * d
    if not count:
        return {"kind": "empty"}
    share = diff / float(count)
    mse = total / count
    out = {"kind": "psnr", "diff_share": share, "exact": False,
           "sample_stride": stride,
           "psnr": (10.0 * math.log10(peak * peak / mse)) if mse > 0 else None}
    if x1 >= 0:
        out["box"] = (x0, y0, x1, y1)
        out["box_share"] = ((x1 - x0 + 1) * (y1 - y0 + 1)) / float(w * h)
    return out


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

CSV_COLUMNS = ["bench_version", "codec", "direction", "image", "alg", "mode",
               "threads", "batch", "note", "frames", "boundary", "total_ms",
               "ms_per_frame", "fps", "mb_s", "out_kb", "cr", "gpu_mem_mb",
               "gpu_avail_mb", "power_w", "j_per_frame", "j_per_frame_net",
               "energy_j_counter", "j_per_frame_counter", "j_per_frame_diff",
               "cpu_s", "cores", "gpu", "sdk", "pcie_mb_s", "wall_s", "cmd"]

def groups(rows):
    """Medians over the repeats of one and the same measurement."""
    acc = {}
    for r in rows:
        if not r.get("fps"):
            continue
        key = (r["codec"], r["direction"], r["image"], r["alg"], r["mode"],
               r.get("threads"), r.get("batch"), r.get("note") or "")
        acc.setdefault(key, []).append(r["fps"])
    out = {}
    for key, v in acc.items():
        m = median(v)
        out[key] = {"fps": m, "n": len(v),
                    "spread": (100.0 * (max(v) - min(v)) / m)
                    if (m and len(v) > 1) else 0.0}
    return out


def write_results(b, outdir, codecs, quality, ref_size,
                  checks=None, cross=None, subs=None, ratios=None,
                  env=None, geom=None, ladder=None, calib=None,
                  stages=None, noupload=None, reps=1, scales=None,
                  watermark=None, energy=None, counter=None):
    path = os.path.join(outdir, "results.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";",
                           extrasaction="ignore")
        w.writeheader()
        for r in b.rows:
            w.writerow(r)

    env = env or {}
    geom = geom or {}
    g = groups(b.rows)

    def get(codec, direction, image, alg, mode, th=None, ba=None, note=""):
        return g.get((codec, direction, image, alg, mode, th, ba, note))

    def best(codec, direction, image, alg):
        cand = [(k, v) for k, v in g.items()
                if k[0] == codec and k[1] == direction and k[2] == image
                and k[3] == alg and k[4] == "throughput" and not k[7]]
        if not cand:
            return None, None
        k, v = max(cand, key=lambda kv: kv[1]["fps"])
        return v, (k[5], k[6])

    L = []
    add = L.append

    # ------------------------------------------------------------ test system
    add("JPEG2000 codec comparison")
    add("")
    add("Test system and measurement conditions")
    add("")
    sdk = {}
    gpu_seen = ""
    pcie = ""
    for r in b.rows:
        if r.get("sdk") and r["codec"] not in sdk:
            sdk[r["codec"]] = r["sdk"]
        if r.get("gpu") and not gpu_seen:
            gpu_seen = r["gpu"]
        if r.get("pcie_mb_s") and not pcie:
            pcie = r["pcie_mb_s"]
    rows_env = [
        ("GPU", env.get("gpu") or gpu_seen or "-"),
        ("Driver", env.get("driver", "-")),
        ("CUDA (driver)", env.get("cuda_driver", "-")),
        ("GPU memory", env.get("gpu_mem", "-")),
        ("Power limit", env.get("power_limit", "-")),
        ("CPU", env.get("cpu", "-")),
        ("Architecture", env.get("arch", "-")),
        ("Cores / RAM", "%s / %s" % (env.get("cores", "-"),
                                     ("%.0f GB" % env["ram_gb"])
                                     if env.get("ram_gb") else "-")),
        ("Operating system", env.get("os", "-")),
        ("Python", env.get("python", "-")),
        ("Bus, measured", ("%s MB/s host -> GPU" % pcie)
         if pcie else "-"),
        ("Measurement date", env.get("date", "-")),
        ("Repeats per point", str(reps)),
        ("Benchmark script", "bench-04.py, version " + BENCH_VERSION),
        ("Energy meters", (("counter + sampling (%s)" % counter.source)
                           if (counter and counter.available)
                           else "sampling only, no NVML counter")),
    ]
    for key, label in (("board", "Board (Jetson)"),
                       ("jetpack", "JetPack"),
                       ("power_mode", "Power mode")):
        if env.get(key):
            rows_env.append((label, env[key]))
    for c in codecs:
        rows_env.append((CODECS[c]["name"], sdk.get(c, "-")))
    w1 = max(len(a) for a, _ in rows_env)
    for a, v in rows_env:
        add("  %-*s  %s" % (w1, a, v))
    add("")
    add("  Stream settings: code block %dx%d, %d resolution levels, one "
        "quality" % (CODE_BLOCK, CODE_BLOCK, LEVELS))
    add("  layer, LRCP progression, tiling off, SOP and EPH markers off.")
    add("  Search grid: " + ", ".join("%dx%d" % p for p in POINTS))
    add("  Notation: fv - the Fastvideo codec, nv - nvJPEG2000,")
    add("  E - encoding, D - decoding.")
    add("  The measured time: encoder - from pixels in GPU memory to the")
    add("  compressed stream in host memory; decoder mirrored. Disk excluded.")
    add("")

    for tag, _ in IMAGES:
        if tag in geom:
            add("  %s: %d x %d, %d components"
                % (tag, geom[tag]["w"], geom[tag]["h"], geom[tag]["comps"]))
    add("")

    # ---------------------------------------------------------- quality ladder
    if ladder:
        add("-" * 78)
        add("Quality ladder, Fastvideo codec, lossy mode")
        add("")
        add("    q    2K, kB    2K ratio       2K bpp     4K, kB"
            "    4K ratio       4K bpp")
        add("  " + "-" * 74)
        for r in ladder:
            add("  %3s %9s %11s %12s %10s %11s %12s"
                % (r["q"], r.get("2k_kb") or "-",
                   ("%.1f:1" % r["2k_cr"]) if r.get("2k_cr") else "-",
                   ("%.2f" % r["2k_bpp"]) if r.get("2k_bpp") else "-",
                   r.get("4k_kb") or "-",
                   ("%.1f:1" % r["4k_cr"]) if r.get("4k_cr") else "-",
                   ("%.2f" % r["4k_bpp"]) if r.get("4k_bpp") else "-"))
        add("")
        add("  The same setting gives different compression on different")
        add("  frames: the knob sets the coarseness of rounding, not the")
        add("  file size.")
        add("")

    # ------------------------------------------------------ reference streams
    add("-" * 78)
    add("Reference streams")
    add("")
    add("  codec  frame alg        size, kB    ratio     bit/pixel")
    add("  " + "-" * 58)
    for c in codecs:
        for tag, _ in IMAGES:
            for alg in ALGS:
                kb = ref_size.get((c, tag, alg))
                bpp = bits_per_pixel(kb, geom.get(tag))
                cr = None
                for r in b.rows:
                    pass
                add("  %-6s %-5s %-8s %10s %8s %13s"
                    % (c, tag, alg, kb or "-",
                       ("%.1f:1" % (geom[tag]["w"] * geom[tag]["h"]
                                    * geom[tag]["comps"] / (kb * 1024.0)))
                       if (kb and tag in geom) else "-",
                       ("%.2f" % bpp) if bpp else "-"))
    add("")

    # ---------------------------------------------------------- size matching
    if calib:
        add("-" * 78)
        add("Size matching: nvJPEG2000 quality search for a given file size")
        add("")
        add("  frame target, bytes       q found      actual, bytes     miss")
        add("  " + "-" * 62)
        for r in calib:
            add("  %-5s %13s %13s %18s %8s"
                % (r["image"], r.get("target") or "-",
                   ("%.2f" % r["q"]) if r.get("q") else "-",
                   r.get("got") or "-",
                   ("%.2f %%" % r["miss"]) if r.get("miss") is not None
                   else "-"))
        add("")

    # ---------------------------------------------------------- quality scales
    if scales:
        add("-" * 78)
        add("Check that the two quality scales correspond")
        add("")
        add("  frame    fv quality target, bytes  search [1,100]"
            "  search [50,99]      diff")
        add("  " + "-" * 76)
        for r in scales:
            d = (abs(r["wide"] - r["narrow"])
                 if (r.get("wide") and r.get("narrow")) else None)
            add("  %-5s %13s %13s %15s %15s %9s"
                % (r["image"], r["fv_q"], r.get("target") or "-",
                   ("%.4f" % r["wide"]) if r.get("wide") else "-",
                   ("%.4f" % r["narrow"]) if r.get("narrow") else "-",
                   ("%.4f" % d) if d is not None else "-"))
        add("")
        for line in scales_verdict(scales):
            for piece in textwrap.wrap(line, 74):
                add("  " + piece)
        add("")
        add("  The search tolerance here is %.2f %% by size against %.2f %%"
            % (100.0 * SCALE_CHECK_TOL, 100.0 * CALIB_TOL))
        add("  in the main run: the search goes deeper, the grid cell gets")
        add("  narrower, and the property of the scales is separated from")
        add("  the trace of the bisection procedure itself.")
        add("")

    # ------------------------------------------------------------- full grids
    for d, title in (("E", "Encoding"), ("D", "Decoding")):
        add("-" * 78)
        add("%s, frames per second (median over %d repeats)" % (title, reps))
        add("")
        head = "  workload                        single"
        for th, ba in POINTS:
            head += " %6s " % ("%dx%d" % (th, ba))
        head += "   best"
        add(head)
        add("  " + "-" * (len(head) - 2))
        for tag, _ in IMAGES:
            for alg in ALGS:
                for c in codecs:
                    lat = get(c, d, tag, alg, "latency", 1, 1)
                    line = "  %-31s %6s" % (
                        "%s %s, %s" % (tag, "lossy" if alg == "irrev"
                                       else "lossless", CODECS[c]["name"]),
                        ("%.0f" % lat["fps"]) if lat else "-")
                    bv, bp = best(c, d, tag, alg)
                    for th, ba in POINTS:
                        v = get(c, d, tag, alg, "throughput", th, ba)
                        mark = "*" if (bp == (th, ba) and v) else " "
                        line += " %6s%s" % (("%.0f" % v["fps"])
                                            if v else "-", mark)
                    line += "   %-6s" % (("%dx%d" % bp) if bp else "-")
                    add(line)
        add("")

    # ---------------------------------------------------------------- summary
    if len(codecs) == 2:
        a, bb = codecs
        add("-" * 78)
        add("Summary: single image mode and the best combination of threads")
        add("and batch")
        add("")
        add("  dir   frame alg              single, fps"
            "           multithreaded, fps")
        add("  %-5s %-5s %-12s %7s %7s %5s  %-11s %-11s %5s"
            % ("", "", "", a, bb, "ratio", a, bb, "ratio"))
        add("  " + "-" * 74)
        for tag, _ in IMAGES:
            for alg in ALGS:
                for d in ("E", "D"):
                    la = get(a, d, tag, alg, "latency", 1, 1)
                    lb = get(bb, d, tag, alg, "latency", 1, 1)
                    ta, pa = best(a, d, tag, alg)
                    tb, pb = best(bb, d, tag, alg)

                    def f(v):
                        return "%7s" % (("%.0f" % v["fps"]) if v else "-")

                    def ft(v, p):
                        if not v:
                            return "%11s" % "-"
                        return "%6.0f %-4s" % (v["fps"], "%dx%d" % p)

                    def rat(x, y):
                        if x and y and y["fps"]:
                            return "%5.2f" % (x["fps"] / y["fps"])
                        return "%5s" % "-"

                    add("  %-5s %-5s %-12s %s %s %s  %s %s %s"
                        % (d, tag, ALG_RU.get(alg, alg),
                           f(la), f(lb), rat(la, lb),
                           ft(ta, pa), ft(tb, pb), rat(ta, tb)))
        add("")
        add("  E - encoding, D - decoding, ratio = %s / %s." % (a, bb))
        add("  In the tables above a star marks the best value in the row.")
        add("")

    # ---------------------------------------------------- speedup: where from
    add("-" * 78)
    add("Where the speedup comes from: threads and batching")
    add("")
    add("  codec  dir   frame alg       from threads from batch   total")
    add("  " + "-" * 62)
    for c in codecs:
        for d in ("E", "D"):
            for tag, _ in IMAGES:
                for alg in ALGS:
                    lat = get(c, d, tag, alg, "latency", 1, 1)
                    thr = get(c, d, tag, alg, "throughput", 8, 1)
                    bv, bp = best(c, d, tag, alg)
                    if not (lat and thr and bv):
                        continue
                    add("  %-6s %-5s %-5s %-9s %12s %10s %7s"
                        % (c, d, tag, alg,
                           "%.2fx" % (thr["fps"] / lat["fps"]),
                           "%.2fx" % (bv["fps"] / thr["fps"]),
                           "%.2fx" % (bv["fps"] / lat["fps"])))
    add("")
    add("  From threads - going from single image mode to 8x1. From batch -")
    add("  from 8x1 to the best combination. The two multiply into 'total'.")
    add("")

    # ----------------------------------------------------------- repeatability
    if reps > 1:
        add("-" * 78)
        add("Repeatability: spread between repeats of one measurement")
        add("")
        add("  codec  dir      worst spread       mean spread  points")
        add("  " + "-" * 58)
        for c in codecs:
            for d in ("E", "D"):
                sp = [v["spread"] for k, v in g.items()
                      if k[0] == c and k[1] == d and v["n"] > 1]
                if not sp:
                    continue
                add("  %-6s %-6s %14s %17s %7d"
                    % (c, d, "%.1f %%" % max(sp),
                       "%.1f %%" % (sum(sp) / len(sp)), len(sp)))
        add("")

    # ------------------------------------------------------------ round trip
    if checks:
        add("-" * 78)
        add("Round trip check: encode, decode, compare")
        add("")
        add("  codec  frame alg      result")
        add("  " + "-" * 68)
        for c, tag, alg, q in checks:
            add("  %-6s %-5s %-8s %s" % (c, tag, alg, describe(q)))
        add("")
        add("  Lossless is expected to be an exact match. A small share of")
        add("  differences collected into one rectangle is the watermark of")
        add("  the demo build, not a defect of the codec.")
        add("")

    if watermark:
        add("-" * 78)
        add("Watermark on the frame, and what PSNR is measured against")
        add("")
        add("  codec  frame watermark      applied     PSNR reference")
        add("  " + "-" * 62)
        for w in watermark:
            add("  %-6s %-5s %9s %12s     %s"
                % (w["codec"], w["image"],
                   "yes" if w.get("has_mark") else "no",
                   ("repeatable" if w.get("stable") else "varies")
                   if w.get("has_mark") else "-",
                   "lossless round trip" if (w.get("has_mark")
                                             and w.get("stable"))
                   else "original"))
        add("")
        add("  The demo build draws a watermark on the frame BEFORE encoding.")
        add("  Comparing a decoded frame with the source file would then")
        add("  measure the watermark and not the codec. So the reference is")
        add("  the frame that came back through the LOSSLESS round trip on")
        add("  the same build: it is bit for bit what the encoder was given.")
        add("  The condition: the watermark must be applied the same way")
        add("  every run; that is checked by two independent lossless round")
        add("  trips, which must come out byte for byte identical.")
        add("")

    # ------------------------------------------------------ chroma subsampling
    if subs:
        add("-" * 78)
        add("Chroma subsampling, Fastvideo codec only")
        add("")
        add("  frame mode      size, kB    ratio        enc single"
            " multithreaded   PSNR")
        add("  " + "-" * 74)
        for r in subs:
            add("  %-5s %-6s %11s %8s %17s %13s %6s"
                % (r["image"], r["sub"], r.get("kb") or "-",
                   ("%.1f:1" % r["cr"]) if r.get("cr") else "-",
                   ("%.0f" % r["enc_lat"]) if r.get("enc_lat") else "-",
                   ("%.0f" % r["enc_thr"]) if r.get("enc_thr") else "-",
                   ("%.1f" % r["psnr"]) if r.get("psnr") else "-"))
        add("")
        add("  PSNR is computed against the original full-colour frame, so")
        add("  it includes the loss from the chroma subsampling as well.")
        add("")

    # ---------------------------------------------------- compression ratios
    if ratios:
        add("-" * 78)
        add("Compression ratio sweep (Fastvideo - rate control,")
        add("nvJPEG2000 quality matched to the same size)")
        add("")
        add("  frame   ratio   fv, kB   nv, kB    nv q   enc fv   enc nv"
            "   dec fv   dec nv")
        add("  " + "-" * 76)
        for r in ratios:
            def n(key, fmt="%.0f"):
                return (fmt % r[key]) if r.get(key) else "-"
            add("  %-5s %7s %8s %8s %7s %8s %8s %8s %8s"
                % (r["image"], "%.0f:1" % r["ratio"], r.get("fv_kb") or "-",
                   r.get("nv_kb") or "-", n("nv_q", "%.2f"), n("fv_enc"),
                   n("nv_enc"), n("fv_dec"), n("nv_dec")))
        add("")
        add("  All numbers are single image mode. Decoding time follows the")
        add("  number of coding passes in the stream, not the size of the")
        add("  file.")
        add("")

    # ------------------------------------------------ energy, two meters
    if energy:
        add("-" * 78)
        add("Energy per frame: two meters and the differential method")
        add("")
        add("  dir   frame alg      codec   counter  sampling  minus idle"
            "   cores   spread")
        add("  " + "-" * 74)
        gaps = []
        for tag, _ in IMAGES:
            for alg in ALGS:
                for d in ("E", "D"):
                    for c in codecs:
                        rs = [r for r in energy
                              if r["codec"] == c and r["direction"] == d
                              and r["image"] == tag and r["alg"] == alg]
                        if not rs:
                            continue
                        r = rs[0]
                        cnt_v = r.get("j_per_frame_diff")
                        smp = r.get("j_per_frame_sampled")
                        gap = None
                        if cnt_v and smp:
                            gap = 100.0 * (smp - cnt_v) / cnt_v
                            gaps.append(abs(gap))
                        add("  %-5s %-5s %-8s %-6s %8s %9s %11s %7s %8s"
                            % (d, tag, alg, c,
                               ("%.3f" % cnt_v) if cnt_v else "-",
                               ("%.3f" % smp) if smp else "-",
                               ("%.3f" % r["j_per_frame_sampled_net"])
                               if r.get("j_per_frame_sampled_net") else "-",
                               ("%.1f" % r["cores"]) if r.get("cores")
                               else "-",
                               ("%+.0f %%" % gap) if gap is not None else "-"))
        add("")
        add("  Two meters at once. 'counter' is the card's own cumulative")
        add("  energy counter, read through NVML, and the value is the")
        add("  DIFFERENCE between a run on 2N frames and a run on N frames,")
        add("  divided by N: everything that does not depend on the number of")
        add("  frames - process start, buffers, the card's idle draw - falls")
        add("  out of the difference. 'sampling' is the older method: average")
        add("  power over the whole run times its wall time, divided by the")
        add("  frames, so it still carries that fixed cost; 'minus idle' has")
        add("  the card's idle draw taken off it.")
        add("")
        if gaps:
            med = median(gaps) or 0.0
            add("  The two meters differ by %.0f %% on the median point and by"
                % med)
            add("  %.0f %% at most. The counter is the one to quote: it loses"
                % max(gaps))
            add("  nothing between samples and the difference removes the")
            add("  fixed cost of a run.")
            add("")
        else:
            add("  The counter was not available on this machine, so only the")
            add("  sampled column is filled. Install nvidia-ml-py and repeat")
            add("  the run to get the second meter.")
            add("")

    # ------------------------------------------------------------- energy
    grid_energy = [r for r in b.rows
                   if r.get("mode") == "throughput" and r.get("j_per_frame")]
    if grid_energy and not energy:
        add("-" * 78)
        add("Energy per frame and CPU load at the best combination")
        add("")
        add("  dir   frame alg      codec    J/frame"
            "     J/frame minus idle  cores")
        add("  " + "-" * 74)
        seen = set()
        for tag, _ in IMAGES:
            for alg in ALGS:
                for d in ("E", "D"):
                    for c in codecs:
                        rs = [r for r in grid_energy
                              if r["codec"] == c and r["direction"] == d
                              and r["image"] == tag and r["alg"] == alg
                              and not r.get("note")]
                        if not rs or (d, tag, alg, c) in seen:
                            continue
                        seen.add((d, tag, alg, c))
                        r = max(rs, key=lambda x: x["fps"])
                        add("  %-5s %-5s %-8s %-6s %9.3f %22s %6s"
                            % (d, tag, alg, c, r["j_per_frame"],
                               ("%.3f" % r["j_per_frame_net"])
                               if r.get("j_per_frame_net") else "-",
                               ("%.1f" % r["cores"]) if r.get("cores")
                               else "-"))
        add("")
        add("  J/frame is measured for the whole card, so it includes the")
        add("  memory and everything else on it; the second column has the")
        add("  card's idle draw subtracted. 'cores' is the processor time of")
        add("  the codec itself divided by wall clock time: it does not")
        add("  depend on other load on the machine.")
        add("")

    # ---------------------------------------------------------- cross-decoding
    if cross:
        add("-" * 78)
        add("Cross-decoding: the other codec's stream instead of its own")
        add("")
        add("  codec  frame alg       own stream  other stream      change")
        add("  " + "-" * 62)
        for c, tag, alg, own, oth in cross:
            chg = "%+.0f %%" % ((oth / own - 1.0) * 100.0) \
                if (own and oth) else "-"
            add("  %-6s %-5s %-8s %11s %13s %11s"
                % (c, tag, alg, ("%.0f" % own) if own else "-",
                   ("%.0f" % oth) if oth else "-", chg))
        add("")
        add("  A large change means the two streams give the decoder")
        add("  different amounts of work, and a comparison of decoders turns")
        add("  into a comparison of what the encoders produced.")
        add("")

    # ------------------------------------------------------- stage breakdown
    if stages:
        add("-" * 78)
        add("Stage breakdown, one frame, -info key, lossy mode")
        add("")
        for key in sorted(stages):
            c, d, tag = key
            add("  %s, %s, %s"
                % (CODECS[c]["name"], "encoding" if d == "E"
                   else "decoding", tag))
            for name, ms, share in stages[key]:
                add("      %-46s %7.2f ms %6.1f %%" % (name[:46], ms, share))
            add("")
        add("  The -info key inserts synchronisations between the stages, so")
        add("  the sum of the stages is larger than the real time of one")
        add("  frame. Read the shares only, never add them up.")
        add("")

    # ---------------------------------------------------------- diagnostics
    if noupload:
        add("-" * 78)
        add("nvJPEG2000 encoder: the cost of uploading a frame to the GPU")
        add("")
        add("  frame  with upload without upload      diff")
        add("  " + "-" * 48)
        for r in noupload:
            add("  %-5s %12s %14s %9s"
                % (r["image"], ("%.0f" % r["with_upload"])
                   if r.get("with_upload") else "-",
                   ("%.0f" % r["without"]) if r.get("without") else "-",
                   ("+%.0f %%" % r["gain"]) if r.get("gain") else "-"))
        add("")
        add("  The check separates the benchmark harness from the library:")
        add("  if the gain is small even without the upload, the flat")
        add("  behaviour of the encoder is a property of the library itself,")
        add("  not a consequence of the harness.")
        add("")

    machine = {
        "bench_version": BENCH_VERSION,
        "bench_script": "bench-04.py",
        "license": "CC BY 4.0 - https://creativecommons.org/licenses/by/4.0/ "
                   "- attribution: Fastvideo JPEG2000 benchmark. Keep the "
                   "measurement conditions next to the numbers.",
        "environment": env,
        "settings": {"code_block": CODE_BLOCK, "levels": LEVELS,
                     "layers": 1, "progression": "LRCP", "tiling": False,
                     "grid": ["%dx%d" % p for p in POINTS],
                     "repeats": reps, "quality": {"%s_%s" % k: v
                                                  for k, v in quality.items()},
                     "boundary": "encoder: pixels in GPU memory -> stream in "
                                 "host memory; decoder mirrored; disk excluded"},
        "images": geom,
        "quality_ladder": ladder or [],
        "reference_streams": [{"codec": k[0], "image": k[1], "alg": k[2],
                               "kb": v,
                               "bits_per_pixel": bits_per_pixel(v,
                                                                geom.get(k[1]))}
                              for k, v in sorted(ref_size.items())],
        "size_matching": calib or [],
        "quality_scales": scales or [],
        "measurements": [{"codec": k[0], "direction": k[1], "image": k[2],
                          "alg": k[3], "mode": k[4], "threads": k[5],
                          "batch": k[6], "note": k[7], "fps": v["fps"],
                          "repeats": v["n"], "spread_percent": v["spread"]}
                         for k, v in sorted(g.items(),
                                            key=lambda kv: str(kv[0]))],
        "round_trip": [{"codec": c, "image": t_, "alg": a, "quality": q}
                       for c, t_, a, q in (checks or [])],
        "cross_decode": [{"codec": c, "image": t_, "alg": a, "own_fps": o,
                          "other_fps": ot}
                         for c, t_, a, o, ot in (cross or [])],
        "subsampling": subs or [],
        "ratio_sweep": ratios or [],
        "stage_breakdown": {"%s_%s_%s" % k: [{"stage": n, "ms": ms,
                                              "share_percent": sh}
                                             for n, ms, sh in v]
                            for k, v in (stages or {}).items()},
        "energy": energy or [],
        "energy_meters": {
            "counter": (counter.source if (counter and counter.available)
                        else None),
            "counter_error": (counter.error if counter else "not created"),
            "sampling": "average power from nvidia-smi times wall time",
            "method": "counter value is the difference between a 2N-frame run "
                      "and an N-frame run, divided by N",
        },
        "upload_diagnostic": noupload or [],
        "watermark_check": watermark or [],
    }
    with open(os.path.join(outdir, "results.json"), "w",
              encoding="utf-8") as fh:
        json.dump(machine, fh, ensure_ascii=False, indent=1, default=str)

    text = "\n".join(L) + "\n"
    with open(os.path.join(outdir, "summary.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(text)
    print("")
    print(text)
    print("written: %s" % path)
    print("written: %s" % os.path.join(outdir, "summary.txt"))
    print("written: %s" % os.path.join(outdir, "results.json"))


START = time.time()

if __name__ == "__main__":
    sys.exit(main())
