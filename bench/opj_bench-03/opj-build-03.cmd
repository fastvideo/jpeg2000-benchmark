@echo off
rem ===========================================================================
rem opj-build-03.cmd - version 03, 14 September 2026
rem
rem Builds OpenJPEG and opj_bench twice - an ordinary Release build and one
rem with /arch:AVX2 - and lays the results out the way opj-run-04.py expects.
rem
rem   opj-build-03.cmd <OpenJPEG source> <root for the builds> [opj_bench source]
rem
rem Example:
rem   opj-build-03.cmd D:\_Test\openjpeg-master D:\_Test\opj
rem
rem WHAT WENT WRONG IN VERSION 02, AND WHAT IS DIFFERENT HERE
rem
rem   1. It used whatever opj_bench folder happened to sit next to it, without
rem      looking at what was inside. On the measuring machine that folder held
rem      the OLD sources (opj_bench-02.cpp, a CMakeLists with no build tag), so
rem      both builds produced a file called opj_bench.exe, neither of them knew
rem      its own tag, and the run stopped at the missing opj_bench-avx2.exe.
rem      Version 03 checks the sources before building and says plainly if they
rem      are the old ones.
rem
rem   2. It configured into build folders that already had a CMakeCache.txt
rem      from an earlier attempt, and CMake refused: "generator platform: x64
rem      does not match the platform used previously". The fallback then
rem      quietly configured for the wrong platform. Version 03 removes the four
rem      build folders first - they are regenerable, and a stale cache is the
rem      most common way this build goes wrong.
rem
rem Everything printed here is English on purpose: cmd.exe reads a .cmd file in
rem the console code page, and Russian text comes out as garbage that hides the
rem real error.
rem
rem Every command and every line of compiler output goes to
rem <root>\build-log.txt. If a step fails, send that file.
rem
rem Run it from "x64 Native Tools Command Prompt for VS".
rem ===========================================================================

setlocal enabledelayedexpansion

set "SRC=%~1"
set "ROOT=%~2"
set "BENCH=%~3"
set "HERE=%~dp0"

if "%SRC%"=="" goto :usage
if "%ROOT%"=="" goto :usage

rem --- where the opj_bench sources are ---------------------------------------

if not "%BENCH%"=="" goto :bench_given
if exist "%HERE%opj_bench\CMakeLists.txt" set "BENCH=%HERE%opj_bench"
if "%BENCH%"=="" if exist "D:\_Test\opj_bench\CMakeLists.txt" set "BENCH=D:\_Test\opj_bench"
:bench_given

if "%BENCH%"=="" (
  echo.
  echo ERROR: opj_bench sources not found.
  echo Looked in:
  echo   %HERE%opj_bench
  echo   D:\_Test\opj_bench
  echo Pass the folder as the third argument, or put opj_bench next to this
  echo script.
  exit /b 1
)

rem --- are these the NEW sources? --------------------------------------------
rem This is the check that was missing in version 02 and cost a whole build.

if not exist "%BENCH%\opj_bench-03.cpp" (
  echo.
  echo ERROR: %BENCH% holds the OLD opj_bench sources.
  echo   missing: %BENCH%\opj_bench-03.cpp
  echo.
  echo The old program does not know its own build tag, and both builds would
  echo come out as opj_bench.exe - the comparison would be meaningless.
  echo.
  echo Copy the whole opj_bench folder from the archive over this one:
  echo   fastvideo.ru\draft\jpeg2000-gpu-vs-cpu\code\opj_bench\
  exit /b 1
)

findstr /c:"OPJ_BENCH_TAG" "%BENCH%\CMakeLists.txt" >nul
if errorlevel 1 (
  echo.
  echo ERROR: %BENCH%\CMakeLists.txt is the OLD one - no OPJ_BENCH_TAG in it.
  echo.
  echo Both builds would come out named opj_bench.exe and neither would know
  echo which library it was built against.
  echo.
  echo Copy the whole opj_bench folder from the archive over this one:
  echo   fastvideo.ru\draft\jpeg2000-gpu-vs-cpu\code\opj_bench\
  exit /b 1
)

rem --- the rest of the checks ------------------------------------------------

if not exist "%SRC%\CMakeLists.txt" (
  echo.
  echo ERROR: no CMakeLists.txt in "%SRC%"
  echo That folder is not an OpenJPEG source tree.
  exit /b 1
)

where cmake >nul 2>&1
if errorlevel 1 (
  echo.
  echo ERROR: cmake not found in PATH.
  exit /b 1
)

