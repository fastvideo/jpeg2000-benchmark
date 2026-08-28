# -*- coding: utf-8 -*-
# make_charts.py
# версия 2026-08-28.4 от 28.08.2026
# Картинки статьи про сравнение кодеков JPEG2000: кодирование, декодирование,
# сводная для первого экрана, энергия на кадр и разбор по стадиям.
# Числа берутся из results.json прогона, язык задаётся ключом.
#     python make_charts.py <папка-прогона> <папка-вывода>
#
# Что нового против 2026-08-24.1:
#   * у каждой пары столбцов подписана кратность — отдельным столбцом справа,
#     на плашке цвета того, кто в этой строке впереди. Шапка столбца, плашки
#     и легенда стоят на одной вертикали, и она не подбирается на глаз, а
#     меряется по отрисованной картинке;
#   * новая картинка «энергия на кадр», две половины: кодирование и
#     декодирование, общая шкала, меньше — лучше;
#   * новая картинка «разбор по стадиям», доли времени кодирования и
#     декодирования; берётся из stages.json рядом с results.json, потому что
#     в самом results.json разбора по стадиям нет;
#   * подписи строк на одиночных картинках выровнены по левому краю, по той
#     же вертикали, что заголовок и шапка; поля слева и справа одинаковые;
#   * у разбора по стадиям свой цвет у каждой стадии вместо одного тона от
#     светлого к тёмному: соседние доли теперь различимы, набор проверен
#     считалкой на различимость, в том числе при дальтонизме.
#
# Что нового против 2026-08-26.2:
#   * малый разрыв пишется процентами, а не кратностью: «× 1,02» читателю
#     ничего не говорит. Порог — двукратный разрыв. На картинке энергии
#     проценты не используются: там величина обратная, и «× 1,6» и
#     «экономия 60 %» — разные числа, путать их нельзя;
#   * разрыв считается по числам, НАПЕЧАТАННЫМ у столбцов, а не по исходным:
#     читатель делит то, что видит, и должен получить то, что в плашке.
#     Заодно плашка сходится с таблицей статьи;
#   * если хоть в одной строке впереди чужой кодек, в плашках пишется имя
#     победителя, а шапка столбца становится «Разница». Без имени плашка
#     читается как наш выигрыш, а цвет рамки на чёрно-белой печати и при
#     дальтонизме не спасает;
#   * плашки одного столбца выровнены по ширине: её задаёт самая длинная
#     строка, остальным добавляется поле поровну с двух сторон, и текст
#     стоит по середине плашки.
import sys, os, json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
import matplotlib.patheffects as pe

