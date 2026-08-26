#!/bin/sh
# Fallback build, in case CMake is not available or is too old.
# Builds the same two executables as CMakeLists.txt does.
#
#   ./build.sh
#   NVJPEG2K_ROOT=/opt/nvjpeg2k CUDA_ROOT=/usr/local/cuda ./build.sh
#
# The two executables land next to this script.

set -e

CUDA_ROOT="${CUDA_ROOT:-/usr/local/cuda}"
NVJPEG2K_ROOT="${NVJPEG2K_ROOT:-/usr/local/nvjpeg2k}"

INC=""
LIB=""

for d in "$CUDA_ROOT/include" "$CUDA_ROOT/targets/aarch64-linux/include" /usr/include; do
    [ -f "$d/cuda_runtime_api.h" ] && INC="$INC -I$d" && break
done
for d in "$CUDA_ROOT/lib64" "$CUDA_ROOT/lib" \
         "$CUDA_ROOT/targets/aarch64-linux/lib" /usr/lib/aarch64-linux-gnu; do
    [ -f "$d/libcudart.so" ] && LIB="$LIB -L$d -Wl,-rpath,$d" && break
done
for d in "$NVJPEG2K_ROOT/include" /usr/include; do
    [ -f "$d/nvjpeg2k.h" ] && INC="$INC -I$d" && break
done
for d in "$NVJPEG2K_ROOT/lib/13" "$NVJPEG2K_ROOT/lib/12" "$NVJPEG2K_ROOT/lib/11" \
         "$NVJPEG2K_ROOT/lib64" "$NVJPEG2K_ROOT/lib" /usr/lib/aarch64-linux-gnu; do
    [ -f "$d/libnvjpeg2k.so" ] && LIB="$LIB -L$d -Wl,-rpath,$d" && break
done

echo "includes:$INC"
echo "libraries:$LIB"

g++ -std=c++11 -O3 -Wall $INC nvj2k_bench.cpp -o nvj2kEncoderSample \
    $LIB -lnvjpeg2k -lcudart -lpthread -ldl
g++ -std=c++11 -O3 -Wall -DBUILD_DECODER $INC nvj2k_bench.cpp -o nvj2kDecoderSample \
    $LIB -lnvjpeg2k -lcudart -lpthread -ldl

echo "built: nvj2kEncoderSample nvj2kDecoderSample"
