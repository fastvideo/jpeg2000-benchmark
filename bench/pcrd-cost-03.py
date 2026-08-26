#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What it costs to hit a given compressed size, measured the short way.

The question: rate control (-cr, PCRD) reaches a target file size, and the
previous series measured it with no quality parameter set, so quantisation was
left at its default and PCRD had to trim a stream that carried everything.
Does setting a base quality first give the speed back, and how much of it?

At one and the same output size this compares:

  q85        quality 85, no rate control - this defines the target and is the
             reference row; it is how sections 6-10 of the article encode
  cr-only    no quality parameter, rate control alone - how section 11 encoded
  q90+cr     quality fixed above the target, rate control trimming the rest
  q95+cr

Deliberately small.  The effect being measured is tens of per cent; the spread
between repeats is a few per cent.  Three repeats, a threads-by-batch grid, a
bisection for the reference row and five runs per stage breakdown were all
measured in the first version and none of them changed a conclusion.  About 70
runs here against about 700 there.

    python pcrd-cost-02.py --selftest    checks only, measures nothing
    python pcrd-cost-02.py               the run, roughly 40 minutes
    python pcrd-cost-02.py --report DIR  rebuild the report from a run folder

Results are written as they are computed, one line per row, into
results.jsonl.  Stopping the run at any point leaves a usable file: nothing has
to be recovered from logs afterwards.
"""

import argparse
import csv
import datetime
import json
import math
import os
import platform
import re
import subprocess
import sys
import time

BENCH_VERSION = "pcrd-2026-08-26.3"

EXE = ".exe" if os.name == "nt" else ""

CODECS = {
    "fv": {"enc": "J2kEncoderSample" + EXE, "dec": "J2kDecoderSample" + EXE},
    "nv": {"enc": "nvj2kEncoderSample" + EXE, "dec": "nvj2kDecoderSample" + EXE},
}

IMAGES = [("2k", "2k_wild.ppm"), ("4k", "4k_wild.ppm")]

CODE_BLOCK = 32
LEVELS = 6

Q_REF = 85.0                     # the reference quality; it defines the target
Q_LADDER = [85, 90, 95, 100]     # natural sizes, also the source of variants
Q_VARIANTS = [90, 95]            # quality values tried together with -cr

CALIB_TOL = 0.001                # 0.1 %, same rule as the article uses
CALIB_STEPS = 6
Q_PRINT_TOL = 0.06               # the sample prints quality with one decimal
MEASURE_S = 3.0                  # length of one speed measurement
PROBE_FRAMES = 40
HEARTBEAT_S = 300.0              # a sign of life at least this often
DEFAULT_RUN_COST_S = 33.0        # measured on the Windows/RTX 4090 machine

RE_SDK = re.compile(r"SDK version:\s*(\S+)")
RE_GPU = re.compile(r"Processing unit:\s*(.+?)\s*\(device id")
RE_QUALITY = re.compile(r"^\s*([\d.]+)\s*%\s*Quality\s*$", re.M)
RE_RATIO = re.compile(r"^\s*([\d.]+):1\s*Compression ratio\s*$", re.M)
RE_PCRD_OFF = re.compile(r"PCRD is disabled")
RE_SIZE = re.compile(r"size\s*=\s*(\d+)\s*KB\s*\(([\d.]+):1\)")
RE_CALIB = re.compile(r"Calibration:\s*q\s*=\s*([\d.]+)")
RE_STAGE = re.compile(r"^\s*([\d.]+)\s*ms\s+(\d+)\)\s*(.+?)\s*$", re.M)
RE_SUMMARY = re.compile(
    r"for\s+(\d+)\s+images"
    r"(?:\s+per\s+(\d+)\s+threads?)?"
    r"\s*=\s*([\d.]+)\s*ms;"
    r"(?:\s*([\d.]+)\s*MB/s;)?"
    r"\s*([\d.]+)\s*FPS;")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def median(values):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def spread_pct(values):
    v = [x for x in values if x]
    if len(v) < 2:
        return None
    m = median(v)
    return 100.0 * (max(v) - min(v)) / m if m else None


def hms(seconds):
    seconds = int(seconds + 0.5)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def now_hm():
    return datetime.datetime.now().strftime("%H:%M:%S")


def read_ppm(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 10 or data[0:1] != b"P":
        return None
    comps = 3 if data[1:2] == b"6" else 1
    pos, fields = 2, []
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
    return w, h, comps, (2 if maxval > 255 else 1), data[pos:]


def compare_images(src_path, out_path):
    a, b = read_ppm(src_path), read_ppm(out_path)
    if not a or not b:
        return {"kind": "unreadable"}
    if a[:4] != b[:4]:
        return {"kind": "different geometry"}
    bps = a[3]
    n = min(len(a[4]), len(b[4]))
    if n == 0:
        return {"kind": "empty"}
    if a[4][:n] == b[4][:n]:
        return {"kind": "exact", "diff_share": 0.0, "psnr": None}
    try:
        import numpy as np
    except ImportError:
        return {"kind": "no numpy"}
    dt = np.uint8 if bps == 1 else np.dtype("<u2")
    va = np.frombuffer(a[4][:n], dtype=dt).astype(np.int64)
    vb = np.frombuffer(b[4][:n], dtype=dt).astype(np.int64)
    d = va - vb
    mse = float(np.mean(d * d))
    peak = 255.0 if bps == 1 else 65535.0
    return {"kind": "psnr", "diff_share": float((d != 0).mean()),
            "psnr": (10.0 * math.log10(peak * peak / mse)) if mse > 0 else None}


def parse_output(text):
    out = {}
    for key, rx, cast in (("sdk", RE_SDK, str), ("gpu", RE_GPU, str),
                          ("quality_printed", RE_QUALITY, float),
                          ("ratio_printed", RE_RATIO, float),
                          ("calib_q", RE_CALIB, float)):
        m = rx.search(text)
        if m:
            out[key] = cast(m.group(1))
    out["pcrd_disabled"] = bool(RE_PCRD_OFF.search(text))
    m = RE_SIZE.search(text)
    if m:
        out["out_kb"] = int(m.group(1))
        out["cr_printed"] = float(m.group(2))
    best = None
    for line in text.splitlines():
        sm = RE_SUMMARY.search(line)
        if sm:
            best = sm
    if best:
        frames = int(best.group(1))
        total = float(best.group(3))
        out["frames"] = frames
        out["total_ms"] = total
        out["ms_per_frame"] = total / frames if frames else 0.0
        out["fps"] = float(best.group(5))
    out["stages"] = [(re.sub(r"\s*\(.*\)\s*$", "", n), float(ms))
                     for ms, _, n in RE_STAGE.findall(text)]
    return out


def size_of(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


# ---------------------------------------------------------------------------
# progress: a sign of life on a timer, not on phase boundaries
# ---------------------------------------------------------------------------

class Progress(object):
    """Prints the wall-clock time at least every HEARTBEAT_S seconds.

    A long run with no output is indistinguishable from a hung one.  The
    previous version printed only when a variant finished, and on 4K that is
    tens of minutes of silence.
    """

    def __init__(self, planned, run_cost):
        self.t0 = time.time()
        self.planned = planned
        self.run_cost = run_cost
        self.done = 0
        self.last = 0.0
        self.what = ""

    def set_task(self, what):
        self.what = what

    def count(self, seconds):
        self.done += 1
        # the estimate follows the machine rather than my expectations: the
        # plain average over everything done so far, because the cost of one
        # run varies a lot by kind and a running average would swing about
        if self.done >= 3:
            self.run_cost = (time.time() - self.t0) / self.done
        self.beat()

    def left(self):
        return max(0, self.planned - self.done) * self.run_cost

    def beat(self, force=False):
        t = time.time()
        if not force and t - self.last < HEARTBEAT_S:
            return
        self.last = t
        print("   [%s] прогонов %d из ~%d, прошло %s, осталось примерно %s%s"
              % (now_hm(), self.done, self.planned, hms(t - self.t0),
                 hms(self.left()), ("  |  " + self.what) if self.what else ""))
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# results are written as they are computed
# ---------------------------------------------------------------------------

class Recorder(object):
    """Append-only file of results, flushed after every row.

    The first version wrote results.json when the whole run had finished, so a
    run stopped half way left nothing but logs.  Here every value goes to disk
    at the moment it is computed.
    """

    def __init__(self, outdir):
        self.path = os.path.join(outdir, "results.jsonl")
        self.fh = open(self.path, "a", encoding="utf-8")

    def add(self, kind, **row):
        row["kind"] = kind
        row["at"] = datetime.datetime.now().isoformat(timespec="seconds")
        self.fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.fh.flush()
        try:
            os.fsync(self.fh.fileno())
        except OSError:
            pass

    def close(self):
        try:
            self.fh.close()
        except Exception:
            pass


class Bench(object):
    def __init__(self, outdir, recorder, progress, dry_run=False):
        self.outdir = outdir
        self.logdir = os.path.join(outdir, "logs")
        self.rec = recorder
        self.pr = progress
        self.dry_run = dry_run
        os.makedirs(self.logdir, exist_ok=True)

    def run(self, exe, args, log_name):
        if os.path.exists(exe):
            exe = os.path.abspath(exe)
        cmd = [exe] + [str(a) for a in args]
        if self.dry_run:
            print("   would run:", " ".join(cmd))
            return {}
        t0 = time.time()
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            out, _ = p.communicate(timeout=1800)
            text = out.decode("utf-8", "replace")
        except FileNotFoundError:
            text = "ERROR: %s not found\n" % exe
        except subprocess.TimeoutExpired:
            p.kill()
            text = "ERROR: timed out\n"
        wall = time.time() - t0
        res = parse_output(text)
        res["wall_s"] = round(wall, 2)
        res["cmd"] = " ".join(cmd)
        res["log"] = log_name

        # the log carries its own result in the header: one log is then enough
        head = ["# %s" % log_name,
                "# started %s, took %.2f s" % (now_hm(), wall),
                "# parsed: " + json.dumps(
                    {k: v for k, v in res.items()
                     if k not in ("stages", "cmd", "log")},
                    ensure_ascii=False)]
        if res.get("stages"):
            head.append("# stages: " + json.dumps(res["stages"],
                                                  ensure_ascii=False))
        with open(os.path.join(self.logdir, log_name + ".log"), "w",
                  encoding="utf-8") as fh:
            fh.write("\n".join(head) + "\n\n$ " + " ".join(cmd) + "\n\n" + text)

        self.rec.add("run", log=log_name, wall_s=res["wall_s"],
                     fps=res.get("fps"), out_kb=res.get("out_kb"),
                     quality_printed=res.get("quality_printed"),
                     ratio_printed=res.get("ratio_printed"))
        self.pr.count(wall)
        res["raw"] = text
        return res


# ---------------------------------------------------------------------------
# encoder arguments
# ---------------------------------------------------------------------------

def fv_enc(image, out, q=None, cr=None, extra=None):
    a = ["-i", image, "-o", out, "-a", "irrev", "-c", CODE_BLOCK, "-l", LEVELS]
    if q is not None:
        a += ["-q", "%g" % q]
    if cr is not None:
        a += ["-cr", "%.4f" % cr]
    return a + list(extra or [])


def dec_args(ref, out="tmp.ppm", extra=None):
    return ["-i", ref, "-o", out] + list(extra or [])


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------

def preflight(b, images):
    print("\n[0] проверки перед измерением  [%s]" % now_hm())
    ok = True
    for name in (CODECS["fv"]["enc"], CODECS["fv"]["dec"]):
        if not os.path.exists(name):
            print("   НЕТ ФАЙЛА: %s" % name)
            ok = False
    geom = {}
    for tag, path in images:
        if not os.path.exists(path):
            print("   НЕТ ФАЙЛА: %s" % path)
            ok = False
            continue
        g = read_ppm(path)
        if not g:
            print("   %s не читается как двоичный PPM/PGM" % path)
            ok = False
            continue
        geom[tag] = {"w": g[0], "h": g[1], "comps": g[2], "bps": g[3],
                     "raw_bytes": g[0] * g[1] * g[2] * g[3]}
        print("   %-3s %dx%d, компонент %d, %d бит, исходно %d байт"
              % (tag, g[0], g[1], g[2], 8 * g[3], geom[tag]["raw_bytes"]))
    if not ok:
        return None
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("   ВНИМАНИЕ: numpy не установлен, PSNR считаться не будет")

    tag, path = images[0]
    r = b.run(CODECS["fv"]["enc"],
              fv_enc(path, "pf_q85.jp2", q=Q_REF, extra=["-info"]), "pf_q85")
    if b.dry_run:
        return {"geom": geom, "default_q": 100.0, "watermark": False,
                "psnr_ref": {t: p for t, p in images}}
    nat = size_of("pf_q85.jp2")
    if not nat:
        print("   ОШИБКА: при -q 85 файл не получился, см. logs/pf_q85.log")
        return None
    print("   -q 85 отдельно: %d байт, напечатано качество %s, PCRD выключен: %s"
          % (nat, r.get("quality_printed"), r.get("pcrd_disabled")))

    # какое качество стоит по умолчанию: от этого зависит смысл строки cr-only
    r0 = b.run(CODECS["fv"]["enc"], fv_enc(path, "pf_def.jp2", extra=["-info"]),
               "pf_default_q")
    default_q = r0.get("quality_printed")
    print("   без -q кодер печатает качество %s — значит строка «только -cr» "
          "это на самом деле «качество %s плюс -cr»" % (default_q, default_q))

    # главное: берёт ли кодер -q и -cr вместе
    cr = geom[tag]["raw_bytes"] / float(nat)
    r2 = b.run(CODECS["fv"]["enc"],
               fv_enc(path, "pf_q95cr.jp2", q=95, cr=cr, extra=["-info"]),
               "pf_q95_cr")
    qp, rp = r2.get("quality_printed"), r2.get("ratio_printed")
    got = size_of("pf_q95cr.jp2")
    has_pcrd = any(n.lower().startswith("pcrd") for n, _ in r2.get("stages", []))
    print("   -q 95 вместе с -cr %.3f: качество %s, степень %s, %s байт, "
          "строка PCRD в разборе: %s" % (cr, qp, rp, got, has_pcrd))
    if qp is None or abs(qp - 95.0) > Q_PRINT_TOL:
        print("   ОШИБКА: кодер не принял -q вместе с -cr, напечатано %s." % qp)
        print("   Пришлите logs/pf_q95_cr.log — перестрою тест под то, что он "
              "принимает.")
        return None
    if rp is None:
        print("   ОШИБКА: нет строки «Compression ratio», -cr не сработал.")
        return None

    # ватермарк: полный цикл без потерь обязан вернуть кадр байт в байт
    b.run(CODECS["fv"]["enc"], ["-i", path, "-o", "pf_rev.jp2", "-a", "rev",
                                "-c", CODE_BLOCK, "-l", LEVELS], "pf_rev_enc")
    b.run(CODECS["fv"]["dec"], dec_args("pf_rev.jp2", "pf_rev.ppm"),
          "pf_rev_dec")
    wm = compare_images(path, "pf_rev.ppm")
    psnr_ref = {t: p for t, p in images}
    watermark = wm.get("kind") != "exact"
    if not watermark:
        print("   цикл без потерь точный: ватермарка нет, PSNR считается "
              "относительно исходного файла")
    else:
        print("   цикл без потерь дал расхождение (%s): сборка наносит "
              "ватермарк, PSNR будет считаться относительно кадра после "
              "цикла без потерь" % wm.get("kind"))
        for t, p in images:
            jp2, ppm = "ref_lossless_%s.jp2" % t, "ref_lossless_%s.ppm" % t
            b.run(CODECS["fv"]["enc"], ["-i", p, "-o", jp2, "-a", "rev",
                                        "-c", CODE_BLOCK, "-l", LEVELS],
                  "ref_lossless_enc_" + t)
            b.run(CODECS["fv"]["dec"], dec_args(jp2, ppm),
                  "ref_lossless_dec_" + t)
            if size_of(ppm):
                psnr_ref[t] = ppm

    for junk in ("pf_q85.jp2", "pf_def.jp2", "pf_q95cr.jp2", "pf_rev.jp2",
                 "pf_rev.ppm"):
        try:
            os.remove(junk)
        except OSError:
            pass

    return {"geom": geom, "sdk": r.get("sdk", ""), "gpu": r.get("gpu", ""),
            "default_q": default_q, "watermark": watermark,
            "psnr_ref": psnr_ref}


# ---------------------------------------------------------------------------
# calibration of -cr
# ---------------------------------------------------------------------------

def calibrate_cr(b, path, target, q, name, seed=None, natural=None):
    """Find the -cr that lands on the target size.

    The parameter is a ratio against the raw frame, so the first guess is
    raw/target, or the value found for a previous variant: the ratio needed
    barely depends on the quality, so one seed saves most of the iterations.
    """
    g = read_ppm(path)
    raw = g[0] * g[1] * g[2] * g[3]
    if natural is not None and natural < target * 0.99:
        # Quantisation alone has already compressed harder than asked, and rate
        # control cannot make a file bigger: a normal outcome, not a failure.
        # The threshold is deliberately not the calibration tolerance: when the
        # natural size only just reaches the target, rate control still shifts
        # it, so that case has to be calibrated rather than assumed.
        return {"cr": raw / float(target), "bytes": natural,
                "miss": (natural - target) / float(target), "steps": 0,
                "not_binding": True}
    cr = seed if seed else raw / float(target)
    best, hist = None, []
    for i in range(CALIB_STEPS):
        out = "cal_%s.jp2" % name
        b.run(CODECS["fv"]["enc"], fv_enc(path, out, q=q, cr=cr),
              "cal_%s_%d" % (name, i))
        if b.dry_run:
            return {"cr": cr, "bytes": target, "miss": 0.0, "steps": 0}
        got = size_of(out)
        if not got:
            return {"error": "файл не получился"}
        miss = (got - target) / float(target)
        hist.append({"cr": round(cr, 4), "bytes": got, "miss": round(miss, 5)})
        if best is None or abs(miss) < abs(best["miss"]):
            best = {"cr": cr, "bytes": got, "miss": miss}
        if abs(miss) <= CALIB_TOL:
            break
        cr = cr * (got / float(target))
    best["steps"] = len(hist)
    best["hist"] = hist
    return best


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def measure_variant(b, rec, tag, path, item, target, psnr_ref, reps, stage_runs,
                    decode):
    label = "%s_%s" % (tag, item["variant"].replace("+", "_"))
    b.pr.set_task("%s, %s" % (tag, item["variant"]))
    ref = "ref_%s.jp2" % label

    r0 = b.run(CODECS["fv"]["enc"],
               fv_enc(path, ref, q=item["q"], cr=item["cr"], extra=["-info"]),
               label + "_prep")
    got = size_of(ref)
    warn = []
    if item["q"] is not None and r0.get("quality_printed") is not None \
            and abs(r0["quality_printed"] - item["q"]) > Q_PRINT_TOL:
        warn.append("запрошено качество %s, напечатано %s"
                    % (item["q"], r0["quality_printed"]))
    if item["cr"] is None and not r0.get("pcrd_disabled"):
        warn.append("-cr не задан, но PCRD не помечен выключенным")
    if warn:
        print("      ВНИМАНИЕ (%s): %s" % (item["variant"], "; ".join(warn)))

    stages = {}
    order = []
    for name, ms in r0.get("stages", []):
        stages.setdefault(name, []).append(ms)
        order.append(name)
    for i in range(max(0, stage_runs - 1)):
        rs = b.run(CODECS["fv"]["enc"],
                   fv_enc(path, "tmp.jp2", q=item["q"], cr=item["cr"],
                          extra=["-info"]), "%s_stages_%d" % (label, i))
        for name, ms in rs.get("stages", []):
            stages.setdefault(name, []).append(ms)
            if name not in order:
                order.append(name)

    probe = b.run(CODECS["fv"]["enc"],
                  fv_enc(path, "tmp.jp2", q=item["q"], cr=item["cr"],
                         extra=["-repeat", PROBE_FRAMES, "-discard"]),
                  label + "_E_probe")
    base = probe.get("fps") or 100.0
    n = max(20, int(base * MEASURE_S))
    enc = []
    for i in range(reps):
        r = b.run(CODECS["fv"]["enc"],
                  fv_enc(path, "tmp.jp2", q=item["q"], cr=item["cr"],
                         extra=["-repeat", n, "-discard"]),
                  "%s_E_%d" % (label, i))
        if r.get("fps"):
            enc.append(r["fps"])

    dec = []
    if decode:
        rp = b.run(CODECS["fv"]["dec"],
                   dec_args(ref, "tmp.ppm", ["-repeat", PROBE_FRAMES,
                                             "-discard"]), label + "_D_probe")
        nd = max(20, int((rp.get("fps") or 100.0) * MEASURE_S))
        for i in range(reps):
            r = b.run(CODECS["fv"]["dec"],
                      dec_args(ref, "tmp.ppm", ["-repeat", nd, "-discard"]),
                      "%s_D_%d" % (label, i))
            if r.get("fps"):
                dec.append(r["fps"])

    out_ppm = "chk_%s.ppm" % label
    b.run(CODECS["fv"]["dec"], dec_args(ref, out_ppm), label + "_check")
    qual = (compare_images(psnr_ref, out_ppm) if size_of(out_ppm)
            else {"kind": "нет выходного файла"})
    try:
        os.remove(out_ppm)
    except OSError:
        pass

    row = {"image": tag, "variant": item["variant"], "q": item["q"],
           "cr": item["cr"], "target_bytes": target, "bytes": got,
           "miss_pct": (100.0 * (got - target) / target) if got else None,
           "not_binding": bool(item.get("not_binding")),
           "enc_fps": median(enc), "enc_spread_pct": spread_pct(enc),
           "enc_runs": len(enc),
           "dec_fps": median(dec) if dec else None,
           "psnr": qual.get("psnr"), "psnr_kind": qual.get("kind"),
           "stages": [(nm, median(stages[nm])) for nm in order],
           "calib": item.get("calib"), "warn": warn}
    rec.add("row", **row)          # на диск сразу, до печати
    print("      %-9s q %-7s cr %-9s %9d Б  промах %6.3f %%  кодер %7.1f  "
          "PSNR %s%s"
          % (item["variant"],
             ("%.2f" % item["q"]) if item["q"] is not None else "-",
             ("%.3f" % item["cr"]) if item["cr"] is not None else "-",
             got or 0, row["miss_pct"] or 0.0, row["enc_fps"] or 0,
             ("%.2f" % row["psnr"]) if row.get("psnr") else "-",
             "   (PCRD нечего резать)" if row["not_binding"] else ""))
    sys.stdout.flush()
    return row


def plan_runs(images, reps, stage_runs, decode):
    per_variant = 1 + max(0, stage_runs - 1) + 1 + reps + 1
    if decode:
        per_variant += 1 + reps
    variants = 2 + len(Q_VARIANTS)          # q85, cr-only, q90+cr, q95+cr
    calib = 2 + 2 * len(Q_VARIANTS)         # редко больше двух шагов
    return len(images) * (len(Q_LADDER) + variants * per_variant + calib) + 8


def environment(device=0):
    env = {"date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "os": "%s %s" % (platform.system(), platform.release()),
           "python": platform.python_version(),
           "bench_version": BENCH_VERSION,
           "code_block": CODE_BLOCK, "levels": LEVELS}
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version",
             "--format=csv,noheader", "-i", str(device)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        line = out.stdout.decode("utf-8", "replace").strip().splitlines()
        if line:
            parts = [p.strip() for p in line[0].split(",")]
            env["gpu"] = parts[0]
            if len(parts) > 1:
                env["driver"] = parts[1]
    except Exception:
        pass
    return env


# ---------------------------------------------------------------------------
# report: built from results.jsonl, so it can be rebuilt at any moment
# ---------------------------------------------------------------------------

def build_report(outdir):
    path = os.path.join(outdir, "results.jsonl")
    if not os.path.exists(path):
        print("нет %s" % path)
        return 2
    env, rows, notes, ladder = {}, [], [], []
    runs = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        kind = r.get("kind")
        if kind == "row":
            rows.append(r)
        elif kind == "run":
            runs += 1
        elif kind == "environment":
            env = r
        elif kind == "note":
            notes.append(r.get("text", ""))
        elif kind == "ladder":
            ladder.append(r)

    cols = ["image", "variant", "q", "cr", "target_bytes", "bytes", "miss_pct",
            "not_binding", "enc_fps", "enc_spread_pct", "dec_fps", "psnr",
            "psnr_kind"]
    with open(os.path.join(outdir, "results.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";",
                           extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(outdir, "results.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"environment": env, "ladder": ladder, "rows": rows,
                   "notes": notes, "runs": runs}, fh, indent=1,
                  ensure_ascii=False)

    L = ["Скорость режима PCRD при заданном размере файла, %s" % BENCH_VERSION]
    for k in ("date", "gpu", "driver", "os", "python"):
        if env.get(k):
            L.append("%-14s %s" % (k + ":", env[k]))
    L.append("прогонов: %d" % runs)
    L.append("")
    for n in notes:
        L.append("замечание: " + n)
    if notes:
        L.append("")
    if ladder:
        L.append("Лестница качества без управления размером")
        L.append("%-4s %-5s %12s %10s" % ("кадр", "q", "байт", "степень"))
        for r in ladder:
            L.append("%-4s %-5s %12d %9.2f:1"
                     % (r["image"], r["q"], r["bytes"], r["ratio"]))
        L.append("")
    hdr = ("%-4s %-9s %7s %9s %10s %8s %9s %7s %8s"
           % ("кадр", "вариант", "q", "cr", "байт", "промах%", "кодер fps",
              "разброс", "PSNR"))
    L.append(hdr)
    L.append("-" * len(hdr))
    for r in rows:
        L.append("%-4s %-9s %7s %9s %10s %8s %9s %7s %8s"
                 % (r["image"], r["variant"],
                    ("%.2f" % r["q"]) if r.get("q") is not None else "-",
                    ("%.3f" % r["cr"]) if r.get("cr") is not None else "-",
                    r.get("bytes") or "-",
                    ("%.3f" % r["miss_pct"]) if r.get("miss_pct") is not None
                    else "-",
                    ("%.1f" % r["enc_fps"]) if r.get("enc_fps") else "-",
                    ("%.1f" % r["enc_spread_pct"])
                    if r.get("enc_spread_pct") is not None else "-",
                    ("%.2f" % r["psnr"]) if r.get("psnr") else "-"))
    # главный вывод считается прямо здесь, а не в голове у читателя
    L.append("")
    L.append("Во сколько раз медленнее эталона (эталон — только качество 85)")
    for tag in sorted({r["image"] for r in rows}):
        base = [r for r in rows if r["image"] == tag and r["variant"] == "q85"]
        if not base or not base[0].get("enc_fps"):
            continue
        b0 = base[0]["enc_fps"]
        for r in rows:
            if r["image"] != tag or r["variant"] == "q85" or not r.get("enc_fps"):
                continue
            L.append("   %-4s %-9s %.2f раза   (PSNR %s против %s)"
                     % (tag, r["variant"], b0 / r["enc_fps"],
                        ("%.2f" % r["psnr"]) if r.get("psnr") else "-",
                        ("%.2f" % base[0]["psnr"]) if base[0].get("psnr")
                        else "-"))
    nb = [r for r in rows if r.get("not_binding")]
    if nb:
        L.append("")
        L.append("Строки, где PCRD нечего было резать: квантование уже сжало "
                 "сильнее, чем просили. Это нормальный исход, а не сбой.")
        for r in nb:
            L.append("   %s %s: %d байт при цели %d"
                     % (r["image"], r["variant"], r["bytes"],
                        r["target_bytes"]))
    wr = [r for r in rows if r.get("warn")]
    if wr:
        L.append("")
        L.append("ПРЕДУПРЕЖДЕНИЯ:")
        for r in wr:
            L.append("   %s %s: %s" % (r["image"], r["variant"],
                                       "; ".join(r["warn"])))
    L.append("")
    L.append("Разбор по стадиям, один кадр под -info, медианы в мс")
    L.append("(-info вставляет синхронизации между стадиями, поэтому сумма "
             "выше реального времени кадра: читать как доли, не как итог)")
    for r in rows:
        if not r.get("stages"):
            continue
        L.append("")
        L.append("%s %s" % (r["image"], r["variant"]))
        tot = sum(v for _, v in r["stages"]) or 1.0
        for name, ms in r["stages"]:
            L.append("   %-42s %7.2f мс  %5.1f %%" % (name, ms,
                                                      100.0 * ms / tot))
    text = "\n".join(L) + "\n"
    with open(os.path.join(outdir, "summary.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(text)
    return text


def main():
    ap = argparse.ArgumentParser(
        description="Скорость режима PCRD: качество, режим PCRD и то и другое "
                    "вместе при одном и том же размере файла.")
    ap.add_argument("--q-variants", default=",".join(str(q) for q in Q_VARIANTS),
                    help="качества, которые сочетаются с -cr, через запятую; "
                         "по умолчанию %s" % ",".join(str(q) for q in Q_VARIANTS))
    ap.add_argument("--reps", type=int, default=2,
                    help="повторов каждого измерения, по умолчанию 2")
    ap.add_argument("--stage-runs", type=int, default=2,
                    help="прогонов на разбор по стадиям, по умолчанию 2")
    ap.add_argument("--decode", action="store_true",
                    help="мерить ещё и декодирование (к скорости режима PCRD "
                         "отношения не имеет, по умолчанию выключено)")
    ap.add_argument("--run-cost", type=float, default=DEFAULT_RUN_COST_S,
                    help="ожидаемая длительность одного запуска в секундах, для "
                         "оценки времени; уточняется по ходу")
    ap.add_argument("--device", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="только проверки, ничего не меряет")
    ap.add_argument("--report", metavar="DIR",
                    help="пересобрать отчёт из results.jsonl готовой папки")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    if args.q_variants:
        try:
            qv = [float(x) for x in args.q_variants.split(",") if x.strip()]
        except ValueError:
            print("не разобрал --q-variants: %s" % args.q_variants)
            return 2
        bad = [q for q in qv if q > 100.0]
        if bad:
            print("качество выше 100 в этот тест не берём: %s"
                  % ", ".join("%g" % q for q in bad))
            return 2
        globals()["Q_VARIANTS"] = qv
        globals()["Q_LADDER"] = sorted({int(Q_REF)} | {int(q) for q in qv}
                                       | {100})

    if args.report:
        text = build_report(args.report)
        if isinstance(text, str):
            print(text)
            return 0
        return text

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = "pcrd_" + stamp + (("_" + args.label) if args.label else "")
    os.makedirs(outdir, exist_ok=True)

    planned = plan_runs(IMAGES, args.reps, args.stage_runs, args.decode)
    pr = Progress(planned, args.run_cost)
    rec = Recorder(outdir)
    b = Bench(outdir, rec, pr, args.dry_run)

    print("Скорость режима PCRD при заданном размере файла, %s" % BENCH_VERSION)
    print("папка: %s" % outdir)
    print("начало: %s" % now_hm())
    print("запусков примерно %d, при %.0f с на запуск это около %s"
          % (planned, args.run_cost, hms(planned * args.run_cost)))
    print("результаты пишутся построчно в %s — прогон можно останавливать "
          "в любой момент" % os.path.join(outdir, "results.jsonl"))
    sys.stdout.flush()

    pre = preflight(b, IMAGES)
    if pre is None:
        print("\nпроверки не прошли, ничего не измерено")
        rec.close()
        return 1
    if args.selftest:
        print("\nпроверки прошли, останавливаюсь как просили")
        rec.close()
        return 0

    env = environment(args.device)
    env["sdk"] = pre.get("sdk", "")
    rec.add("environment", **env)
    if pre.get("watermark"):
        rec.add("note", text="сборка наносит ватермарк, PSNR считается "
                             "относительно кадра после цикла без потерь")
    if pre.get("default_q"):
        rec.add("note", text="без -q кодер работает с качеством %s, поэтому "
                             "строка cr-only это «качество %s плюс -cr»"
                             % (pre["default_q"], pre["default_q"]))

    for tag, path in IMAGES:
        geom = pre["geom"][tag]
        print("\n[1] %s: лестница качества без управления размером  [%s]"
              % (tag, now_hm()))
        pr.set_task("%s, лестница качества" % tag)
        natural = {}
        for q in Q_LADDER:
            out = "lad_%s_q%d.jp2" % (tag, q)
            r = b.run(CODECS["fv"]["enc"], fv_enc(path, out, q=q),
                      "ladder_%s_q%d" % (tag, q))
            n = size_of(out)
            qp = r.get("quality_printed")
            if n and qp is not None and abs(qp - q) > Q_PRINT_TOL:
                print("   q %-3d  кодер напечатал качество %s, точка "
                      "пропущена" % (q, qp))
                n = None
            if n:
                natural[q] = n
                rec.add("ladder", image=tag, q=q, bytes=n,
                        ratio=geom["raw_bytes"] / float(n))
                print("   q %-3d  %10d байт  %6.2f:1"
                      % (q, n, geom["raw_bytes"] / float(n)))
            elif not args.dry_run:
                print("   q %-3d  файла нет, см. %s" % (q, r.get("log")))
            try:
                os.remove(out)
            except OSError:
                pass

        target = natural.get(int(Q_REF))
        if not target:
            print("   цель не определена: нет файла при q %g, кадр пропущен"
                  % Q_REF)
            continue

        print("\n[2] %s: измерение при размере %d байт (%.2f:1)  [%s]"
              % (tag, target, geom["raw_bytes"] / float(target), now_hm()))
        pr.beat(force=True)

        plan = [{"variant": "q85", "q": Q_REF, "cr": None, "calib": None}]

        c = calibrate_cr(b, path, target, None, "%s_cronly" % tag,
                         natural=natural.get(int(pre.get("default_q") or 0)))
        if "error" in c:
            print("      только -cr: не вышло, %s" % c["error"])
        else:
            print("      только -cr:  cr = %.4f, %d байт, промах %.3f %%, "
                  "шагов %d" % (c["cr"], c["bytes"], 100 * c["miss"],
                                c["steps"]))
            plan.append({"variant": "cr-only", "q": None, "cr": c["cr"],
                         "calib": c, "not_binding": c.get("not_binding")})

        seed = c.get("cr") if "error" not in c else None
        for q in Q_VARIANTS:
            if q not in natural:
                print("      q %-3d пропущено: нет размера в лестнице" % q)
                continue
            cq = calibrate_cr(b, path, target, q, "%s_q%d" % (tag, q),
                              seed=seed, natural=natural[q])
            if "error" in cq:
                print("      q %-3d + cr: не вышло, %s" % (q, cq["error"]))
                continue
            print("      q %-3d + cr = %.4f, %d байт, промах %.3f %%, шагов %d%s"
                  % (q, cq["cr"], cq["bytes"], 100 * cq["miss"], cq["steps"],
                     "   (PCRD нечего резать)" if cq.get("not_binding") else ""))
            plan.append({"variant": "q%d+cr" % q, "q": float(q),
                         "cr": cq["cr"], "calib": cq,
                         "not_binding": cq.get("not_binding")})

        for item in plan:
            measure_variant(b, rec, tag, path, item, target,
                            pre["psnr_ref"].get(tag, path), args.reps,
                            args.stage_runs, args.decode)

    rec.close()
    text = build_report(outdir)
    print("\n" + (text if isinstance(text, str) else ""))
    print("прогонов: %d, всего времени %s, конец %s"
          % (pr.done, hms(time.time() - pr.t0), now_hm()))
    print("всё в папке %s" % outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
