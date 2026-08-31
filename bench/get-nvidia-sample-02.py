# -*- coding: utf-8 -*-
# get-nvidia-sample-02.py
# версия 02 от 31.08.2026, заменяет 01 — её можно удалить
#
# Забирает исходники примеров NVIDIA для JPEG2000 и печатает команды сборки.
# Ничего не меняет в самих файлах — в этом весь смысл.
#
# ЧТО ИЗМЕНИЛОСЬ ПРОТИВ ВЕРСИИ 01
#
#   1. Качается не одна программа, а обе: декодер и КОДЕР. Ступень 1 нашего
#      прогона стала двусторонней, а версия 01 знала только про декодер.
#   2. Каждая ложится в свою папку — decoder и encoder. У обеих внутри файл
#      называется CMakeLists.txt, в одной папке они бы затёрли друг друга.
#   3. Подсказка в конце называет нынешний скрипт прогона и оба его ключа.
#      Версия 01 звала j2k-stock-threads-02.py, которого больше нет.
#   4. Файл, которого в репозитории не оказалось, больше не роняет остальное:
#      README не нужен для сборки, и его отсутствие теперь просто отмечается.
#   5. Имена готовых программ названы по их CMakeLists.txt, а не по README.
#      У декодера они у NVIDIA расходятся: README зовёт программу
#      nvjpeg2k_decode_sample, а add_executable собирает
#      nvjpeg2000_decode_sample. Кодер собирается как nvjpeg2k_encode.
#
# ПОЧЕМУ ФАЙЛЫ КАЧАЮТСЯ, А НЕ ЛЕЖАТ В АРХИВЕ
#
# Ступень 1 отвечает на вопрос «что даёт продукт NVIDIA как есть». Ответ имеет
# силу ровно до тех пор, пока программа — их, слово в слово. Копия, прошедшая
# через чужие руки, этой силы не имеет: любой читатель вправе спросить, не
# правили ли мы её. Поэтому файлы берутся из репозитория NVIDIA, а скрипт
# печатает размер и контрольную сумму каждого — видно, что именно скачано.
#
#     python get-nvidia-sample-02.py --dir D:\nvj2k
#     python get-nvidia-sample-02.py --dir D:\nvj2k --only encoder
#     python get-nvidia-sample-02.py --dir D:\nvj2k --ref master
#
# Повторный запуск безопасен, результат тот же: файлы перезаписываются теми же.
# Сети нет или не пускает — скрипт напечатает адреса, файлы можно взять
# браузером и положить в те же папки руками.

import os
import sys
import hashlib
import argparse
import urllib.request

VERSION = "get-nvidia-sample-02 от 31.08.2026"

RAW = "https://raw.githubusercontent.com/NVIDIA/CUDALibrarySamples/%s/%s"