where cl >nul 2>&1
if errorlevel 1 (
  echo.
  echo ERROR: cl.exe not found in PATH.
  echo This script must run inside the Visual Studio developer environment.
  echo Open "x64 Native Tools Command Prompt for VS" and run it from there.
  exit /b 1
)

if not exist "%ROOT%" mkdir "%ROOT%"
set "LOG=%ROOT%\build-log.txt"
(echo opj-build-03, %DATE% %TIME%)> "%LOG%"
(echo openjpeg source: %SRC%)>> "%LOG%"
(echo opj_bench source: %BENCH%)>> "%LOG%"
(echo root:            %ROOT%)>> "%LOG%"
(echo.)>> "%LOG%"

echo.
echo OpenJPEG source:  %SRC%
echo opj_bench source: %BENCH%
echo Build root:       %ROOT%
echo Log file:         %LOG%

rem --- clean the build folders ------------------------------------------------
rem A left-over CMakeCache.txt from an earlier attempt is the single most
rem common reason this build fails, and the error it gives ("does not match the
rem platform used previously") points at the cache, not at the cause. These
rem four folders are regenerable, so they are simply removed.

echo.
echo === removing old build folders ===
(echo === removing old build folders ===)>> "%LOG%"
for %%D in ("%ROOT%\lib\plain" "%ROOT%\lib\avx2" "%ROOT%\bench\plain" "%ROOT%\bench\avx2") do (
  if exist %%D (
    echo   %%~D
    rmdir /s /q %%D
  )
)

rem --- 1 of 4: the library, ordinary build -----------------------------------

set "STEP=1 of 4: library, ordinary build"
set "CFGDIR=%ROOT%\lib\plain"
echo.
echo === %STEP% ===
(echo === %STEP% ===)>> "%LOG%"
echo cmake -S "%SRC%" -B "%CFGDIR%" -A x64 -DBUILD_SHARED_LIBS=ON -DBUILD_CODEC=OFF
(echo cmake -S "%SRC%" -B "%CFGDIR%" -A x64 -DBUILD_SHARED_LIBS=ON -DBUILD_CODEC=OFF)>> "%LOG%"
cmake -S "%SRC%" -B "%CFGDIR%" -A x64 -DBUILD_SHARED_LIBS=ON -DBUILD_CODEC=OFF >> "%LOG%" 2>&1
if errorlevel 1 goto :cfgfailed
cmake --build "%CFGDIR%" --config Release >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
call :need_file "%CFGDIR%\bin\Release\openjp2.dll" "the plain library"
if errorlevel 1 goto :quiet_fail

rem --- 2 of 4: the library with /arch:AVX2 -----------------------------------
rem
rem The flag is ADDED through CMAKE_C_FLAGS. Overwriting CMAKE_C_FLAGS_RELEASE
rem would drop /MD from it, the library would go to the static C runtime while
rem opj_bench stays on the dynamic one, and the link would fail with LNK2038.
rem
rem Do not add /fp:fast here. It changes floating point rules, the lossy path
rem (the 9/7 wavelet) is floating point, and the compressed file would come out
rem different - then the two builds would no longer be doing the same work.

set "STEP=2 of 4: library with /arch:AVX2"
set "CFGDIR=%ROOT%\lib\avx2"
echo.
echo === %STEP% ===
(echo === %STEP% ===)>> "%LOG%"
echo cmake -S "%SRC%" -B "%CFGDIR%" -A x64 -DBUILD_SHARED_LIBS=ON -DBUILD_CODEC=OFF -DCMAKE_C_FLAGS=/arch:AVX2
(echo cmake -S "%SRC%" -B "%CFGDIR%" -A x64 -DCMAKE_C_FLAGS=/arch:AVX2)>> "%LOG%"
cmake -S "%SRC%" -B "%CFGDIR%" -A x64 -DBUILD_SHARED_LIBS=ON -DBUILD_CODEC=OFF -DCMAKE_C_FLAGS="/arch:AVX2" >> "%LOG%" 2>&1
if errorlevel 1 goto :cfgfailed
cmake --build "%CFGDIR%" --config Release >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
call :need_file "%CFGDIR%\bin\Release\openjp2.dll" "the AVX2 library"
if errorlevel 1 goto :quiet_fail

rem --- 3 of 4: opj_bench against the ordinary library ------------------------

set "STEP=3 of 4: opj_bench against the ordinary library"
set "CFGDIR=%ROOT%\bench\plain"
echo.
echo === %STEP% ===
(echo === %STEP% ===)>> "%LOG%"
echo cmake -S "%BENCH%" -B "%CFGDIR%" -A x64 -DOPJ_ROOT="%SRC%" -DOPJ_BUILD="%ROOT%\lib\plain" -DOPJ_BENCH_TAG=plain
(echo cmake -S "%BENCH%" -B "%CFGDIR%" -A x64 -DOPJ_BENCH_TAG=plain)>> "%LOG%"
cmake -S "%BENCH%" -B "%CFGDIR%" -A x64 -DOPJ_ROOT="%SRC%" -DOPJ_BUILD="%ROOT%\lib\plain" -DOPJ_BENCH_TAG=plain >> "%LOG%" 2>&1
if errorlevel 1 goto :cfgfailed
cmake --build "%CFGDIR%" --config Release >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
call :need_exe "%CFGDIR%\Release\opj_bench.exe" "%CFGDIR%" "plain"
if errorlevel 1 goto :quiet_fail

rem --- 4 of 4: opj_bench against the AVX2 library ----------------------------
rem
rem opj_bench itself deliberately does NOT get /arch:AVX2. Its own code hardly
rem takes part in the measurement, and giving the flag to both halves would
rem leave it unclear which half the difference came from.

set "STEP=4 of 4: opj_bench against the AVX2 library"
set "CFGDIR=%ROOT%\bench\avx2"
echo.
echo === %STEP% ===
(echo === %STEP% ===)>> "%LOG%"
echo cmake -S "%BENCH%" -B "%CFGDIR%" -A x64 -DOPJ_ROOT="%SRC%" -DOPJ_BUILD="%ROOT%\lib\avx2" -DOPJ_BENCH_TAG=avx2
(echo cmake -S "%BENCH%" -B "%CFGDIR%" -A x64 -DOPJ_BENCH_TAG=avx2)>> "%LOG%"
cmake -S "%BENCH%" -B "%CFGDIR%" -A x64 -DOPJ_ROOT="%SRC%" -DOPJ_BUILD="%ROOT%\lib\avx2" -DOPJ_BENCH_TAG=avx2 >> "%LOG%" 2>&1
if errorlevel 1 goto :cfgfailed
cmake --build "%CFGDIR%" --config Release >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
call :need_exe "%CFGDIR%\Release\opj_bench-avx2.exe" "%CFGDIR%" "avx2"
if errorlevel 1 goto :quiet_fail

rem --- laying out the ready sets ---------------------------------------------
rem
rem A build is a FOLDER, not a file: on Windows the library is loaded from
rem beside the executable. Two executables in one folder would both measure
rem whichever dll happens to be there.

set "STEP=laying out the ready sets"
echo.
echo === %STEP% ===
(echo === %STEP% ===)>> "%LOG%"

if exist "%ROOT%\builds\plain" rmdir /s /q "%ROOT%\builds\plain"
if exist "%ROOT%\builds\avx2"  rmdir /s /q "%ROOT%\builds\avx2"
mkdir "%ROOT%\builds\plain"
mkdir "%ROOT%\builds\avx2"

copy /y "%ROOT%\bench\plain\Release\opj_bench.exe"     "%ROOT%\builds\plain\" >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
copy /y "%ROOT%\bench\plain\Release\openjp2.dll"       "%ROOT%\builds\plain\" >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
copy /y "%ROOT%\bench\avx2\Release\opj_bench-avx2.exe" "%ROOT%\builds\avx2\"  >> "%LOG%" 2>&1
if errorlevel 1 goto :failed
copy /y "%ROOT%\bench\avx2\Release\openjp2.dll"        "%ROOT%\builds\avx2\"  >> "%LOG%" 2>&1
if errorlevel 1 goto :failed

echo   %ROOT%\builds\plain\opj_bench.exe
echo   %ROOT%\builds\avx2\opj_bench-avx2.exe

rem --- what the two builds say about themselves ------------------------------

echo.
echo === build tags ===
(echo === build tags ===)>> "%LOG%"
"%ROOT%\builds\plain\opj_bench.exe" -version
"%ROOT%\builds\avx2\opj_bench-avx2.exe" -version
"%ROOT%\builds\plain\opj_bench.exe" -version >> "%LOG%" 2>&1
"%ROOT%\builds\avx2\opj_bench-avx2.exe" -version >> "%LOG%" 2>&1

set "TAGFAIL="
"%ROOT%\builds\plain\opj_bench.exe" -version | findstr /c:"Build: plain" >nul
if errorlevel 1 set "TAGFAIL=1"
"%ROOT%\builds\avx2\opj_bench-avx2.exe" -version | findstr /c:"Build: avx2" >nul
if errorlevel 1 set "TAGFAIL=1"

if defined TAGFAIL (
  echo.
  echo ERROR: the two builds do not report the tags they should.
  echo Expected "Build: plain" and "Build: avx2".
  echo The usual cause is the wrong openjp2.dll sitting next to an executable.
  echo Check both folders under %ROOT%\builds
  exit /b 1
)

rem --- did the flag actually reach the compiler? -----------------------------

echo.
echo === checking that /arch:AVX2 reached the library ===
(echo === checking that /arch:AVX2 reached the library ===)>> "%LOG%"
where dumpbin >nul 2>&1
if errorlevel 1 (
  echo dumpbin not found, skipping this check.
) else (
  dumpbin /disasm:nobytes "%ROOT%\builds\plain\openjp2.dll" > "%ROOT%\dis-plain.txt" 2>>"%LOG%"
  dumpbin /disasm:nobytes "%ROOT%\builds\avx2\openjp2.dll"  > "%ROOT%\dis-avx2.txt"  2>>"%LOG%"
  for /f %%i in ('findstr /c:"ymm" "%ROOT%\dis-plain.txt" ^| find /c /v ""') do set "NPLAIN=%%i"
  for /f %%i in ('findstr /c:"ymm" "%ROOT%\dis-avx2.txt"  ^| find /c /v ""') do set "NAVX2=%%i"
  echo   ymm registers in the plain library: !NPLAIN!
  echo   ymm registers in the AVX2 library:  !NAVX2!
  (echo   ymm plain !NPLAIN! avx2 !NAVX2!)>> "%LOG%"
  echo   Without /arch the compiler stays on SSE2 and xmm registers, so the
  echo   second number should be much larger than the first.
  del "%ROOT%\dis-plain.txt" "%ROOT%\dis-avx2.txt" >nul 2>&1
)

echo.
echo === done ===
echo Now measure:
echo   python "%HERE%opj-run-04.py"        show what was found
echo   python "%HERE%opj-run-04.py" --do   measure
echo.
exit /b 0

rem ---------------------------------------------------------------------------

:need_file
if not exist %1 (
  echo.
  echo ERROR: the build finished but %~2 is missing.
  echo Expected: %~1
  echo Look in %LOG% for the reason.
  exit /b 1
)
exit /b 0

:need_exe
rem %1 expected exe, %2 the build folder, %3 the tag
if exist %1 exit /b 0
echo.
echo ERROR: the build finished but the executable is not where it should be.
echo Expected: %~1
if exist "%~2\Release\opj_bench.exe" (
  echo Found instead: %~2\Release\opj_bench.exe
  echo.
  echo That means CMake did not see the build tag, so both builds would be
  echo called opj_bench.exe. The opj_bench sources in
  echo   %BENCH%
  echo are the old ones. Copy the whole opj_bench folder from the archive:
  echo   fastvideo.ru\draft\jpeg2000-gpu-vs-cpu\code\opj_bench\
  echo A configured build prints a line "-- Build tag: %~3"; look for it in
  echo %LOG%
)
exit /b 1

:cfgfailed
echo.
echo ===========================================================================
echo CMAKE CONFIGURE FAILED at step: %STEP%
echo ===========================================================================
echo.
powershell -NoProfile -Command "Get-Content -Tail 30 -LiteralPath '%LOG%'" 2>nul
echo.
echo Full log: %LOG%
exit /b 1

:failed
echo.
echo ===========================================================================
echo BUILD FAILED at step: %STEP%
echo ===========================================================================
echo.
echo The last 40 lines of the log:
echo.
powershell -NoProfile -Command "Get-Content -Tail 40 -LiteralPath '%LOG%'" 2>nul
echo.
echo Full log: %LOG%
echo Send that file and the step name above.
exit /b 1

:quiet_fail
echo.
echo Stopped at step: %STEP%
echo Full log: %LOG%
exit /b 1

:usage
echo.
echo Usage:
echo   opj-build-03.cmd ^<OpenJPEG source^> ^<root for the builds^> [opj_bench source]
echo.
echo Example:
echo   opj-build-03.cmd D:\_Test\openjpeg-master D:\_Test\opj
echo.
echo The opj_bench sources are looked for next to this script, then in
echo D:\_Test\opj_bench. They must be the NEW ones: opj_bench-03.cpp and a
echo CMakeLists.txt that knows OPJ_BENCH_TAG.
echo.
echo Run it from "x64 Native Tools Command Prompt for VS".
echo.
exit /b 1
