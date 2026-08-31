# -*- coding: utf-8 -*-
# make_charts-03.py
# версия 2026-08-31.2 от 31.08.2026, заменяет make_charts-02.py
#
# ЧТО ИЗМЕНИЛОСЬ В 03
#
#   1. ЭНЕРГИЯ БЕРЁТСЯ ИЗ РАЗДЕЛА energy, А НЕ ИЗ measurements. Разностные
#      джоули на кадр - те самые, которыми набраны таблицы главы 12 - лежат в
#      results.json в отдельном разделе energy. В measurements их нет вовсе:
#      разность считается уже после того, как обе строки записаны. Версия 02
#      искала только в measurements и картинку энергии просто не рисовала.
#
#   2. РАЗБОР ПО СТАДИЯМ БЕРЁТСЯ ИЗ ТОГО ЖЕ results.json. Он лежит там в
#      разделе stage_breakdown; версия 02 искала отдельный файл stages.json,
#      которого bench-05.py не делает, и картинку пропускала. Отдельный
#      stages.json по-прежнему принимается и имеет старшинство.
#
# Картинки статьи про сравнение кодеков JPEG2000 из папки прогона: кодирование,
# декодирование, сводная для первого экрана, энергия на кадр и разбор по
# стадиям. Числа берутся из results.json прогона, язык задаётся внутри — рисует
# сразу обе версии, русскую и английскую.
#
#     python make_charts-02.py                      что умеет, ничего не делает
#     python make_charts-02.py <папка-прогона>       показать числа, не рисовать
#     python make_charts-02.py <папка-прогона> --do  нарисовать и записать
#
# ЧЕМ ЭТОТ СКРИПТ ОТЛИЧАЕТСЯ ОТ j2k-charts-03.py, И КОГДА КАКОЙ БРАТЬ
#
#   Этот берёт числа из папки прогона и рисует английские картинки для
#   открытого репозитория. j2k-charts-03.py берёт числа из таблиц самой статьи
#   и рисует картинки для сайта — так картинка и таблица не могут разойтись.
#   Для сайта нужен тот, для репозитория этот. Одну и ту же картинку двумя
#   скриптами не делают.
#
# ЧТО ИЗМЕНИЛОСЬ ПРОТИВ ВЕРСИИ БЕЗ НОМЕРА (2026-08-26.2)
#
#   1. ЭНЕРГИЯ БЕРЁТСЯ ИЗ ТОГО ЖЕ ПОЛЯ, ЧТО И ТАБЛИЦЫ СТАТЬИ. Прежняя версия
#      искала джоули среди строк режима throughput и брала первое подходящее
#      поле, то есть j_per_frame — величину, посчитанную из средней мощности за
#      время прогона. А в таблицах главы 12 стоят разностные значения,
#      j_per_frame_diff, и живут они в строках режима energy, куда прежний
#      разбор вообще не заглядывал. Картинка и таблица показывали бы разные
#      величины под одной подписью. Теперь берётся разностное значение, а если
#      его нет — скрипт говорит вслух, что рисует другую величину.
#
#   2. ЗАПУСК БЕЗ ПАРАМЕТРОВ НИЧЕГО НЕ ДЕЛАЕТ, а печатает, как его звать и что
#      ему нужно. Прежняя версия падала на sys.argv[1] с трассировкой.
#
#   3. СНАЧАЛА ЧИСЛА, ПОТОМ КАРТИНКИ. Без ключа --do скрипт печатает всё, что
#      он взял из прогона, и не рисует ничего: числа можно сверить с таблицами
#      статьи глазами до того, как появятся файлы.
#
#   4. ШРИФТ ИЩЕТСЯ ТАМ, ГДЕ ОН ЕСТЬ, А НЕ ТОЛЬКО В LINUX. Прежняя версия
#      подсовывала matplotlib два файла по пути /usr/share/fonts/..., которого
#      на машине с Windows нет, и молча рисовала запасным шрифтом: картинка
#      выходила похожей, но не такой, как соседние на странице, а имя файла у
#      неё было то же самое. Теперь Carlito ищется рядом со скриптом в папке
#      fonts, потом в системных местах, и без него скрипт не рисует и говорит,
#      чего не хватает. Обойти можно ключом --any-font, но для картинок на
#      сайт так делать не надо.
#
#   5. ЧЕГО НЕ ХВАТАЕТ — СКАЗАНО СЛОВАМИ. Нет папки, нет results.json, нет
#      stages.json, не нашлось точки сетки — вместо трассировки печатается,
#      что искали, где искали и что делать.
#
#   6. ВЕРСИЯ В ТРЁХ МЕСТАХ: в имени файла, в строке выше и в первой строке
#      вывода вместе с папкой прогона.
#
import sys, os, json, argparse, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
import matplotlib.patheffects as pe

SCRIPT_NAME = "make_charts-03.py"          # совпадает с именем файла на диске
VERSION = "2026-08-31.2"                   # печатается первой строкой вывода

# Шрифт статьи — Carlito. Он лежит рядом со скриптом, в папке fonts, и
# подсовывается matplotlib прямо файлом: ставить его в систему не нужно, и
# работает это одинаково на Windows и на Linux. Заодно смотрим туда, где шрифт
# оказывается при обычной установке — с LibreOffice или руками.
_HERE = os.path.dirname(os.path.abspath(__file__))
FONT_FILES = ("Carlito-Regular.ttf", "Carlito-Bold.ttf")
FONT_DIRS = [
    os.path.join(_HERE, "fonts"),
    os.path.join(_HERE, "..", "fonts"),
    "/usr/share/fonts/truetype/crosextra",
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 "Microsoft", "Windows", "Fonts"),
]
FONT_FROM = []
for _d in FONT_DIRS:
    if not _d:
        continue
    for _n in FONT_FILES:
        _p = os.path.join(_d, _n)
        if os.path.isfile(_p):
            try:
                font_manager.fontManager.addfont(_p)
                if _d not in FONT_FROM:
                    FONT_FROM.append(os.path.normpath(_d))
            except Exception:
                pass
plt.rcParams["font.family"] = ["Carlito", "DejaVu Sans"]


def carlito_ready():
    """Есть ли у matplotlib сам Carlito.

    Спрашиваем по списку известных ему семейств, а не через findfont: тот на
    ненайденном шрифте отдаёт запасной и при этом считается успехом.
    """
    try:
        names = set(f.name for f in font_manager.fontManager.ttflist)
    except Exception:
        return False
    return "Carlito" in names