for _f in ("/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
           "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"):
    try:
        font_manager.fontManager.addfont(_f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Carlito", "DejaVu Sans"]

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
# Кегль и поле плашки. Поле держим отдельной константой: по нему считается
# добавка, которая уравнивает ширину плашек в столбце.
RATIO_FS = 17.0
RATIO_PAD = 0.38
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
        "pct": "+%s %%",
        "ratio_head": "Ускорение",
        "ratio_head_dif": "Разница",
        "ratio_head_energy": "Экономия",
        "short": {"fv": "fv", "nv": "nv"},
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
        "pct": "+%s %%",
        "ratio_head": "Speedup",
        "ratio_head_dif": "Difference",
        "ratio_head_energy": "Saving",
        "short": {"fv": "fv", "nv": "nv"},
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


# Ниже этой кратности разрыв пишем процентами: «× 1,02» читателю не говорит
# ничего. Фёдор 28.08.2026: «вместо x 1.05 можно написать 5 % для малых
# значений».
PCT_BELOW = 2.0
# Текст для языка задаётся снаружи — в _gap_text приходит уже готовый набор.
_LANG = [None]


def _gap_text(fv, nv, digits, less_is_better, named):
    """Текст плашки: «× 7,2» при большом разрыве, «nv +14 %» при малом.

    Разрыв считается по числам, НАПЕЧАТАННЫМ у столбцов, а не по исходным:
    читатель делит то, что видит, и должен получить то, что стоит в плашке.
    Заодно плашка сходится с таблицей статьи, где числа округлены так же.
    """
    T = _LANG[0]
    fv = float(("%%.%df" % digits) % fv)
    nv = float(("%%.%df" % digits) % nv)
    k = _ratio(fv, nv)
    if not k:
        return None, None
    if less_is_better:
        win = "fv" if fv <= nv else "nv"
    else:
        win = "fv" if fv >= nv else "nv"
    # Проценты только там, где «быстрее на N %» читается однозначно. На
    # картинке энергии величина обратная: «× 1,6» там не то же самое, что
    # «экономия 60 %», и путать эти два числа нельзя.
    if k < PCT_BELOW and not less_is_better:
        pct = (k - 1.0) * 100.0
        if round(pct) < 1:
            return None, None
        body = T["pct"] % ("%.0f" % pct)
    else:
        body = T["ratio"] % _fmt(k, 1)
    if named:
        body = "%s %s" % (T["short"][win], body)
    return body, (FV if win == "fv" else NV)


def _needs_names(rows, less_is_better):
    """Нужно ли писать в плашках имя победителя.

    Не нужно только там, где во всех строках впереди наш кодек: тогда шапка
    «Ускорение» говорит всё сама. Как только хоть в одной строке впереди
    чужой, плашки без имени читаются как наш выигрыш — и имя обязательно.
    """
    for fv, nv in rows:
        if not ((fv <= nv) if less_is_better else (fv >= nv)):
            return True
    return False


def _fmt(val, digits):
    t = ("%%.%df" % digits) % val
    return t.replace(".", ",") if _DECIMAL_COMMA[0] else t


_DECIMAL_COMMA = [False]


def _axis(ax, rows, xmax, xlabel, labels, digits=0, ratio_label=None,
          ratio_head=None, less_is_better=False, val_size=17, tick_top=None,
          ratio_x=RATIO_X, ratio_head_dif=None):
    """Одна половина картинки: строки из пары столбцов.

    ratio_label — как подписать кратность («×%s» или «x%s»). Подпись ставится
    у конца более длинного столбца и набирается цветом текста, а не цветом
    столбца: за принадлежность отвечает положение, а цвет остаётся у столбца.
    """
    ypos = []
    boxes = []
    # Имя победителя в плашке нужно там, где он меняется от строки к строке:
    # иначе строку не прочитать ни на чёрно-белой печати, ни при дальтонизме,
    # потому что держится она на одном цвете рамки.
    named = bool(ratio_label) and _needs_names(rows, less_is_better)
    if named and ratio_head_dif:
        ratio_head = ratio_head_dif
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
            body, who = _gap_text(fv, nv, digits, less_is_better, named)
            if body:
                t = ax.text(xmax * ratio_x, y, body,
                            va="center", ha="left", fontsize=RATIO_FS,
                            color=TXT, zorder=5, fontweight="bold",
                            bbox=dict(boxstyle="round,pad=%.2f,rounding_size=%.2f"
                                                % (RATIO_PAD, RATIO_PAD),
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


def _equalise_boxes(fig, ax):
    """Уравнять ширину плашек столбца, не сдвигая их левый край.

    Плашки разной длины («nv +14 %» и «fv +2 %») смотрятся как разнобой.
    Фёдор 28.08.2026: «размеры прямоугольников с процентами лучше сделать
    одинаковыми». Ширину задаёт самая длинная строка, остальным добавляется
    поле — поровну слева и справа, поэтому текст стоит по середине плашки.
    Добавка слева сдвинула бы плашку влево, и левый край столбца перестал бы
    быть прямым, — поэтому текст сдвигается вправо ровно на эту добавку.
    """
    boxes = ax._ratio_boxes
    if len(boxes) < 2:
        return
    fig.canvas.draw()
    wid = [t.get_window_extent().width for t in boxes]
    w_max = max(wid)
    if w_max <= 0:
        return
    # точек данных в одном пикселе шкалы и кегль плашки в пикселях
    per_unit = abs(ax.transData.transform((1, 0))[0]
                   - ax.transData.transform((0, 0))[0])
    fs_px = RATIO_FS * fig.dpi / 72.0
    if per_unit <= 0:
        return
    for t, w in zip(boxes, wid):
        extra = (w_max - w) / 2.0
        if extra <= 0.5:
            continue
        t.get_bbox_patch().set_boxstyle(
            "round,pad=%.4f,rounding_size=%.4f"
            % (RATIO_PAD + extra / fs_px, RATIO_PAD))
        t.set_x(t.get_position()[0] + extra / per_unit)
    fig.canvas.draw()


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
    _equalise_boxes(fig, ax)
    patch = ax._ratio_boxes[0].get_bbox_patch()
    x_px = patch.get_window_extent().x0
    head = getattr(ax, "_ratio_head", None)
    if head is not None:
        x_data = ax.transData.inverted().transform((x_px, 0))[0]
        head.set_x(x_data)
    return x_px / fig.bbox.width


def chart_one(rows, labels, title, sub, xlabel, digits=0, ratio_label=None,
              ratio_head=None, less_is_better=False, val_size=17,
              ratio_head_dif=None):
    """Одна половина: четыре строки, кодирование или декодирование."""
    xmax = max(max(r) for r in rows) * (1.46 if ratio_label else 1.18)
    fig, ax = plt.subplots(figsize=(12, 7.0), dpi=100)
    fig.patch.set_facecolor("white")
    _axis(ax, rows, xmax, xlabel, labels, digits, ratio_label, ratio_head,
          less_is_better, val_size, ratio_head_dif=ratio_head_dif)
    fig.subplots_adjust(left=0.16, right=0.965, top=0.70, bottom=0.14)
    _left_align_ylabels(fig, ax, to_head=True)
    _head(fig, title, sub, _align_ratio_column(fig, ax, ratio_label))
    return fig


def chart_two(left, right, labels, title, sub, xlabel, panels,
              digits=0, ratio_label=None, left_margin=0.09, ratio_head=None,
              less_is_better=False, val_size=17, height=5.9,
              ratio_head_dif=None):
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
              less_is_better, val_size, tick_top, RATIO_X_TWO, ratio_head_dif)
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
            # Доли приходят дробными (13,559…), а подписываем их целыми.
            # Округляем ЯВНО: «%d» обрезает, и 13,6 превращалось в 13.
            shown = int(round(val))
            if shown < 3:
                left += w
                continue
            # На тёмных ступенях подпись белая. На заштрихованной ступени белые
            # полосы штриховки идут прямо через цифры, и число выглядит
            # перечёркнутым, поэтому под цифрами лежит сплошная плашка цвета
            # самой ступени: штриховка её не пересекает, а на глаз плашки не
            # видно — цвет тот же.
            hatched = (j == len(parts) - 1)
            t = ax.text(left + w / 2.0, y, "%d" % shown, va="center",
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


ENERGY_KEYS = ("j_per_frame", "j_per_frame_diff", "energy_j", "joules_per_frame")


def energy_points(run):
    """Джоули на кадр. Лежат отдельным блоком `energy` в results.json.

    В `measurements` энергии нет вовсе — там записи режима `energy` хранят
    только кадры в секунду. Раньше скрипт искал джоули среди полей
    `measurements` и, разумеется, не находил.

    Из четырёх способов счёта берём `j_per_frame_diff` — разностный: прогон
    на N и на 2N кадрах, разница делится на N. Так из результата уходит всё,
    что тратится один раз на запуск, и остаётся цена самого кадра.
    """
    field = "j_per_frame_diff"
    block = run.get("energy")
    if not block:
        return None, sorted(run.keys())
    out = {}
    for m in block:
        if m.get(field) is None:
            continue
        out[(m["codec"], m["direction"], m["image"], m["alg"])] = m[field]
    return (out or None), field


# Имена стадий в результатах прогона — к нашим шести местам на картинке.
# Первая стадия называется по-разному в зависимости от направления:
# на кодировании Preprocessing, на декодировании Postprocessing. Это одно и
# то же цветовое преобразование со сдвигом, только в обратную сторону.
STAGE_MAP = {
    "Preprocessing time": 0, "Postprocessing time": 0,
    "DWT time": 1,
    "Tier-1 time": 2,
    "Buffers gathering time": 3,
    "GPU->CPU copy time": 4, "CPU->GPU copy time": 4,
    "Tier-2 time": 5,
}
STAGE_ROWS = ("fv_E_2k", "fv_D_2k", "fv_E_4k", "fv_D_4k")


def stage_points(run):
    """Доли времени по стадиям из блока `stage_breakdown` results.json.

    Раньше их приходилось подавать отдельным файлом `stages.json`: я считал,
    что в результатах прогона разбора по стадиям нет. Он там есть, с
    миллисекундами и долями, — отдельный файл больше не нужен.
    """
    sb = run.get("stage_breakdown")
    if not sb:
        return None, None
    rows, unknown = [], []
    for key in STAGE_ROWS:
        if key not in sb:
            return None, None
        vals = [0.0] * 6
        for s in sb[key]:
            i = STAGE_MAP.get(s["stage"])
            if i is None:
                unknown.append(s["stage"])
                continue
            vals[i] += s["share_percent"]
        rows.append(vals)
    return rows, sorted(set(unknown))


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


def main():
    rundir = sys.argv[1]
    outroot = sys.argv[2] if len(sys.argv) > 2 else "charts"
    run = json.load(open(os.path.join(rundir, "results.json"), encoding="utf-8"))
    fps = best_points(run)
    joules, jfield = energy_points(run)
    if joules is None:
        print("  ВНИМАНИЕ: в results.json нет блока energy с джоулями на кадр. "
              "Есть блоки: %s. Картинку энергии пропускаю." % ", ".join(jfield))
    else:
        print("  джоули на кадр беру из блока energy, поле %s" % jfield)
    stages, unknown = stage_points(run)
    if stages is None:
        print("  ВНИМАНИЕ: в results.json нет блока stage_breakdown со всеми "
              "четырьмя строками (%s). Картинку разбора по стадиям пропускаю."
              % ", ".join(STAGE_ROWS))
    elif unknown:
        print("  ВНИМАНИЕ: незнакомые имена стадий, они не попали на картинку: "
              "%s" % ", ".join(unknown))
    date_iso = run["environment"]["date"][:10]              # 2026-08-24
    y, m, d = date_iso.split("-")
    order = [("2k", "irrev"), ("2k", "rev"), ("4k", "irrev"), ("4k", "rev")]

    for lang in ("ru", "en"):
        T = TEXT[lang]
        date = ("%s.%s.%s" % (d, m, y)) if lang == "ru" else date_iso
        sub = T["sub"].format(date=date)
        outdir = os.path.join(outroot, lang)
        os.makedirs(outdir, exist_ok=True)
        labels = [T["rows"][k] for k in order]

        _DECIMAL_COMMA[0] = (lang == "ru")
        _LANG[0] = T
        enc = [(fps[("fv", "E") + k], fps[("nv", "E") + k]) for k in order]
        dec = [(fps[("fv", "D") + k], fps[("nv", "D") + k]) for k in order]
        made = []
        made += save(chart_one(enc, labels, T["enc"], sub, T["x"],
                               ratio_label=T["ratio"], ratio_head=T["ratio_head"],
                               ratio_head_dif=T["ratio_head_dif"]),
                     outdir, "j2k-encode-4090-%s" % date_iso)
        made += save(chart_one(dec, labels, T["dec"], sub, T["x"],
                               ratio_label=T["ratio"], ratio_head=T["ratio_head"],
                               ratio_head_dif=T["ratio_head_dif"]),
                     outdir, "j2k-decode-4090-%s" % date_iso)

        # сводная: только режим с потерями, две строки
        srows = ["2k", "4k"]
        sl = [(fps[("fv", "E", t, "irrev")], fps[("nv", "E", t, "irrev")]) for t in srows]
        sr = [(fps[("fv", "D", t, "irrev")], fps[("nv", "D", t, "irrev")]) for t in srows]
        made += save(chart_two(sl, sr, [T["sum_rows"][t] for t in srows],
                               T["sum"], T["sub_sum"].format(date=date),
                               T["x"], T["panels"], ratio_label=T["ratio"],
                               ratio_head=T["ratio_head"],
                               ratio_head_dif=T["ratio_head_dif"]),
                     outdir, "j2k-summary-%s" % date_iso)

        # энергия на кадр: те же четыре строки, две половины, общая шкала
        if joules is not None:
            je = [(joules[("fv", "E") + k], joules[("nv", "E") + k]) for k in order]
            jd = [(joules[("fv", "D") + k], joules[("nv", "D") + k]) for k in order]
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
            # порядок строк задан в STAGE_ROWS: 2K обе, потом 4K обе
            made += save(chart_stages(stages, list(T["stage_rows"]),
                                      list(T["stage_names"]), T["stages"],
                                      T["stages_sub"].format(date=date),
                                      T["stages_x"]),
                         outdir, "j2k-stages-4090-%s" % date_iso)
        for p, w, h, sz in made:
            print("  %-58s %4dx%-4d %6d байт" % (os.path.relpath(p, outroot), w, h, sz))
    print("готово")


if __name__ == "__main__":
    main()
