#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# j2k-point-repeat-02.py
# версия 2026-08-31.1 от 31.08.2026, заменяет j2k-point-repeat-01.py
#
# ЧТО ИЗМЕНИЛОСЬ В 02
#
# Версия 01 падала на первом же запуске: класс датчиков подставляется в
# bench вместо его собственного измерителя мощности, а bench после запуска
# читает у него поле idle_w - потребление карты вхолостую. У моего класса
# такого поля не было.
#
# Починено не добавлением одного поля, а по существу: класс датчиков теперь
# НАСЛЕДУЕТСЯ от Power из самого bench. Всё, что есть у оригинала, есть и у
# него; переопределены только опрос и итог. Своя копия чужого набора полей
# разъехалась бы с оригиналом на первой же его правке - что и произошло.
#
# Заодно потребление вхолостую теперь измеряется по-настоящему: три секунды
# до начала прогона, пока ничего не запущено. Оно нужно не для отчёта, а
# для той же картины 'кормили карту или нет'.
#
# ЗАЧЕМ ЭТОТ СКРИПТ
#
# В прогоне cmp_20260831_122512 одна точка дала пять запусков подряд:
#
#     540,6   539,4   309,9   310,2   309,6      кадров в секунду
#     164     168     136     135     136        ватт на карте
#
# Это не разброс. Внутри каждой группы совпадение до десятых, между группами
# разница в 1,74 раза, и у медленной группы карта берёт заметно меньше ватт.
# Медиана по пяти запускам выбирает ту группу, где запусков оказалось больше,
# то есть отвечает не на тот вопрос. Публиковать такое число нельзя.
#
# Скрипт меряет одну названную точку много раз и отвечает на три вопроса:
#
#   1. Значения собираются в одну кучку или в две?
#   2. Если в две — что при этом делает карта: частота, температура,
#      загрузка, мощность? Троттлинг и голодание выглядят по-разному.
#      При троттлинге частота падает, температура высокая, мощность у
#      предела. При голодании падает и мощность, и загрузка, а температура
#      обычная: карте просто не подают работу.
#   3. Это свойство точки или состояние машины? Для этого рядом меряется
#      контрольная точка того же вида, через одну. Если проседают обе -
#      виновата машина. Если только спорная - дело в ней самой.
#
# ЧТО НУЖНО РЯДОМ
#
# Та же папка, где лежат экзешники и где делался прогон: bin\x64\Release.
# Скрипт берёт команды и разбор вывода из bench-05.py, лежащего рядом, -
# именно поэтому измерение получается тем же самым, а не похожим. Эталонные
# потоки (nv_ref_2k_irrev.jp2 и прочие) нужны готовые: их делает bench-05.py,
# и после его прогона они уже там.
#
# КАК ЗАПУСКАТЬ
#
#     python j2k-point-repeat-02.py            показывает это и ничего не меряет
#     python j2k-point-repeat-02.py --go       спорная точка, 20 запусков
#
# Ctrl-C останавливает в любой момент: всё измеренное уже на диске.

import argparse
import datetime
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time

SCRIPT_NAME = "j2k-point-repeat-02.py"      # совпадает с именем файла
VERSION = "2026-08-31.1"                    # печатается в каждую строку

# Спорная точка и контрольная к ней. Контрольная - соседняя по сетке точка
# того же кодека и той же задачи: она меряется через одну и служит свидетелем
# состояния машины.
POINT = ("nv", "D", "2k", "irrev", 8, 1)
CONTROL = ("nv", "D", "2k", "irrev", 8, 2)

# Столько кадров было в том прогоне на этой точке. Берём столько же, чтобы
# условия совпадали: длина запуска на числа влияет, и смешивать два вопроса
# в одном измерении не надо.
FRAMES = 4288

RUNS = 20                                   # запусков спорной точки
GAP_LIMIT = 15.0                            # с какого разрыва считаем, что кучки две
HEARTBEAT_S = 300.0
SAMPLE_MS = 200                             # как часто опрашивать карту


# ---------------------------------------------------------------------------
# датчики карты
# ---------------------------------------------------------------------------