FV, NV = "#26ADDF", "#FE7E2A"
TXT, GREY = "#23262E", "#3F454F"
# Ускорение — величина считанная, а не измеренная, и ни одному из двух
# кодеков не принадлежит. Поэтому оно вынесено в отдельный столбец справа и
# набрано на плашке: и цвет не спорит с цветами кодеков, и видно, что это
# другая величина. Менять цвет — здесь, двумя строками.
# Плашка окрашена по тому, кто впереди в этой строке: светлая заливка и
# рамка — цвета того кодека, у которого столбец длиннее. Одна общая краска
# здесь врала бы: на декодировании впереди nvJPEG2000, и зелёная плашка
# читалась бы как «выиграли мы». Сама цифра остаётся тёмной, цветом текста.
RATIO_TINT = {FV: "#E3F4FB", NV: "#FEEEE2"}
# Где начинается столбец с ускорением: доля от ширины шкалы, ЛЕВЫЙ край.
# И шапка, и плашки выровнены по нему слева — так они стоят ровно друг под
# другом, и не нужно гадать, какой ширины плашка.
RATIO_X = 0.80
# У сдвоенной картинки столбец придвинут к столбикам плотнее: справа нужно
# место ещё и для легенды, которая выравнивается по правой половине.
RATIO_X_TWO = 0.78
# Левый край заголовка, шапки и подписей строк — одна вертикаль на картинке.
HEAD_X = 0.055
WIDTHS = (1200, 900, 700)

# Цвета стадий. Раньше здесь был один тон от светлого к тёмному — по замыслу
# «это последовательность», на деле соседние доли различались плохо. Стадии —
# это шесть разных действий, а не шесть величин одной шкалы, поэтому у каждой
# теперь свой цвет. Набор проверен считалкой: соседние пары различимы и при
# дальтонизме (худшая пара ΔE 9,1 при пороге 8), все в допустимой полосе
# светлоты. Большая доля, EBCOT Tier-1, получила синий: она главная в кадре.
# Стадия на процессоре вдобавок помечена штриховкой — её видно и без цвета,
# и на чёрно-белой печати.
# Зелёных было два — светлый и тёмный, и они путались. Копирование по шине
# стало серым, и это не только ради различимости: в таблице статьи у этой
# строки в графе «где» стоит прочерк — она единственная не считает ничего ни
# на видеокарте, ни на процессоре, а просто везёт данные. Серый цвет ровно
# про это. Он единственный в наборе без насыщенности, и это сделано намеренно.
STAGE_RAMP = ("#1BAF7A", "#EDA100", "#2A78D6", "#E87BA4", "#6B7280", "#4A3AA7")
CPU_HATCH = "///"


def _ink(hexcolor):
    """Цвет подписи поверх заливки: на тёмной — белый, на светлой — тёмный."""
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return TXT if lum > 0.55 else "white"

TEXT = {
    "ru": {
        "enc": "Кодирование JPEG2000",
        "dec": "Декодирование JPEG2000",
        "sum": "JPEG2000: кодирование и декодирование",
        "sub": ("RTX 4090, {date}, три повтора, сжатые файлы одинакового размера.\n"
                "У каждого кодека взяты число потоков и размер пачки, дающие лучшую скорость."),
        "sub_sum": ("RTX 4090, {date}, три повтора, сжатие с потерями при одинаковом размере файла.\n"
                    "У каждого кодека взяты число потоков и размер пачки, дающие лучшую скорость."),
        "x": "Кадров в секунду",
        "rows": {("2k", "irrev"): "2K, с потерями", ("2k", "rev"): "2K, без потерь",
                 ("4k", "irrev"): "4K, с потерями", ("4k", "rev"): "4K, без потерь"},
        "panels": ("Кодирование", "Декодирование"),
        "sum_rows": {"2k": "2K", "4k": "4K"},
        "ratio": "× %s",
        "ratio_head": "Ускорение",
        "ratio_head_energy": "Экономия",
        "energy": "JPEG2000: энергия на кадр",
        "energy_sub": ("RTX 4090, {date}, три повтора, сжатые файлы одинакового размера.\n"
                       "Меньше — лучше: столбец короче значит, что кадр обошёлся дешевле."),
        "energy_x": "Джоулей на кадр",
        "stages": "Из чего складывается время кадра",
        "stages_sub": ("fvJPEG2000, RTX 4090, {date}, сжатие с потерями, один кадр.\n"
                       "Доли этого времени по стадиям, проценты округлены до целых."),
        "stages_x": "Доля времени кодирования или декодирования, %",
        "stage_names": ("Цветовое преобразование и сдвиг", "Вейвлет-преобразование",
                        "EBCOT Tier-1", "Сборка буферов", "Копирование по шине",
                        "Tier-2 (процессор)"),
        # Сначала обе строки про 2K, потом обе про 4K: так рядом стоит то,
        # что читатель и сравнивает — кодирование с декодированием на одном
        # размере кадра.
        "stage_rows": ("Кодирование 2K", "Декодирование 2K",
                       "Кодирование 4K", "Декодирование 4K"),
    },
    "en": {
        "enc": "JPEG2000 encoding",
        "dec": "JPEG2000 decoding",
        "sum": "JPEG2000: encoding and decoding",
        "sub": ("RTX 4090, {date}, three repeats, matching compressed file sizes.\n"
                "For each codec the number of threads and the batch size that give the best speed."),
        "sub_sum": ("RTX 4090, {date}, three repeats, lossy algorithm at matching file sizes.\n"
                    "For each codec the number of threads and the batch size that give the best speed."),
        "x": "Frames per second",
        "rows": {("2k", "irrev"): "2K, lossy", ("2k", "rev"): "2K, lossless",
                 ("4k", "irrev"): "4K, lossy", ("4k", "rev"): "4K, lossless"},
        "panels": ("Encoding", "Decoding"),
        "sum_rows": {"2k": "2K", "4k": "4K"},
        "ratio": "x %s",
        "ratio_head": "Speedup",
        "ratio_head_energy": "Saving",
        "energy": "JPEG2000: energy per frame",
        "energy_sub": ("RTX 4090, {date}, three repeats, matching compressed file sizes.\n"
                       "Less is better: a shorter bar means less energy per frame."),
        "energy_x": "Joules per frame",
        "stages": "Where the time goes inside one frame",
        "stages_sub": ("fvJPEG2000, RTX 4090, {date}, lossy algorithm, one frame.\n"
                       "Share of the encoding or decoding time by stage, rounded."),
        # «Share of frame time» — конструкция верная (frame time, frametime —
        # устоявшийся термин в графике), но на сайтах редкая. Меняться местами
        # ей нельзя: «time frame» по-английски значит «отрезок времени, срок»,
        # и подпись читалась бы как «доля некоего срока». Поэтому называем
        # прямо то, от чего берётся доля: время кодирования или декодирования.
        "stages_x": "Share of encode/decode time, %",
        # Английский у нас американский: color, а не colour.
        "stage_names": ("Color transform and level shift", "Wavelet transform",
                        "EBCOT Tier-1", "Buffers gathering", "Copy over the bus",
                        "Tier-2 (CPU)"),
        "stage_rows": ("Encoding 2K", "Decoding 2K", "Encoding 4K", "Decoding 4K"),
    },
}
NAMES = ("fvJPEG2000", "nvJPEG2000")