# Две программы. Имя папки на диске короткое, чтобы пути в командах сборки не
# разъезжались; путь в репозитории — как у NVIDIA.
SAMPLES = [
    {"key": "decoder",
     "path": "nvJPEG2000/nvJPEG2000-Decoder",
     # Имя берётся из их же CMakeLists.txt (add_executable), а не из README:
     # в README декодера написано nvjpeg2k_decode_sample, а собирается
     # nvjpeg2000_decode_sample. Расходятся они у NVIDIA, не у нас.
     "exe": "nvjpeg2000_decode_sample",
     "what": "декодирование",
     "files": ["nvjpeg2000DecodeSample.cpp", "nvjpeg2000DecodeSample.h",
               "CMakeLists.txt"],
     "optional": ["README.md"]},
    {"key": "encoder",
     "path": "nvJPEG2000/nvJPEG2000-Encoder",
     "exe": "nvjpeg2k_encode",
     "what": "кодирование",
     "files": ["nvjpeg2k_encode.cpp", "nvjpeg2k_encode.h", "CMakeLists.txt"],
     "optional": ["README.md"]},
]
# В корне репозитория файл называется LICENSE.TXT, заглавными. Версия 01
# искала три написания в нижнем регистре и лицензию не находила ни разу —
# raw.githubusercontent к регистру чувствителен.
LICENSES = ["LICENSE.TXT", "LICENSE", "LICENSE.md", "LICENSE.txt"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fastvideo-bench"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_one(sample, out, ref):
    """Одна программа. Возвращает (всё ли на месте, список адресов)."""
    folder = os.path.join(out, sample["key"])
    if not os.path.isdir(folder):
        os.makedirs(folder)
    print("\n%s — %s" % (sample["key"], sample["what"]))
    print("  папка: %s" % folder)
    ok, urls = True, []
    for name in sample["files"] + sample["optional"]:
        needed = name in sample["files"]
        url = RAW % (ref, "%s/%s" % (sample["path"], name))
        if needed:
            urls.append(url)
        try:
            data = get(url)
        except Exception as e:
            if needed:
                print("  %-30s НЕ СКАЧАЛСЯ: %s" % (name, e))
                ok = False
            else:
                # README для сборки не нужен: его отсутствие — заметка, а не
                # причина останавливаться.
                print("  %-30s нет в репозитории, для сборки не нужен" % name)
            continue
        open(os.path.join(folder, name), "wb").write(data)
        print("  %-30s %7d байт   md5 %s"
              % (name, len(data), hashlib.md5(data).hexdigest()))
    return ok, urls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="nvidia-sample",
                    help="куда положить исходники")
    ap.add_argument("--ref", default="master", help="ветка или хеш коммита")
    ap.add_argument("--only", choices=["decoder", "encoder"], default="",
                    help="забрать только одну программу")
    args = ap.parse_args()

    print(VERSION)
    out = os.path.abspath(args.dir)
    if not os.path.isdir(out):
        os.makedirs(out)
    print("Папка: %s" % out)
    print("Ветка: %s" % args.ref)

    want = [s for s in SAMPLES if not args.only or s["key"] == args.only]
    ok, urls = True, []
    for sample in want:
        good, u = fetch_one(sample, out, args.ref)
        ok = ok and good
        urls += u

    print("")
    for name in LICENSES:
        try:
            data = get(RAW % (args.ref, name))
        except Exception:
            continue
        open(os.path.join(out, name), "wb").write(data)
        print("  %-30s %7d байт   md5 %s   (лицензия NVIDIA)"
              % (name, len(data), hashlib.md5(data).hexdigest()))
        break
    else:
        print("  Файл лицензии не нашёлся — посмотрите его в репозитории NVIDIA.")

    if not ok:
        print("\nЧасть файлов не скачалась. Адреса, чтобы взять браузером:")
        for u in urls:
            print("  %s" % u)
        print("\nКладите их в те же папки: %s\\decoder и %s\\encoder" % (out, out))
        return 1

    print("""
СБОРКА НА WINDOWS

Нужны: свежий драйвер NVIDIA, CUDA Toolkit, CMake 3.17 или новее и сама
библиотека nvJPEG2000 (пакет nvidia-nvjpeg2k-cu12 или загрузка с сайта NVIDIA).

Собирается каждая программа отдельно, командой одного вида:""")
    for sample in want:
        print("""
    cd %s\\%s
    mkdir build
    cd build
    cmake .. -G "Visual Studio 17 2022" -A x64 -DNVJPEG2K_PATH=<путь к nvJPEG2000>
    cmake --build . --config Release

Получится %s.exe в build\\Release."""
              % (out, sample["key"], sample["exe"]))

    print("""
Ключ -DNVJPEG2K_PATH нужен, если библиотека лежит не там, где её ищет CMake: он
сам проверяет папки CUDA Toolkit и, не найдя, останавливается с этим же советом.

ПРОВЕРКА, ЧТО СОБРАЛОСЬ ПРАВИЛЬНО

    nvjpeg2000_decode_sample.exe -i <папка с одним .jp2> -b 1 -t 20 -w 1
    nvjpeg2k_encode.exe -i <папка с одним .ppm> -b 1 -t 20 -w 1 -cblk 32,32

У декодера в выводе должна быть строка «Avg images per sec: ...», у кодера —
«Avg encode speed  (in images per sec): ...». Их и разбирает измерительный
скрипт.

ДАЛЬШЕ

    python j2k-nv-threads-and-states-01.py --selftest ^
        --nv-sample %s\\decoder\\build\\Release\\nvjpeg2000_decode_sample.exe ^
        --nv-encode-sample %s\\encoder\\build\\Release\\nvjpeg2k_encode.exe

Те же два ключа потом у --prepare, --trial и --final.

Ключи самих программ, из их README:

    декодер:  -i images_dir [-b batch_size] [-t total_images] [-w warmup]
              [-o output_dir]
    кодер:    то же плюс [-I] [-cblk w,h] [-q_factor v] [-quantization v]
              [-psnr v] [-ht]
""" % (out, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
