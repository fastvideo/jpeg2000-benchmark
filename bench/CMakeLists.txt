# ---------------------------------------------------------------------------
# nvJPEG2000 benchmark harness — two executables from one source
#
#   nvj2kEncoderSample   (default)
#   nvj2kDecoderSample   (the same source with BUILD_DECODER defined)
#
# Both mirror the command line and the printed output of the Fastvideo J2K
# samples, so that one and the same measurement script drives both codecs.
#
# Build (Jetson, Linux, aarch64):
#
#     cmake -B build -DCMAKE_BUILD_TYPE=Release
#     cmake --build build -j
#
# If nvJPEG2000 is not in a standard place, point CMake at it:
#
#     cmake -B build -DCMAKE_BUILD_TYPE=Release -DNVJPEG2K_ROOT=/opt/nvjpeg2k
#
# The two executables land in build/ ; copy them next to the test frames.
# ---------------------------------------------------------------------------

cmake_minimum_required(VERSION 3.10)
project(nvj2k_bench LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

# ---------------------------------------------------------------------------
# CUDA runtime
#
# find_package(CUDAToolkit) needs CMake 3.17. JetPack 5 ships 3.16, so there is
# a manual path as well: look for cuda_runtime_api.h and libcudart next to the
# toolkit that is actually installed.
# ---------------------------------------------------------------------------

set(CUDA_HINTS
    "${CUDA_ROOT}" "$ENV{CUDA_ROOT}"
    "${CUDAToolkit_ROOT}" "$ENV{CUDAToolkit_ROOT}"
    /usr/local/cuda /usr/local/cuda-13.0 /usr/local/cuda-12.6 /usr/local/cuda-12.2
    /usr/local/cuda-11.4 /usr)

if(NOT CMAKE_VERSION VERSION_LESS 3.17)
    find_package(CUDAToolkit QUIET)
endif()

if(TARGET CUDA::cudart)
    set(CUDART_TARGET CUDA::cudart)
    set(CUDA_INCLUDE_DIRS_FOUND "${CUDAToolkit_INCLUDE_DIRS}")
    set(CUDART_WHERE "CUDAToolkit ${CUDAToolkit_VERSION}")
else()
    find_path(CUDA_INCLUDE_DIR cuda_runtime_api.h
              HINTS ${CUDA_HINTS}
              PATH_SUFFIXES include targets/aarch64-linux/include
                            targets/x86_64-linux/include)
    find_library(CUDART_LIBRARY NAMES cudart
                 HINTS ${CUDA_HINTS}
                 PATH_SUFFIXES lib64 lib lib/aarch64-linux-gnu
                               lib/x86_64-linux-gnu
                               targets/aarch64-linux/lib
                               targets/x86_64-linux/lib)
    if(NOT CUDA_INCLUDE_DIR OR NOT CUDART_LIBRARY)
        message(FATAL_ERROR
            "CUDA runtime not found.\n"
            "Point CMake at the toolkit, for example:\n"
            "  cmake -B build -DCUDA_ROOT=/usr/local/cuda")
    endif()
    add_library(cudart_imported UNKNOWN IMPORTED)
    set_target_properties(cudart_imported PROPERTIES
        IMPORTED_LOCATION "${CUDART_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${CUDA_INCLUDE_DIR}")
    set(CUDART_TARGET cudart_imported)
    set(CUDA_INCLUDE_DIRS_FOUND "${CUDA_INCLUDE_DIR}")
    set(CUDART_WHERE "${CUDART_LIBRARY}")
endif()

# ---------------------------------------------------------------------------
# nvJPEG2000
#
# It is a separate download from NVIDIA, not part of the CUDA Toolkit. The
# tarball unpacks into include/ and lib/<cuda major>/ ; the deb package puts the
# header into /usr/include and the library into /usr/lib/<arch>-linux-gnu.
# ---------------------------------------------------------------------------

set(NVJPEG2K_HINTS
    "${NVJPEG2K_ROOT}" "$ENV{NVJPEG2K_ROOT}"
    /usr/local/nvjpeg2k /opt/nvjpeg2k /opt/nvidia/nvjpeg2k
    /usr/local/cuda /usr)

find_path(NVJPEG2K_INCLUDE_DIR nvjpeg2k.h
          HINTS ${NVJPEG2K_HINTS}
          PATH_SUFFIXES include include/nvjpeg2k
                        targets/aarch64-linux/include)

find_library(NVJPEG2K_LIBRARY NAMES nvjpeg2k nvjpeg2k_static
             HINTS ${NVJPEG2K_HINTS}
             PATH_SUFFIXES lib lib64 lib/13 lib/12 lib/11
                           lib/aarch64-linux-gnu lib/x86_64-linux-gnu
                           targets/aarch64-linux/lib)

if(NOT NVJPEG2K_INCLUDE_DIR OR NOT NVJPEG2K_LIBRARY)
    message(FATAL_ERROR
        "nvJPEG2000 not found.\n"
        "It is a separate download from NVIDIA: "
        "https://developer.nvidia.com/nvjpeg2000-downloads\n"
        "Unpack it and point CMake at the folder that holds include/ and lib/:\n"
        "  cmake -B build -DNVJPEG2K_ROOT=/path/to/nvjpeg2k\n"
        "header found: ${NVJPEG2K_INCLUDE_DIR}\n"
        "library found: ${NVJPEG2K_LIBRARY}")
endif()

add_library(nvjpeg2k_imported UNKNOWN IMPORTED)
set_target_properties(nvjpeg2k_imported PROPERTIES
    IMPORTED_LOCATION "${NVJPEG2K_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${NVJPEG2K_INCLUDE_DIR}")

# ---------------------------------------------------------------------------
# threads
# ---------------------------------------------------------------------------

set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

# ---------------------------------------------------------------------------
# the two executables
# ---------------------------------------------------------------------------

set(NVJ2K_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/nvj2k_bench.cpp")
if(NOT EXISTS "${NVJ2K_SOURCE}")
    message(FATAL_ERROR "nvj2k_bench.cpp is not next to CMakeLists.txt")
endif()

foreach(pair "nvj2kEncoderSample;" "nvj2kDecoderSample;BUILD_DECODER")
    list(GET pair 0 target_name)
    list(GET pair 1 target_define)
    add_executable(${target_name} "${NVJ2K_SOURCE}")
    if(target_define)
        target_compile_definitions(${target_name} PRIVATE ${target_define})
    endif()
    target_link_libraries(${target_name}
        PRIVATE nvjpeg2k_imported ${CUDART_TARGET} Threads::Threads ${CMAKE_DL_LIBS})
    if(UNIX)
        # so that the binaries find libnvjpeg2k.so without LD_LIBRARY_PATH
        get_filename_component(NVJPEG2K_LIBDIR "${NVJPEG2K_LIBRARY}" DIRECTORY)
        set_target_properties(${target_name} PROPERTIES
            BUILD_RPATH "${NVJPEG2K_LIBDIR}"
            INSTALL_RPATH "${NVJPEG2K_LIBDIR}")
    endif()
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(${target_name} PRIVATE -O3 -Wall)
    endif()
endforeach()

# ---------------------------------------------------------------------------
# what was found
# ---------------------------------------------------------------------------

message(STATUS "----------------------------------------------------------")
message(STATUS "CUDA runtime : ${CUDART_WHERE}")
message(STATUS "CUDA headers : ${CUDA_INCLUDE_DIRS_FOUND}")
message(STATUS "nvJPEG2000   : ${NVJPEG2K_LIBRARY}")
message(STATUS "nvJPEG2000 h : ${NVJPEG2K_INCLUDE_DIR}")
message(STATUS "build type   : ${CMAKE_BUILD_TYPE}")
message(STATUS "executables  : ${CMAKE_BINARY_DIR}/nvj2kEncoderSample")
message(STATUS "               ${CMAKE_BINARY_DIR}/nvj2kDecoderSample")
message(STATUS "----------------------------------------------------------")