def best_points(run):
    """Лучшая точка сетки для каждого сочетания: fps."""
    out = {}
    for m in run["measurements"]:
        if m["mode"] != "throughput" or m["note"]:
            continue
        k = (m["codec"], m["direction"], m["image"], m["alg"])
        if k not in out or m["fps"] > out[k]:
            out[k] = m["fps"]
    return out


def _head(fig, title, sub, legend_x=None):
    """Шапка картинки. legend_x — левый край легенды в долях ширины.

    Когда справа стоит столбец с ускорением, легенда выравнивается по его
    левому краю: квадратики цветов, слово «Speedup» и плашки оказываются на
    одной вертикали, и правый край картинки читается как один блок.
    """
    fig.suptitle(title, fontsize=24, color=TXT, x=HEAD_X, ha="left", y=0.965)
    fig.text(HEAD_X, 0.86, sub, fontsize=15, color=GREY, ha="left", va="top",
             linespacing=1.75)
    handles = [Patch(color=FV, label=NAMES[0]), Patch(color=NV, label=NAMES[1])]
    if legend_x is None:
        fig.legend(handles=handles, loc="upper right",
                   bbox_to_anchor=(0.985, 0.885), frameon=False,
                   fontsize=16, labelcolor=TXT)
    else:
        leg = fig.legend(handles=handles, loc="upper left",
                         bbox_to_anchor=(legend_x, 0.885), frameon=False,
                         fontsize=16, labelcolor=TXT)
        # Точка привязки — это угол рамки легенды, а не левый край квадратика:
        # между ними есть внутренний отступ, и на глаз он заметен. Поэтому
        # рисуем один раз, замеряем, где на самом деле оказался квадратик, и
        # сдвигаем легенду на разницу.
        fig.canvas.draw()
        patch = leg.get_patches()[0]
        got = patch.get_window_extent().x0 / fig.bbox.width
        leg.set_bbox_to_anchor((legend_x + (legend_x - got), 0.885))
        fig.canvas.draw()


def _left_align_ylabels(fig, ax, gap=14, to_head=False):
    """Подписи строк слева выровнять по левому краю, а не по шкале.

    По умолчанию они прижаты к шкале справа, и слева получается рваный край:
    «Кодирование 2K» начинается левее, чем «2K». Разворачиваем их влево и
    отодвигаем от шкалы на ширину самой длинной подписи — тогда все они
    начинаются с одной вертикали.
    """
    for lbl in ax.get_yticklabels():
        lbl.set_ha("left")
    # Засечки у этих подписей теперь висят сами по себе, оторванные от текста,
    # и читаются как случайные чёрточки. Убираем.
    ax.tick_params(axis="y", length=0)
    fig.canvas.draw()
    widest = max((t.get_window_extent().width for t in ax.get_yticklabels()),
                 default=0)
    # Левый край подписей ставим туда же, где начинаются заголовок и шапка:
    # у первой половины картинки это одна вертикаль на всё изображение.
    # Если самая длинная подпись до шкалы не достаёт, отступ считаем по ней.
    # У правой половины сдвоенной картинки такой вертикали нет: до заголовка
    # там пол-изображения, поэтому её подписи просто выравниваются между собой.
    head_px = HEAD_X * fig.bbox.width
    want = (ax.get_window_extent().x0 - head_px) if to_head else 0
    if to_head and widest + gap > want:
        # Подписи длиннее, чем поле слева от шкалы. Так бывает по-русски:
        # «Декодирование 4K» шире, чем «Decoding 4K». Не даём им уехать за
        # вертикаль заголовка — вместо этого отодвигаем саму шкалу вправо.
        fig.subplots_adjust(left=(head_px + widest + gap) / fig.bbox.width)
        fig.canvas.draw()
        want = widest + gap
    # Отступ у matplotlib меряется в пунктах, а всё, что мы намеряли, — в
    # точках картинки. Без пересчёта подписи улетают к самому краю: при 100
    # точках на дюйм пункт длиннее точки почти в полтора раза.
    px_to_pt = 72.0 / fig.dpi
    ax.tick_params(axis="y", pad=max(widest + gap, want) * px_to_pt)


def _ratio(a, b):
    """Во сколько раз больший больше меньшего. Ноль и пропуск не считаем."""
    lo, hi = min(a, b), max(a, b)
    return (hi / lo) if lo > 0 else None


def _fmt(val, digits):
    t = ("%%.%df" % digits) % val
    return t.replace(".", ",") if _DECIMAL_COMMA[0] else t


_DECIMAL_COMMA = [False]