def make_sensors(bench):
    """Класс датчиков, наследующий измеритель мощности самого bench.

    Так и надо: bench подставляет этот объект себе и потом читает у него свои
    поля - в версии 01 он прочитал idle_w, которого у моей копии не было, и
    прогон упал на первом же запуске. Наследник знает всё, что знает оригинал,
    а переопределены только опрос карты и итог.

    Опрашиваем четыре величины вместо одной: одних ватт мало, чтобы отличить
    голодание от троттлинга. При голодании падают и мощность, и загрузка, а
    температура обычная. При троттлинге падает частота, температура высокая,
    мощность у предела.
    """
    base = getattr(bench, "Power", object)

    class Sensors(base):
        FIELDS = ("power.draw", "clocks.sm", "temperature.gpu",
                  "utilization.gpu")

        def __init__(self, device=0):
            try:
                base.__init__(self, device)
            except TypeError:
                base.__init__(self)
            # На случай, если у оригинала этих полей нет: свои заводим сами,
            # чужие не трогаем.
            if not hasattr(self, "idle_w"):
                self.idle_w = None
            self.device = device
            self.proc = None
            self.rows = []
            self.last = {}
            self._thread = None

        def _reader(self):
            for line in self.proc.stdout:
                parts = line.decode("ascii", "replace").strip().split(",")
                if len(parts) != len(self.FIELDS):
                    continue
                try:
                    self.rows.append([float(x) for x in parts])
                except ValueError:
                    pass

        def start(self):
            self.rows = []
            self.last = {}
            try:
                self.proc = subprocess.Popen(
                    ["nvidia-smi", "-i", str(self.device),
                     "--query-gpu=" + ",".join(self.FIELDS),
                     "--format=csv,noheader,nounits", "-lms", str(SAMPLE_MS)],
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
            rows = self.rows
            if not rows:
                return None
            # Первые и последние доли секунды - это старт и завершение
            # процесса, карта тогда ещё или уже не работает. Отрезаем по
            # десятой части с каждого конца, если сэмплов достаточно.
            if len(rows) >= 20:
                cut = len(rows) // 10
                rows = rows[cut:len(rows) - cut]
            for i, name in enumerate(self.FIELDS):
                vals = sorted(r[i] for r in rows)
                self.last[name] = vals[len(vals) // 2]
            self.last["samples"] = len(rows)
            return self.last.get("power.draw")

        def measure_idle(self, seconds=3.0):
            """Потребление карты, пока ничего не запущено."""
            self.start()
            time.sleep(seconds)
            w = self.stop()
            self.idle_w = w
            return w

    return Sensors


# ---------------------------------------------------------------------------
# признак жизни
# ---------------------------------------------------------------------------

class Heartbeat(object):
    def __init__(self):
        self.what = ""
        self.stop_flag = threading.Event()
        self.thread = None

    def set(self, what):
        self.what = what

    def start(self):
        def loop():
            while not self.stop_flag.wait(HEARTBEAT_S):
                print("   %s ещё работает: %s"
                      % (datetime.datetime.now().strftime("%H:%M:%S"),
                         self.what or "запуск"))
                sys.stdout.flush()
        self.thread = threading.Thread(target=loop)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.stop_flag.set()


HEART = Heartbeat()


# ---------------------------------------------------------------------------
# bench-05.py рядом: берём у него команды и разбор вывода
# ---------------------------------------------------------------------------

def load_bench(folder):
    """Подключает bench-05.py как модуль.

    Так измерение получается тем же самым, а не похожим: и строка команды, и
    разбор вывода, и запись результата - его. Своя копия этих трёх вещей
    разъехалась бы с оригиналом на первой же правке.
    """
    names = sorted(f for f in os.listdir(folder)
                   if f.startswith("bench-") and f.endswith(".py"))
    if not names:
        return None, "рядом нет bench-NN.py"
    path = os.path.join(folder, names[-1])
    spec = importlib.util.spec_from_file_location("bench_mod", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        return None, "%s не подключается: %s" % (names[-1], e)
    for need in ("Bench", "dec_args", "enc_args", "CODECS", "parse_output"):
        if not hasattr(mod, need):
            return None, "в %s нет %s" % (names[-1], need)
    return mod, names[-1]


def ref_name(codec, tag, alg):
    return "%s_ref_%s_%s.jp2" % (codec, tag, alg)


def build_args(bench, pt, frames):
    """Команда ровно та же, что в прогоне: многопоточная точка, -async."""
    codec, direction, tag, alg, th, ba = pt
    extra = ["-repeat", frames, "-async", "-thread", th, "-b", ba]
    if direction == "D":
        return bench.dec_args(ref_name(codec, tag, alg), extra, codec)
    image = "%s_wild.ppm" % tag
    return bench.enc_args(codec, image, alg, None, extra)


def name_of(pt):
    codec, direction, tag, alg, th, ba = pt
    return "%s %s %s %s %dx%d" % (codec, direction, tag, alg, th, ba)


# ---------------------------------------------------------------------------
# разбор результата: одна кучка или две
# ---------------------------------------------------------------------------

def median(values):
    v = sorted(values)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def split_groups(values):
    """Ищет самый большой относительный разрыв в упорядоченном ряду.

    Возвращает (нижняя группа, верхняя группа, разрыв в процентах). Если
    разрыв меньше GAP_LIMIT, считаем, что кучка одна, и верхняя группа пуста.
    """
    v = sorted(values)
    if len(v) < 4:
        return v, [], 0.0
    best_i, best_gap = None, 0.0
    for i in range(len(v) - 1):
        if v[i] <= 0:
            continue
        gap = 100.0 * (v[i + 1] - v[i]) / v[i]
        if gap > best_gap:
            best_i, best_gap = i, gap
    if best_i is None or best_gap < GAP_LIMIT:
        return v, [], best_gap
    return v[:best_i + 1], v[best_i + 1:], best_gap


def verdict(rows, pt, control):
    """Что из этого следует. Печатается в конце и пишется в отчёт."""
    out = []
    main = [r for r in rows if r["point"] == name_of(pt) and r.get("fps")]
    ctrl = [r for r in rows if r["point"] == name_of(control) and r.get("fps")]

    def block(title, data):
        out.append("")
        out.append(title)
        if not data:
            out.append("   не измерено ни одного запуска")
            return None, None
        vals = [r["fps"] for r in data]
        low, high, gap = split_groups(vals)
        out.append("   запусков: %d, от %.1f до %.1f кадров в секунду"
                   % (len(vals), min(vals), max(vals)))
        if not high:
            out.append("   ОДНА КУЧКА: самый большой разрыв в ряду %.1f %%, "
                       "это меньше порога в %.0f %%." % (gap, GAP_LIMIT))
            out.append("   Медиана %.1f - её и можно публиковать."
                       % median(vals))
            return median(vals), None
        out.append("   ДВЕ КУЧКИ, разрыв между ними %.1f %%:" % gap)
        out.append("     медленная  %2d запусков, медиана %.1f"
                   % (len(low), median(low)))
        out.append("     быстрая    %2d запусков, медиана %.1f"
                   % (len(high), median(high)))
        out.append("   Медиана по всем запускам просто выбирает ту кучку,")
        out.append("   где запусков больше. Это не ответ.")
        return median(low), median(high)

    lo_m, hi_m = block("СПОРНАЯ ТОЧКА: %s" % name_of(pt), main)
    if ctrl:
        block("КОНТРОЛЬНАЯ ТОЧКА: %s" % name_of(control), ctrl)

    # что делала карта в каждой кучке
    if main and hi_m is not None:
        out.append("")
        out.append("ЧТО ДЕЛАЛА КАРТА")
        out.append("   кучка        ватт   МГц   °C  загрузка")
        mid = (lo_m + hi_m) / 2.0
        for label, sel in (("медленная", [r for r in main
                                          if r["fps"] < mid]),
                           ("быстрая", [r for r in main if r["fps"] >= mid])):
            def med(field):
                vals = [r[field] for r in sel if r.get(field) is not None]
                return median(vals)
            w, c, t, u = (med("power_w"), med("clock_mhz"),
                          med("temp_c"), med("util_pct"))

            def f(v, fmt):
                return (fmt % v) if v is not None else "    -"
            out.append("   %-11s %s %s %s %s"
                       % (label, f(w, "%6.0f"), f(c, "%5.0f"),
                          f(t, "%4.0f"), f(u, "%8.0f")))
        out.append("")
        out.append("   Читается так. Если у медленной кучки ниже и мощность,")
        out.append("   и загрузка, а температура обычная - карту не кормили,")
        out.append("   у процесса отняли процессорное время. Если ниже")
        out.append("   частота при высокой температуре и мощности у предела -")
        out.append("   это троттлинг, и тогда виновата не посторонняя")
        out.append("   нагрузка, а охлаждение.")

    # машина или точка
    if main and ctrl and hi_m is not None:
        out.append("")
        out.append("ЭТО МАШИНА ИЛИ САМА ТОЧКА")
        mid = (lo_m + hi_m) / 2.0
        slow_rounds = set(r["round"] for r in main if r["fps"] < mid)
        cv = [r["fps"] for r in ctrl]
        c_low, c_high, c_gap = split_groups(cv)
        if not c_high:
            out.append("   У контрольной точки кучка одна (разрыв %.1f %%)."
                       % c_gap)
            out.append("   Значит в те же круги, когда спорная точка")
            out.append("   проседала, соседняя работала ровно, и дело не в")
            out.append("   состоянии машины, а в самой точке.")
        else:
            c_mid = (median(c_low) + median(c_high)) / 2.0
            c_slow = set(r["round"] for r in ctrl if r["fps"] < c_mid)
            both = slow_rounds & c_slow
            out.append("   Кругов, где просела спорная точка: %d"
                       % len(slow_rounds))
            out.append("   Кругов, где просела контрольная:   %d"
                       % len(c_slow))
            out.append("   Совпало кругов: %d" % len(both))
            if len(both) >= 0.7 * max(len(slow_rounds), 1):
                out.append("   Проседают вместе - виновата машина.")
            else:
                out.append("   Проседают порознь - дело не в машине.")
    return out


# ---------------------------------------------------------------------------
# запуск
# ---------------------------------------------------------------------------

def usage():
    print("=" * 72)
    print(" %s, версия %s" % (SCRIPT_NAME, VERSION))
    print(" Одна точка, много запусков: одна кучка значений или две")
    print("=" * 72)
    print("")
    print(" Ничего не измерено: прогон просится по имени.")
    print("")
    print(" ЗАЧЕМ")
    print("   В прогоне 31.08 точка %s дала" % name_of(POINT))
    print("   540, 539, 310, 310, 310 кадров в секунду. Медиана выбрала")
    print("   310, но 540 - это то, что стоит в опубликованной статье.")
    print("   Двадцать запусков покажут, какая из двух кучек настоящая.")
    print("")
    print(" КАК ЗАПУСКАТЬ")
    print("   python %s --go" % SCRIPT_NAME)
    print("")
    print("   Больше ничего передавать не надо. Меряется %s," % name_of(POINT))
    print("   через одну - контрольная %s." % name_of(CONTROL))
    print("   %d запусков по %d кадров, около %d минут."
          % (RUNS, FRAMES, int(RUNS * 2 * 40 / 60.0)))
    print("")
    print("   Если понадобится другое: --runs, --frames, --point,")
    print("   --no-control. Видно по -h.")
    print("")
    print(" ЧТО ДОЛЖНО ЛЕЖАТЬ РЯДОМ")
    folder = os.path.abspath(".")
    what = [("bench-06.py", "команды и разбор вывода берутся у него"),
            ("nvj2kDecoderSample" + (".exe" if os.name == "nt" else ""),
             "измеряемая программа"),
            (ref_name(POINT[0], POINT[2], POINT[3]),
             "эталонный поток, его делает bench-NN.py")]
    for name, why in what:
        there = os.path.exists(os.path.join(folder, name))
        print("   %-28s %s   %s"
              % (name, "нашёлся" if there else "НЕ НАЙДЕН", why))
    print("")
    print("   Папка: %s" % folder)
    print("")
    print(" Ctrl-C останавливает в любой момент: всё измеренное уже на диске.")
    return 1


def parse_point(text, default):
    """Точка строкой: 'nv D 2k irrev 8x1'."""
    if not text:
        return default
    parts = text.replace("x", " ").replace("X", " ").split()
    if len(parts) != 6:
        return None
    codec, direction, tag, alg, th, ba = parts
    try:
        return (codec, direction.upper(), tag, alg, int(th), int(ba))
    except ValueError:
        return None


def main():
    if len(sys.argv) == 1:
        return usage()

    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--go", action="store_true", help="мерить")
    ap.add_argument("--runs", type=int, default=RUNS,
                    help="запусков спорной точки, по умолчанию %d" % RUNS)
    ap.add_argument("--frames", type=int, default=FRAMES,
                    help="кадров на запуск, по умолчанию %d - столько же, "
                         "сколько было в прогоне" % FRAMES)
    ap.add_argument("--point", default="",
                    help="точка строкой, например 'nv D 2k irrev 8x1'")
    ap.add_argument("--control", default="",
                    help="контрольная точка тем же способом")
    ap.add_argument("--no-control", action="store_true",
                    help="мерить только спорную точку")
    ap.add_argument("--dir", default=".", help="папка с программами")
    args = ap.parse_args()

    folder = os.path.abspath(args.dir)
    print("%s, версия %s" % (SCRIPT_NAME, VERSION))
    print("Начато: %s"
          % datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    print("Папка:  %s" % folder)

    pt = parse_point(args.point, POINT)
    ctrl = parse_point(args.control, CONTROL)
    if pt is None or ctrl is None:
        print("")
        print("Точка пишется шестью словами: кодек, направление, кадр,")
        print("режим, потоки, пачка. Например: 'nv D 2k irrev 8x1'.")
        return 1
    if args.no_control:
        ctrl = None

    if not args.go:
        print("")
        print("Ничего не запрошено. Добавьте --go.")
        return 1

    bench, why = load_bench(folder)
    if bench is None:
        print("")
        print("Не получилось: %s." % why)
        print("Скрипт кладётся туда же, где лежит bench-05.py и экзешники, -")
        print("в bin\\x64\\Release. Ничего не измерено.")
        return 1
    print("Команды и разбор вывода взяты из %s" % why)

    missing = []
    for p in ([pt] + ([ctrl] if ctrl else [])):
        codec, direction, tag, alg = p[:4]
        need = (ref_name(codec, tag, alg) if direction == "D"
                else "%s_wild.ppm" % tag)
        if not os.path.exists(os.path.join(folder, need)):
            missing.append(need)
        exe = bench.CODECS[codec]["dec" if direction == "D" else "enc"]
        if not (os.path.exists(os.path.join(folder, exe))
                or os.path.exists(os.path.join(folder, exe + ".exe"))):
            missing.append(exe)
    if missing:
        print("")
        print("Не хватает файлов, и без них мерить нечего:")
        for m in sorted(set(missing)):
            print("   %s" % m)
        print("Эталонные потоки делает bench-05.py; после его прогона они")
        print("лежат в этой же папке. Ничего не измерено.")
        return 1

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(folder, "point_repeat_%s" % stamp)
    os.makedirs(outdir)
    jsonl = os.path.join(outdir, "runs.jsonl")
    report = os.path.join(outdir, "report.txt")

    order = [pt] + ([ctrl] if ctrl else [])
    total = args.runs * len(order)
    print("")
    print("ПРОГОН")
    print("Спорная точка:      %s" % name_of(pt))
    if ctrl:
        print("Контрольная точка:  %s (меряется через одну)" % name_of(ctrl))
    else:
        print("Контрольной точки нет: свидетеля состояния машины не будет.")
    print("Кадров на запуск:   %d, столько же было в прогоне" % args.frames)
    print("Запусков:           %d, около %d минут"
          % (total, int(total * 40 / 60.0)))
    print("Результаты пишутся сразу: %s" % jsonl)
    print("")

    b = bench.Bench(outdir)

    # Класс датчиков делается от Power самого bench, а не рядом с ним.
    Sensors = make_sensors(bench)

    # Потребление карты вхолостую: три секунды до начала, пока ничего не
    # запущено. Нужно как точка отсчёта - «не кормили» видно по тому,
    # насколько мощность под нагрузкой отошла от холостой.
    idle = Sensors()
    idle_w = idle.measure_idle(3.0)
    if idle_w is not None:
        print("Карта вхолостую: %.0f Вт" % idle_w)
    else:
        print("Карта вхолостую: nvidia-smi не отвечает, датчиков не будет")
    print("")

    HEART.start()
    rows = []
    t0 = time.time()
    try:
        with open(jsonl, "a", encoding="utf-8") as fh:
            for rnd in range(1, args.runs + 1):
                for p in order:
                    sensors = Sensors()
                    sensors.idle_w = idle_w
                    log = "%s_%s_%s_%s_%dx%d_r%02d" % (
                        p[0], p[1], p[2], p[3], p[4], p[5], rnd)
                    exe = bench.CODECS[p[0]]["dec" if p[1] == "D" else "enc"]
                    res = b.run(exe, build_args(bench, p, args.frames),
                                log, power=sensors)
                    row = {"script_version": VERSION, "round": rnd,
                           "point": name_of(p), "frames": args.frames,
                           "at": datetime.datetime.now().isoformat(
                               timespec="seconds"),
                           "fps": res.get("fps"),
                           "wall_s": res.get("wall_s"),
                           "cores": res.get("cores"),
                           "boundary": res.get("boundary"),
                           "power_w": sensors.last.get("power.draw"),
                           "clock_mhz": sensors.last.get("clocks.sm"),
                           "temp_c": sensors.last.get("temperature.gpu"),
                           "util_pct": sensors.last.get("utilization.gpu")}
                    rows.append(row)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())

                    def g(v, fmt):
                        return (fmt % v) if v is not None else "     -"
                    print("%s  круг %2d  %-22s %s  %s Вт %s МГц %s °C"
                          % (datetime.datetime.now().strftime("%H:%M:%S"),
                             rnd, name_of(p),
                             g(row["fps"], "%8.1f к/с"),
                             g(row["power_w"], "%5.0f"),
                             g(row["clock_mhz"], "%5.0f"),
                             g(row["temp_c"], "%4.0f")))
                    sys.stdout.flush()
    except KeyboardInterrupt:
        HEART.stop()
        b.close()
        print("")
        print("Остановлено по Ctrl-C. Измерено запусков: %d." % len(rows))
        print("Всё измеренное лежит в %s" % jsonl)
        print("Отчёт по тому, что есть, ниже.")
    else:
        HEART.stop()
        b.close()
        print("")
        print("Готово за %d минут." % int((time.time() - t0) / 60.0))

    lines = ["%s, версия %s" % (SCRIPT_NAME, VERSION),
             "Одна точка, много запусков",
             "сделано: %s"
             % datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
             "кадров на запуск: %d" % args.frames,
             "",
             "ВСЕ ЗАПУСКИ ПО ПОРЯДКУ",
             "  круг  точка                     к/с    ватт    МГц    °C  "
             "загрузка"]
    for r in rows:
        def g(v, fmt):
            return (fmt % v) if v is not None else "      -"
        lines.append("  %4d  %-22s %s %s %s %s %s"
                     % (r["round"], r["point"], g(r["fps"], "%7.1f"),
                        g(r["power_w"], "%7.0f"), g(r["clock_mhz"], "%6.0f"),
                        g(r["temp_c"], "%5.0f"), g(r["util_pct"], "%8.0f")))
    lines += verdict(rows, pt, ctrl or POINT)
    text = "\n".join(lines) + "\n"
    with open(report, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("")
    print("\n".join(lines[5:]))
    print("")
    print("Отчёт: %s" % report)
    print("Строки: %s" % jsonl)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("")
        print("Остановлено по Ctrl-C.")
        sys.exit(130)