def _axis(ax, rows, xmax, xlabel, labels, digits=0, ratio_label=None,
          ratio_head=None, less_is_better=False, val_size=17, tick_top=None,
          ratio_x=RATIO_X):
    """Одна половина картинки: строки из пары столбцов.

    ratio_label — как подписать кратность («×%s» или «x%s»). Подпись ставится
    у конца более длинного столбца и набирается цветом текста, а не цветом
    столбца: за принадлежность отвечает положение, а цвет остаётся у столбца.
    """
    ypos = []
    boxes = []
    for i, (fv, nv) in enumerate(rows):
        y = -i * 1.0
        ax.barh(y + 0.21, fv, height=0.42, color=FV, zorder=3)
        ax.barh(y - 0.21, nv, height=0.42, color=NV, zorder=3)
        widest = max(fv, nv)
        for val, yy in ((fv, y + 0.21), (nv, y - 0.21)):
            ax.text(val + xmax * 0.011, yy, _fmt(val, digits), va="center",
                    fontsize=val_size, color=TXT, zorder=4)
        if ratio_label:
            # Кратность стоит своим столбцом у правого края и выровнена по
            # правому краю: так она не зависит от длины столбца и от того,
            # сколько знаков в значении, и её видно как отдельную величину.
            k = _ratio(fv, nv)
            if k:
                # На картинке скорости впереди тот, у кого столбец длиннее,
                # а на картинке энергии — наоборот, у кого короче.
                if less_is_better:
                    who = FV if fv <= nv else NV
                else:
                    who = FV if fv >= nv else NV
                t = ax.text(xmax * ratio_x, y, ratio_label % _fmt(k, 1),
                            va="center", ha="left", fontsize=17,
                            color=TXT, zorder=5, fontweight="bold",
                            bbox=dict(boxstyle="round,pad=0.38",
                                      facecolor=RATIO_TINT[who], edgecolor=who,
                                      linewidth=1.4))
                boxes.append(t)
        ypos.append(y)
    if ratio_label and ratio_head:
        # Шапка и плашки выровнены по одному левому краю: у плашек ширина
        # одинаковая, поэтому столбец получается ровным и справа тоже.
        ax._ratio_head = ax.text(xmax * ratio_x, max(ypos) + 0.62, ratio_head,
                                 va="center", ha="left", fontsize=16,
                                 color=GREY, zorder=4)
    ax._ratio_boxes = boxes
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=18, color=TXT)
    ax.set_xlim(0, xmax)
    if ratio_label:
        # Столбец с ускорением сидит в запасе справа, и сетка с делениями,
        # которые дальше самого длинного столбца, лезет прямо под плашки.
        # Деления за данными убираем: мерить там всё равно нечего.
        # У сдвоенной картинки шкала общая, поэтому предел делений считается
        # по обеим половинам сразу: иначе половина с длинными столбцами
        # осталась бы без последних делений.
        top = tick_top if tick_top else max(max(r) for r in rows)
        ax.set_xticks([t for t in ax.get_xticks() if t <= top * 1.02])
    ax.set_ylim(min(ypos) - 0.65, max(ypos) + 0.65)
    ax.set_xlabel(xlabel, fontsize=15, color=GREY, labelpad=18)
    if ratio_label:
        # Шкала растянута вправо ради столбца с ускорением, и подпись оси,
        # выровненная по её середине, уезжает от делений. Ставим её по
        # середине той части, где есть деления.
        # Подпись оси centrируется не по всей шкале и не по данным, а по той
        # части, где стоят деления с числами: от нуля до последнего деления.
        ticks = [t for t in ax.get_xticks() if 0 <= t <= xmax]
        last = max(ticks) if ticks else xmax
        ax.xaxis.set_label_coords((last / xmax) / 2.0, -0.135)
    ax.tick_params(axis="x", labelsize=14, colors=GREY)
    # Засечки у подписей строк убираем всегда. Раньше их снимал только тот
    # кусок, который двигает подписи влево, и получалось вразнобой: у левой
    # половины сдвоенной картинки засечек нет, у правой есть.
    ax.tick_params(axis="y", length=0)
    # Сетку рисуем сами, а не ax.grid: та тянет линии на всю высоту поля, и
    # над верхним столбцом остаются висеть хвостики в пустоте. Наши линии
    # доходят снизу до оси, а сверху обрываются по верхнему краю столбцов.
    y_lo = min(ypos) - 0.65
    y_hi = max(ypos) + 0.42
    for t in ax.get_xticks():
        if 0 < t <= xmax:
            ax.vlines(t, y_lo, y_hi, color="#D3D8DE", linewidth=1, zorder=0)
    for sp in ("top", "right", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#9AA1AB")


def _align_ratio_column(fig, ax, ratio_label):
    """Подвести шапку столбца к видимому левому краю плашки.

    Точка привязки текста — начало букв, а у плашки есть ещё и внутренний
    отступ, поэтому её рамка выступает влево. На глаз это заметно. Рисуем
    один раз, замеряем рамку и двигаем шапку к ней. Возвращаем тот же край
    в долях ширины картинки — по нему потом ставится легенда.
    """
    if not ratio_label or not getattr(ax, "_ratio_boxes", None):
        return None
    fig.canvas.draw()
    patch = ax._ratio_boxes[0].get_bbox_patch()
    x_px = patch.get_window_extent().x0
    head = getattr(ax, "_ratio_head", None)
    if head is not None:
        x_data = ax.transData.inverted().transform((x_px, 0))[0]
        head.set_x(x_data)
    return x_px / fig.bbox.width


def chart_one(rows, labels, title, sub, xlabel, digits=0, ratio_label=None,
              ratio_head=None, less_is_better=False, val_size=17):
    """Одна половина: четыре строки, кодирование или декодирование."""
    xmax = max(max(r) for r in rows) * (1.46 if ratio_label else 1.18)
    fig, ax = plt.subplots(figsize=(12, 7.0), dpi=100)
    fig.patch.set_facecolor("white")
    _axis(ax, rows, xmax, xlabel, labels, digits, ratio_label, ratio_head,
          less_is_better, val_size)
    fig.subplots_adjust(left=0.16, right=0.965, top=0.70, bottom=0.14)
    _left_align_ylabels(fig, ax, to_head=True)
    _head(fig, title, sub, _align_ratio_column(fig, ax, ratio_label))
    return fig


def chart_two(left, right, labels, title, sub, xlabel, panels,
              digits=0, ratio_label=None, left_margin=0.09, ratio_head=None,
              less_is_better=False, val_size=17, height=5.9):
    """Две половины на общей шкале: слева кодирование, справа декодирование.

    Шкала общая намеренно: с раздельными картинка сказала бы, что скорости
    сопоставимы, хотя они различаются в разы.
    """
    xmax = max(max(r) for r in left + right) * (1.72 if ratio_label else 1.18)
    tick_top = max(max(r) for r in left + right)
    fig, axes = plt.subplots(1, 2, figsize=(12, height), dpi=100, sharex=True)
    fig.patch.set_facecolor("white")
    for ax, rows, name in zip(axes, (left, right), panels):
        _axis(ax, rows, xmax, xlabel, labels, digits, ratio_label, ratio_head,
              less_is_better, val_size, tick_top, RATIO_X_TWO)
        ax.set_title(name, fontsize=20, color=TXT, pad=14, loc="left")
    # Правое поле шире обычного: за правым столбцом с ускорением должна
    # поместиться ещё и легенда, выровненная по нему.
    wspace = 0.44 if left_margin > 0.12 else 0.26
    fig.subplots_adjust(left=left_margin, right=0.90 if ratio_label else 0.965,
                        top=0.675, bottom=0.17, wspace=wspace)
    # Подписи ЛЕВОЙ половины выравниваем по вертикали заголовка, как на
    # одиночных картинках. Правая остаётся прижатой к своей шкале: слева от
    # неё стоит столбец с плашками левой половины, и отодвинутые подписи
    # налезли бы прямо на него.
    _left_align_ylabels(fig, axes[0], to_head=True)
    # Между половинами должно хватить места на две вещи сразу: столбец с
    # плашками левой половины и подписи строк правой. По-русски подписи шире
    # («Декодирование 4K» против «Decoding 4K»), и на глаз подобранный зазор
    # переставал их разводить — плашка упиралась в подпись. Поэтому зазор не
    # подбираем, а меряем: раздвигаем половины, пока между ними не станет
    # хотя бы 16 точек. Раздвигая, мы сужаем сами половины, и столбец с
    # плашками тоже едет влево, поэтому шагов нужно немного.
    if ratio_label:
        for _ in range(4):
            fig.canvas.draw()
            right_lab = min((t.get_window_extent().x0
                             for t in axes[1].get_yticklabels()), default=None)
            left_end = max([b.get_bbox_patch().get_window_extent().x1
                            for b in getattr(axes[0], "_ratio_boxes", [])]
                           + [getattr(axes[0], "_ratio_head").get_window_extent().x1
                              if getattr(axes[0], "_ratio_head", None) else 0])
            if right_lab is None or left_end + 16 <= right_lab:
                break
            wspace += (left_end + 16 - right_lab) / axes[0].get_window_extent().width
            fig.subplots_adjust(wspace=wspace)
    # Столбцов с ускорением здесь два, и легенда встаёт по правому: он ближе
    # к краю картинки, и вертикаль «квадратики — шапка — плашки» получается
    # одна, как на одиночной картинке. Шапки обеих половин подводим к своим
    # плашкам тем же замером.
    legend_x = None
    # Подписи строк здесь оставлены прижатыми к своей шкале. Выровнять их по
    # левому краю, как на одиночной картинке, не выходит: у правой половины
    # слева от шкалы стоит столбец с плашками левой, и отодвинутые подписи
    # налезают прямо на него.
    for ax in axes:
        legend_x = _align_ratio_column(fig, ax, ratio_label)
    _head(fig, title, sub, legend_x)
    return fig


def chart_stages(rows, row_labels, stage_names, title, sub, xlabel):
    """Разбор по стадиям: доли времени кадра, накопительные столбцы.

    Оттенок один, от светлого к тёмному по порядку стадий в конвейере: это
    не набор независимых величин, а последовательность. Стадия на процессоре
    вдобавок помечена штриховкой — её видно и без цвета.
    """
    fig, ax = plt.subplots(figsize=(12, 6.4), dpi=100)
    fig.patch.set_facecolor("white")
    ypos = []
    marks = []
    seams = []
    for i, parts in enumerate(rows):
        y = -i * 1.0
        left = 0.0
        # Проценты в таблице округлены до целых, и у одной строки они дают в
        # сумме 101. Нарисованная как есть, эта полоска оказывается длиннее
        # остальных, и картинка врёт: доли-то у всех строк одни и те же 100 %.
        # Поэтому ширины нормируем на сотню, а подписи оставляем такими, как
        # в таблице.
        scale = 100.0 / sum(parts) if sum(parts) else 1.0
        for j, val in enumerate(parts):
            if val <= 0:
                continue
            w = val * scale
            # Белой рамки вокруг ступени больше нет. Она рисуется по границе,
            # то есть половиной своей толщины ложится внутрь столбика: из-за
            # этого левый край первой ступени вставал на точку правее нуля и
            # не совпадал с линией шкалы, а правый край последней — не доходил
            # до сотни. Промежутки между ступенями теперь делаются иначе:
            # ступень поджимается слева уже после того, как поля расставлены,
            # и ровно на две точки (см. ниже). Крайние границы столбика при
            # этом остаются на своих местах.
            # Цвет рамки оставляем белым, а толщину ставим в ноль: рамки не
            # будет, но штриховка у стадии на процессоре красится именно
            # цветом рамки — с edgecolor="none" она пропадает совсем.
            bar = ax.barh(y, w, left=left, height=0.52, zorder=3,
                          color=STAGE_RAMP[j], edgecolor="white", linewidth=0,
                          hatch=(CPU_HATCH if j == len(parts) - 1 else None))
            if left > 0:
                seams.append((bar[0], left, w))
            # Подписываем доли от 3 % и выше. Порог тут не про место, а про
            # смысл: доля в один-два процента и так читается как «почти
            # ничего», число рядом с ней ничего не добавляет. А влезет ли
            # число в свою ступень — решает не порог, а замер ниже, уже после
            # отрисовки: раньше стоял порог 8 %, и пятипроцентные ступени
            # оставались без числа, хотя место в них есть.
            if val < 3:
                left += w
                continue
            # На тёмных ступенях подпись белая. На заштрихованной ступени белые
            # полосы штриховки идут прямо через цифры, и число выглядит
            # перечёркнутым, поэтому под цифрами лежит сплошная плашка цвета
            # самой ступени: штриховка её не пересекает, а на глаз плашки не
            # видно — цвет тот же.
            hatched = (j == len(parts) - 1)
            t = ax.text(left + w / 2.0, y, "%d" % val, va="center",
                        ha="center", fontsize=15,
                        color=_ink(STAGE_RAMP[j]), zorder=4,
                        bbox=(dict(boxstyle="square,pad=0.22",
                                   facecolor=STAGE_RAMP[j], edgecolor="none")
                              if hatched else None))
            marks.append((t, left, w))
            left += w
        ypos.append(y)
    ax.set_yticks(ypos)
    ax.set_yticklabels(row_labels, fontsize=17, color=TXT)
    # Шкала ровно до сотни: запас в один процент остался от тех времён, когда
    # у одной строки доли давали 101. Теперь ширины нормированы, и этот запас
    # только оставлял пустую полоску справа от столбиков.
    ax.set_xlim(0, 100)
    ax.set_ylim(min(ypos) - 0.7, max(ypos) + 0.7)
    ax.set_xlabel(xlabel, fontsize=15, color=GREY, labelpad=16)
    ax.tick_params(axis="x", labelsize=14, colors=GREY)
    ax.tick_params(axis="y", length=0)
    # Сетку рисуем сами, как на остальных картинках: ax.grid тянет линии на
    # всю высоту поля, и над верхним столбцом висят хвостики в пустоте.
    y_lo, y_hi = min(ypos) - 0.7, max(ypos) + 0.26
    for t in ax.get_xticks():
        if 0 < t <= 100:
            ax.vlines(t, y_lo, y_hi, color="#D3D8DE", linewidth=1, zorder=0)
    for sp in ("top", "right", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#9AA1AB")
    fig.suptitle(title, fontsize=24, color=TXT, x=HEAD_X, ha="left", y=0.965)
    fig.text(HEAD_X, 0.875, sub, fontsize=15, color=GREY, ha="left", va="top",
             linespacing=1.75)
    handles = [Patch(facecolor=STAGE_RAMP[j], edgecolor="white",
                     hatch=(CPU_HATCH if j == len(stage_names) - 1 else None),
                     label=n) for j, n in enumerate(stage_names)]
    # matplotlib раскладывает легенду по столбцам, а читают её слева направо;
    # переставляем так, чтобы порядок стадий читался строками
    ncol, nrow = 3, 2
    order = [r * ncol + c for c in range(ncol) for r in range(nrow)]
    handles = [handles[i] for i in order if i < len(handles)]
    fig.legend(handles=handles, loc="lower center", ncol=ncol, frameon=False,
               fontsize=14, labelcolor=TXT, bbox_to_anchor=(0.53, 0.0075))
    # Правое поле делаем такой же ширины, как левое: подписи строк стоят на
    # вертикали HEAD_X слева, столбики доходят до сотни справа — значит и
    # отступ от края у них должен быть один. 1 − HEAD_X и есть эта вертикаль,
    # отражённая на правую сторону.
    fig.subplots_adjust(left=0.19, right=1 - HEAD_X, top=0.70, bottom=0.30)
    _left_align_ylabels(fig, ax, to_head=True)
    # Место под число меряем, когда поля уже расставлены: ширина ступени в
    # точках известна только после этого. Числу нужна ещё пара точек воздуха
    # по бокам, иначе оно упирается в белую границу соседней ступени.
    fig.canvas.draw()
    # Две точки промежутка между ступенями. Считаем их в единицах шкалы,
    # когда поля уже расставлены, и поджимаем ступень слева: граница столбика
    # у нуля и у сотни при этом не двигается.
    unit = (ax.transData.transform((1, 0))[0]
            - ax.transData.transform((0, 0))[0])
    gap = 2.0 / unit if unit else 0
    for patch, x0, w in seams:
        patch.set_x(x0 + gap)
        patch.set_width(max(w - gap, 0.01))
    for t, x0, w in marks:
        px = (ax.transData.transform((x0 + w, 0))[0]
              - ax.transData.transform((x0, 0))[0])
        need = t.get_window_extent().width + (10 if t.get_bbox_patch() else 6)
        if need > px:
            t.set_visible(False)
    return fig


# Порядок здесь — это порядок предпочтения, и первым стоит то, что стоит в
# таблицах главы 12: разностное значение. Прежняя версия держала первым
# j_per_frame — среднюю мощность, умноженную на время прогона, — и рисовала бы
# не ту величину, которая напечатана в таблице рядом.
ENERGY_KEYS = ("j_per_frame_diff", "j_per_frame_counter", "j_per_frame",
               "energy_j", "joules_per_frame")
# В каком режиме искать каждое поле: разностное значение живёт в строках
# режима energy, а не throughput, и прежний разбор его просто не видел.
ENERGY_MODES = {"j_per_frame_diff": "energy", "j_per_frame_counter": "energy"}
ENERGY_WHAT = {
    "j_per_frame_diff": "разностное значение — то же, что в таблицах статьи",
    "j_per_frame_counter": "показание счётчика карты, НЕ разностное",
    "j_per_frame": "средняя мощность за время прогона, НЕ разностное",
    "energy_j": "джоули за прогон, НЕ разностное",
    "joules_per_frame": "джоули на кадр, происхождение неизвестно",
}


def energy_points(run):
    """Джоули на кадр в лучшей точке сетки.

    Возвращает (значения, имя поля, где искали). Имя поля печатается, потому
    что под подписью «энергия на кадр» могут стоять три разные величины, и
    какая именно — должно быть видно, а не подразумеваться.

    Сначала смотрим в раздел energy: разностное значение живёт только там.
    Каждая его запись — уже одна точка на задачу, лучшая по скорости, так что
    выбирать не из чего.
    """
    rows = run.get("energy") or []
    for field in ENERGY_KEYS:
        got = {}
        for r in rows:
            if r.get(field) is None:
                continue
            got[(r["codec"], r["direction"], r["image"], r["alg"])] = r[field]
        if len(got) == 16:
            return got, field, "energy"
        if got:
            print("  раздел energy: поле %s заполнено в %d строках из 16"
                  % (field, len(got)))

    seen = set()
    for m in run["measurements"]:
        seen.update(k for k, v in m.items() if v is not None)
    for field in ENERGY_KEYS:
        if field not in seen:
            continue
        mode = ENERGY_MODES.get(field, "throughput")
        best = {}
        for m in run["measurements"]:
            if m.get("mode") != mode or m.get("note") and mode == "throughput":
                continue
            if m.get(field) is None:
                continue
            k = (m["codec"], m["direction"], m["image"], m["alg"])
            fps = m.get("fps") or 0.0
            if k not in best or fps > best[k][0]:
                best[k] = (fps, m[field])
        if best:
            return dict((k, v[1]) for k, v in best.items()), field, mode
    return None, None, sorted(seen)


def save(fig, outdir, stem):
    """Кладёт картинку в трёх ширинах: 1200, 900 и 700 точек."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    im = Image.open(buf).convert("RGB")
    made = []
    for w in WIDTHS:
        h = int(round(im.height * w / im.width))
        p = os.path.join(outdir, "%s-%d.webp" % (stem, w))
        (im if w == im.width else im.resize((w, h), Image.LANCZOS)).save(
            p, "WEBP", quality=88, method=6)
        made.append((p, w, h, os.path.getsize(p)))
    return made


ORDER = [("2k", "irrev"), ("2k", "rev"), ("4k", "irrev"), ("4k", "rev")]
ROW_RU = {("2k", "irrev"): "2K, с потерями", ("2k", "rev"): "2K, без потерь",
          ("4k", "irrev"): "4K, с потерями", ("4k", "rev"): "4K, без потерь"}


def usage():
    """Печатается при запуске без параметров. Ничего не рисует."""
    print("=" * 72)
    print(" %s, версия %s" % (SCRIPT_NAME, VERSION))
    print(" Картинки статьи про JPEG2000 из папки прогона")
    print("=" * 72)
    print("")
    print(" Ничего не сделано: скрипту нужно сказать, из какой папки брать")
    print(" числа.")
    print("")
    print(" КАК ЗАПУСКАТЬ")
    print("   python %s <папка-прогона>" % SCRIPT_NAME)
    print("        показать числа, которые он взял, и ничего не рисовать")
    print("   python %s <папка-прогона> --do" % SCRIPT_NAME)
    print("        нарисовать и записать картинки")
    print("")
    print("   Ключи:")
    print("     --out ПАПКА    куда класть картинки, по умолчанию charts")
    print("     --any-font     рисовать без Carlito (для картинок на сайт")
    print("                    так делать не надо)")
    print("")
    print(" ЧТО ЕМУ НУЖНО")
    print("   <папка-прогона>/results.json   обязательно, это числа прогона")
    print("   <папка-прогона>/stages.json    если есть — будет картинка")
    print("                                  разбора по стадиям, без неё")
    print("                                  просто не будет её одной")
    print("   Carlito-Regular.ttf и Carlito-Bold.ttf — рядом со скриптом,")
    print("   в папке fonts. Ставить в систему не нужно.")
    print("")
    print(" ШРИФТ СЕЙЧАС")
    if carlito_ready():
        print("   Carlito найден: %s" % (", ".join(FONT_FROM) or "из системы"))
    else:
        print("   Carlito НЕ НАЙДЕН. Искал в:")
        for d in FONT_DIRS:
            if d:
                print("     %s" % os.path.normpath(d))
        print("   Без него скрипт не рисует: matplotlib молча подставил бы")
        print("   свой запасной шрифт, картинка вышла бы похожей, но не такой,")
        print("   как соседние на странице, а имя файла у неё было бы то же.")
    print("")
    print(" ЧЕМ ЭТОТ СКРИПТ ОТЛИЧАЕТСЯ ОТ j2k-charts-03.py")
    print("   Этот берёт числа из папки прогона — для открытого репозитория.")
    print("   Тот берёт числа из таблиц самой статьи — для сайта, чтобы")
    print("   картинка и таблица не могли разойтись.")
    return 1


# Как имена стадий из вывода ключа -info ложатся в шесть столбцов картинки.
# У кодера и декодера они называются по-разному и идут в обратном порядке,
# поэтому таблиц соответствия две.
STAGE_SLOTS = ("color", "dwt", "tier1", "buffers", "copy", "tier2")
STAGE_MAP_E = {
    "Preprocessing time": "color",
    "DWT time": "dwt",
    "Tier-1 time": "tier1",
    "Buffers gathering time": "buffers",
    "GPU->CPU copy time": "copy",
    "Tier-2 time": "tier2",
}
STAGE_MAP_D = {
    "Postprocessing time": "color",
    "DWT time": "dwt",
    "Tier-1 time": "tier1",
    "CPU->GPU copy time": "copy",
    "Tier-2 time": "tier2",
}


def stages_from_run(run):
    """Разбор по стадиям прямо из results.json, раздел stage_breakdown.

    Возвращает то же, что раньше читалось из stages.json: по строке на
    encode_2k, decode_2k, encode_4k, decode_4k, в каждой шесть долей в
    порядке столбцов картинки. У декодера сборки буферов нет — там ноль.
    """
    src = run.get("stage_breakdown") or {}
    out = {}
    for key, name in (("fv_E_2k", "encode_2k"), ("fv_D_2k", "decode_2k"),
                      ("fv_E_4k", "encode_4k"), ("fv_D_4k", "decode_4k")):
        rows = src.get(key)
        if not rows:
            continue
        table = STAGE_MAP_E if "_E_" in key else STAGE_MAP_D
        slot = dict((s, 0.0) for s in STAGE_SLOTS)
        for r in rows:
            where = table.get(r.get("stage"))
            if where:
                slot[where] += r.get("share_percent") or 0.0
        out[name] = [round(slot[s]) for s in STAGE_SLOTS]
    return out or None


def show_numbers(fps, joules, jfield, jmode, stages, date_iso):
    """Печатает всё, что взято из прогона, до того как что-то нарисовано.

    Правило простое: числа сверяются с таблицами статьи глазами, и сверять
    надо до появления файлов, а не после.
    """
    print("")
    print("ЧТО ВЗЯТО ИЗ ПРОГОНА")
    print("Дата прогона: %s" % date_iso)
    print("")
    print("Скорость, кадров в секунду (лучшая точка сетки)")
    print("  режим                кодирование            декодирование")
    print("  %-18s %9s %9s %6s  %9s %9s %6s"
          % ("", "fv", "nv", "раз", "fv", "nv", "раз"))
    missing = []
    for k in ORDER:
        vals = []
        for d in ("E", "D"):
            a, b = fps.get(("fv", d) + k), fps.get(("nv", d) + k)
            if a is None or b is None:
                missing.append("%s %s %s" % (d, k[0], k[1]))
            vals += [a, b, (a / b) if (a and b) else None]

        def f(v, digits=1):
            return ("%9.1f" % v) if v is not None else "        -"
        print("  %-18s %s %s %6s  %s %s %6s"
              % (ROW_RU[k], f(vals[0]), f(vals[1]),
                 ("%.2f" % vals[2]) if vals[2] else "-",
                 f(vals[3]), f(vals[4]),
                 ("%.2f" % vals[5]) if vals[5] else "-"))
    if missing:
        print("")
        print("  НЕ НАШЛОСЬ точек сетки: %s" % ", ".join(sorted(set(missing))))
        print("  Картинки по ним будут неполными. Ничего не пропускаю молча.")

    print("")
    if joules is None:
        print("Энергия: в results.json джоулей на кадр нет.")
        print("  Искал поля: %s" % ", ".join(ENERGY_KEYS))
        print("  В записях прогона есть: %s"
              % ", ".join(sorted(jmode)[:20]))
        print("  Картинку энергии пропускаю.")
    else:
        print("Энергия на кадр, джоули — поле %s, строки режима %s"
              % (jfield, jmode))
        print("  %s" % ENERGY_WHAT.get(jfield, "происхождение неизвестно"))
        if jfield != "j_per_frame_diff":
            print("  ВНИМАНИЕ: в таблицах главы 12 статьи стоит разностное")
            print("  значение j_per_frame_diff. Здесь его нет, и картинка")
            print("  покажет ДРУГУЮ величину под той же подписью. Либо взять")
            print("  прогон, где энергия мерялась разностным способом, либо")
            print("  не ставить эту картинку в статью.")
        print("  режим                кодирование        декодирование")
        for k in ORDER:
            a, b = joules.get(("fv", "E") + k), joules.get(("nv", "E") + k)
            c, d_ = joules.get(("fv", "D") + k), joules.get(("nv", "D") + k)
            def g(v):
                return ("%8.3f" % v) if v is not None else "       -"
            print("  %-18s %s %s   %s %s"
                  % (ROW_RU[k], g(a), g(b), g(c), g(d_)))

    print("")
    if stages is None:
        print("Разбор по стадиям: его нет ни в разделе stage_breakdown")
        print("  файла results.json, ни отдельным stages.json рядом.")
        print("  Картинку пропускаю: он собирается из логов, снятых с")
        print("  ключом -info, и в прогоне их могло не быть.")
    else:
        have = [k for k in ("encode_2k", "decode_2k", "encode_4k", "decode_4k")
                if k in stages]
        print("Разбор по стадиям: есть %d строк из 4" % len(have))
        print("  строка                 цвет вейвл Tier-1 буфер  шина Tier-2")
        for k in have:
            print("  %-20s %s" % (k, " ".join("%5d" % v for v in stages[k])))


def main():
    if len(sys.argv) == 1:
        return usage()

    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("rundir", help="папка прогона, в ней results.json")
    ap.add_argument("--out", default="charts", help="куда класть картинки")
    ap.add_argument("--do", action="store_true",
                    help="нарисовать и записать; без него только числа")
    ap.add_argument("--any-font", action="store_true",
                    help="рисовать без Carlito")
    args = ap.parse_args()

    rundir = os.path.abspath(args.rundir)
    print("%s, версия %s" % (SCRIPT_NAME, VERSION))
    print("Папка прогона: %s" % rundir)

    if not os.path.isdir(rundir):
        print("")
        print("Такой папки нет. Нужна папка прогона, в которой лежит")
        print("results.json — её делает bench-05.py, имя вида")
        print("cmp_20260831_101530.")
        return 1
    res_path = os.path.join(rundir, "results.json")
    if not os.path.isfile(res_path):
        print("")
        print("В этой папке нет results.json. Что в ней есть: %s"
              % (", ".join(sorted(os.listdir(rundir))[:12]) or "ничего"))
        print("Если прогон был прерван, соберите отчёт заново:")
        print("   python bench-05.py --summary")
        return 1
    try:
        run = json.load(open(res_path, encoding="utf-8"))
    except ValueError as e:
        print("")
        print("results.json не читается как JSON: %s" % e)
        return 1

    fps = best_points(run)
    joules, jfield, jmode = energy_points(run)
    stages_path = os.path.join(rundir, "stages.json")
    stages = None
    if os.path.exists(stages_path):
        stages = json.load(open(stages_path, encoding="utf-8"))
    else:
        stages = stages_from_run(run)

    try:
        date_iso = run["environment"]["date"][:10]         # 2026-08-31
    except (KeyError, TypeError):
        print("")
        print("В results.json нет environment.date — из неё берётся дата в")
        print("подписях и в именах файлов. Без неё не рисую.")
        return 1

    show_numbers(fps, joules, jfield, jmode, stages, date_iso)

    if not args.do:
        print("")
        print("Ничего не нарисовано: это показ чисел. Сверьте их с таблицами")
        print("статьи, и если сходится — запустите с ключом --do.")
        return 0

    if not carlito_ready() and not args.any_font:
        print("")
        print("Шрифт Carlito не найден, и matplotlib взял бы свой запасной.")
        print("Картинка вышла бы похожей, но не такой, как соседние на")
        print("странице, а имя файла у неё было бы то же самое — подмену")
        print("потом никто не заметил бы. Положите рядом со скриптом папку")
        print("fonts с файлами:")
        for nfile in FONT_FILES:
            print("   %s" % os.path.join(_HERE, "fonts", nfile))
        print("Ничего не рисую. Обойти можно ключом --any-font.")
        return 1

    outroot = os.path.abspath(args.out)
    print("")
    print("РИСУЮ. Шрифт: %s" % ("Carlito из %s" % (", ".join(FONT_FROM)
                                                   or "системы")
                                if carlito_ready() else "ЗАПАСНОЙ, не Carlito"))
    y, m, d = date_iso.split("-")
    order = ORDER

    for lang in ("ru", "en"):
        T = TEXT[lang]
        date = ("%s.%s.%s" % (d, m, y)) if lang == "ru" else date_iso
        sub = T["sub"].format(date=date)
        outdir = os.path.join(outroot, lang)
        os.makedirs(outdir, exist_ok=True)
        labels = [T["rows"][k] for k in order]

        _DECIMAL_COMMA[0] = (lang == "ru")
        enc = [(fps[("fv", "E") + k], fps[("nv", "E") + k]) for k in order]
        dec = [(fps[("fv", "D") + k], fps[("nv", "D") + k]) for k in order]
        made = []
        made += save(chart_one(enc, labels, T["enc"], sub, T["x"],
                               ratio_label=T["ratio"],
                               ratio_head=T["ratio_head"]),
                     outdir, "j2k-encode-4090-%s" % date_iso)
        made += save(chart_one(dec, labels, T["dec"], sub, T["x"],
                               ratio_label=T["ratio"],
                               ratio_head=T["ratio_head"]),
                     outdir, "j2k-decode-4090-%s" % date_iso)

        # сводная: только режим с потерями, две строки
        srows = ["2k", "4k"]
        sl = [(fps[("fv", "E", t, "irrev")], fps[("nv", "E", t, "irrev")])
              for t in srows]
        sr = [(fps[("fv", "D", t, "irrev")], fps[("nv", "D", t, "irrev")])
              for t in srows]
        made += save(chart_two(sl, sr, [T["sum_rows"][t] for t in srows],
                               T["sum"], T["sub_sum"].format(date=date),
                               T["x"], T["panels"], ratio_label=T["ratio"],
                               ratio_head=T["ratio_head"]),
                     outdir, "j2k-summary-%s" % date_iso)

        # энергия на кадр: те же четыре строки, две половины, общая шкала
        if joules is not None:
            je = [(joules[("fv", "E") + k], joules[("nv", "E") + k])
                  for k in order]
            jd = [(joules[("fv", "D") + k], joules[("nv", "D") + k])
                  for k in order]
            made += save(chart_two(je, jd, labels, T["energy"],
                                   T["energy_sub"].format(date=date),
                                   T["energy_x"], T["panels"],
                                   digits=2, ratio_label=T["ratio"],
                                   ratio_head=T["ratio_head_energy"],
                                   left_margin=0.155, less_is_better=True,
                                   val_size=15, height=6.6),
                         outdir, "j2k-energy-4090-%s" % date_iso)

        # разбор по стадиям: доли времени кадра
        if stages is not None:
            srows_ = [stages[k] for k in ("encode_2k", "decode_2k",
                                          "encode_4k", "decode_4k")]
            made += save(chart_stages(srows_, list(T["stage_rows"]),
                                      list(T["stage_names"]), T["stages"],
                                      T["stages_sub"].format(date=date),
                                      T["stages_x"]),
                         outdir, "j2k-stages-4090-%s" % date_iso)
        for p, w, h, sz in made:
            print("  %-58s %4dx%-4d %6d байт"
                  % (os.path.relpath(p, outroot), w, h, sz))
    print("готово")
    return 0


if __name__ == "__main__":
    sys.exit(main())
