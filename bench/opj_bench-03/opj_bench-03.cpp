// opj_bench-03.cpp
// version 03, 14 September 2026
//
// WHAT IS NEW IN 03
//
//   1. The program says which build it is. A line "Build: <tag>" is printed
//      at the start, where the tag comes from the compiler define
//      OPJ_BENCH_TAG (CMake sets it; the default is "plain"). Next to it the
//      program prints whether IT was compiled with AVX2, detected from the
//      compiler's own macro - a tag cannot lie about that part.
//      This exists because two builds of the LIBRARY are now compared, and
//      two executables that look alike must not be confused in a log.
//   2. The program prints its peak working set at the end. The 4K collapse is
//      explained by memory in the article, and an explanation about memory
//      should carry a memory number.
//
// IMPORTANT AND EASY TO GET WRONG: the AVX2 comparison is about the LIBRARY,
// not about this file. This file does no arithmetic worth vectorising. Two
// separate OpenJPEG build trees are needed, and each executable must sit in
// its own directory with its own openjp2.dll - Windows loads the dll from
// beside the executable, so two executables sharing a directory would both
// measure whichever dll happens to be there.
//
// Measurement harness for the OpenJPEG codec, built to the same contract as
// nvj2k_bench-03: the same command-line keys and the same summary lines, so
// that bench-06.py drives all three codecs without knowing they differ.
//
// WHAT IS MEASURED AND WHERE THE BOUNDARIES ARE
//
// The frame is read from disk once, before anything is timed, and converted
// into the layout the library wants. After that the program works in memory:
// nothing is read from or written to disk inside the measured region. That is
// the same boundary the article calls "from host memory to host memory"
// (section 4.2), and for a CPU codec it is the natural one.
//
// This is why the standard opj_compress is not used for the measurement: it
// starts a process and reads a file for every frame, and both land inside its
// timer. We were bitten by exactly that with the standard NVIDIA sample.
//
// WHAT COUNTS AS ONE FRAME OF WORK, AND WHY IT INCLUDES MORE THAN opj_encode
//
// OpenJPEG has no reusable encoder state: a codec object encodes once and is
// then done. And opj_encode TAKES the pixel buffers - after it returns, the
// image's component pointers are null, because the library either freed them
// or moved them into its own tile.
//
// So one frame is: allocate fresh pixel buffers, copy the pristine planes into
// them, create the codec, configure it, encode, destroy the codec. All of it
// is timed, because all of it is what an application must do per frame. The
// handover - buffers plus copy - is reported separately, so that its share is
// known rather than argued about.
//
// TWO WAYS TO USE THE MACHINE, AND BOTH ARE MEASURED
//
//   -thread N      N worker threads, each encoding whole frames of its own.
//                  This is the scheme we use for the GPU codecs.
//   -opjthreads K  OpenJPEG's own thread pool inside one frame
//                  (opj_codec_set_threads; encoder threading exists since
//                  OpenJPEG 2.4.0).
//
// They combine: N x K threads in total. Comparing a single-threaded OpenJPEG
// against our best point on thirty-two threads would be the same "never had a
// fair chance" that we objected to in the standard NVIDIA sample, so the best
// point has to be found by search over both.
//
// CALIBRATION
//
// With -targetsize the program finds the compression ratio that lands on the
// requested byte count, by halving the interval - the same procedure used for
// the nvJPEG2000 quality factor. The knob here is OpenJPEG's compression ratio
// (-r), not a quality factor; the line is printed as "q =" only because that
// is what the harness parses.
//
// BUILD
//
//   cmake -S . -B build -DCMAKE_PREFIX_PATH=D:/_Test/openjpeg-master/bin
//   cmake --build build --config Release
//
// USAGE
//
//   opj_bench -i 2k_wild.ppm -a irrev -r 10.34 -repeat 2000 -thread 8
//   opj_bench -i 2k_wild.ppm -a irrev -targetsize 601703
//   opj_bench -decode -i frame.jp2 -repeat 2000 -thread 8

#include <openjpeg.h>

#include <atomic>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#pragma comment(lib, "psapi.lib")
#else
#include <sys/resource.h>
#endif

// Set by CMake as a bare token: -DOPJ_BENCH_TAG=plain. The preprocessor turns
// it into a string here, so that nothing depends on CMake and the compiler
// agreeing about how to escape a quote inside /D. "plain" is the ordinary
// Release build; "avx2" is the one built against an OpenJPEG compiled with
// /arch:AVX2.
#ifndef OPJ_BENCH_TAG
#define OPJ_BENCH_TAG plain
#endif
#define OPJ_BENCH_STR2(x) #x
#define OPJ_BENCH_STR(x) OPJ_BENCH_STR2(x)
#define OPJ_BENCH_TAG_STR OPJ_BENCH_STR(OPJ_BENCH_TAG)

// Whether THIS file was compiled with AVX2. Not the same question as whether
// the library was, and the program says so in as many words.
static const char* compiledWithAvx2() {
#if defined(__AVX512F__)
    return "yes, AVX-512";
#elif defined(__AVX2__)
    return "yes";
#elif defined(__AVX__)
    return "AVX only";
#else
    return "no";
#endif
}

// Peak working set of the process, megabytes. The 4K collapse is explained by
// the number of frames alive in memory at once, and that explanation should
// come with a measured number rather than an arithmetic estimate.
static double peakWorkingSetMB() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS pmc;
    if (!GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc)))
        return -1.0;
    return (double)pmc.PeakWorkingSetSize / (1024.0 * 1024.0);
#else
    struct rusage r;
    if (getrusage(RUSAGE_SELF, &r) != 0) return -1.0;
    // Linux reports kilobytes, macOS bytes.
#ifdef __APPLE__
    return (double)r.ru_maxrss / (1024.0 * 1024.0);
#else
    return (double)r.ru_maxrss / 1024.0;
#endif
#endif
}

typedef std::chrono::steady_clock Clock;

static double msSince(Clock::time_point t0) {
    return std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
}

// ---------------------------------------------------------------------------
// processor time of this process
// ---------------------------------------------------------------------------
// Needed so that the number of busy cores can be worked out for the MEASURED
// REGION alone. Counting it over the whole process mixes in everything that
// happens before the timer starts - reading the frame, the warm-up - and on a
// thirty-two thread run that halves the answer. (Found on the run of
// 11.09.2026: encoding reported 14.5 busy cores where the real figure inside
// the measured region was about 28. Decoding, which has almost no warm-up,
// reported 30.7 and was right. That difference is what gave it away.)

static double cpuSeconds() {
#ifdef _WIN32
    FILETIME c, e, k, u;
    if (!GetProcessTimes(GetCurrentProcess(), &c, &e, &k, &u)) return -1.0;
    unsigned long long kk = ((unsigned long long)k.dwHighDateTime << 32)
                          | k.dwLowDateTime;
    unsigned long long uu = ((unsigned long long)u.dwHighDateTime << 32)
                          | u.dwLowDateTime;
    return (double)(kk + uu) / 1e7;
#else
    struct rusage r;
    if (getrusage(RUSAGE_SELF, &r) != 0) return -1.0;
    return r.ru_utime.tv_sec + r.ru_utime.tv_usec / 1e6
         + r.ru_stime.tv_sec + r.ru_stime.tv_usec / 1e6;
#endif
}

static void printCores(double cpu0, double cpu1, double wallMs) {
    if (cpu0 < 0 || cpu1 < 0 || wallMs <= 0) return;
    double cpu = cpu1 - cpu0;
    std::printf("- CPU time inside the measured region: %.2f s; "
                "logical cores busy: %.2f\n", cpu, cpu / (wallMs / 1000.0));
}

// ---------------------------------------------------------------------------
// diagnostics from the library
// ---------------------------------------------------------------------------
// Silent by default: a warning printed once per frame would drown the output
// of a run with thousands of frames. Errors are always shown - an error that
// nobody sees turns a failed run into a fast one.

static std::atomic<int> g_errors(0);

// opj_codec_set_threads can refuse - the library may be built without thread
// support, and an encoder pool is younger than a decoder pool. A refusal must
// be said out loud: a run that quietly used one thread while the log says
// eight is a wrong measurement that looks like a right one.
static std::atomic<int> g_poolRefused(0);

static void setPool(opj_codec_t* codec, int n) {
    if (n <= 1) return;
    if (!opj_codec_set_threads(codec, n)) g_poolRefused.fetch_add(1);
}

static void on_error(const char* msg, void*) {
    if (g_errors.fetch_add(1) < 5) std::fprintf(stderr, "OpenJPEG error: %s", msg);
}
static void on_warn(const char*, void*) {}
static void on_info(const char*, void*) {}

// ---------------------------------------------------------------------------
// memory streams
// ---------------------------------------------------------------------------
// OpenJPEG has no built-in memory stream, but it lets the caller supply the
// four functions it needs. Writing to memory is required here: a stream backed
// by a file would put disk traffic inside the measured region.

struct MemOut {
    std::vector<unsigned char> buf;
    OPJ_OFF_T pos;
    MemOut() : pos(0) { buf.reserve(16u << 20); }
};

static OPJ_SIZE_T mem_write(void* p, OPJ_SIZE_T n, void* ud) {
    MemOut* m = (MemOut*)ud;
    if ((OPJ_SIZE_T)m->pos + n > m->buf.size()) m->buf.resize((size_t)m->pos + n);
    std::memcpy(&m->buf[(size_t)m->pos], p, n);
    m->pos += (OPJ_OFF_T)n;
    return n;
}
static OPJ_OFF_T mem_skip_out(OPJ_OFF_T n, void* ud) {
    MemOut* m = (MemOut*)ud;
    m->pos += n;
    if ((OPJ_SIZE_T)m->pos > m->buf.size()) m->buf.resize((size_t)m->pos);
    return n;
}
static OPJ_BOOL mem_seek_out(OPJ_OFF_T n, void* ud) {
    MemOut* m = (MemOut*)ud;
    if (n < 0) return OPJ_FALSE;
    if ((OPJ_SIZE_T)n > m->buf.size()) m->buf.resize((size_t)n);
    m->pos = n;
    return OPJ_TRUE;
}

struct MemIn {
    const unsigned char* data;
    OPJ_SIZE_T len;
    OPJ_OFF_T pos;
};

static OPJ_SIZE_T mem_read(void* p, OPJ_SIZE_T n, void* ud) {
    MemIn* m = (MemIn*)ud;
    if ((OPJ_SIZE_T)m->pos >= m->len) return (OPJ_SIZE_T)-1;
    OPJ_SIZE_T left = m->len - (OPJ_SIZE_T)m->pos;
    OPJ_SIZE_T take = n < left ? n : left;
    std::memcpy(p, m->data + m->pos, take);
    m->pos += (OPJ_OFF_T)take;
    return take;
}
static OPJ_OFF_T mem_skip_in(OPJ_OFF_T n, void* ud) {
    MemIn* m = (MemIn*)ud;
    m->pos += n;
    if (m->pos < 0) m->pos = 0;
    if ((OPJ_SIZE_T)m->pos > m->len) m->pos = (OPJ_OFF_T)m->len;
    return n;
}
static OPJ_BOOL mem_seek_in(OPJ_OFF_T n, void* ud) {
    MemIn* m = (MemIn*)ud;
    if (n < 0 || (OPJ_SIZE_T)n > m->len) return OPJ_FALSE;
    m->pos = n;
    return OPJ_TRUE;
}

static opj_stream_t* out_stream(MemOut* m) {
    opj_stream_t* s = opj_stream_default_create(OPJ_FALSE);
    if (!s) return 0;
    opj_stream_set_user_data(s, m, 0);
    opj_stream_set_write_function(s, mem_write);
    opj_stream_set_skip_function(s, mem_skip_out);
    opj_stream_set_seek_function(s, mem_seek_out);
    return s;
}

static opj_stream_t* in_stream(MemIn* m) {
    opj_stream_t* s = opj_stream_default_create(OPJ_TRUE);
    if (!s) return 0;
    opj_stream_set_user_data(s, m, 0);
    opj_stream_set_user_data_length(s, m->len);
    opj_stream_set_read_function(s, mem_read);
    opj_stream_set_skip_function(s, mem_skip_in);
    opj_stream_set_seek_function(s, mem_seek_in);
    return s;
}

// ---------------------------------------------------------------------------
// input
// ---------------------------------------------------------------------------

struct Frame {
    int w, h, comps, prec;
    std::vector<std::vector<OPJ_INT32> > plane;   // pristine, never encoded
};

static std::vector<unsigned char> readFile(const std::string& path) {
    std::vector<unsigned char> v;
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) {
        std::fprintf(stderr, "ERROR: cannot open %s\n", path.c_str());
        std::exit(1);
    }
    std::fseek(f, 0, SEEK_END);
    long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    v.resize((size_t)(n > 0 ? n : 0));
    if (n > 0 && std::fread(&v[0], 1, (size_t)n, f) != (size_t)n) {
        std::fprintf(stderr, "ERROR: short read on %s\n", path.c_str());
        std::exit(1);
    }
    std::fclose(f);
    return v;
}

// PPM P6 only: that is what the test frames are, and guessing at other
// formats here would add code that is never exercised.
static bool readPPM(const std::string& path, Frame& fr) {
    std::vector<unsigned char> d = readFile(path);
    if (d.size() < 10 || d[0] != 'P' || d[1] != '6') return false;
    size_t p = 2;
    int v[3] = {0, 0, 0};
    for (int k = 0; k < 3;) {
        while (p < d.size() && std::isspace(d[p])) ++p;
        if (p < d.size() && d[p] == '#') {
            while (p < d.size() && d[p] != '\n') ++p;
            continue;
        }
        int val = 0;
        bool any = false;
        while (p < d.size() && std::isdigit(d[p])) { val = val * 10 + (d[p] - '0'); ++p; any = true; }
        if (!any) return false;
        v[k++] = val;
    }
    ++p;                                   // single whitespace after maxval
    fr.w = v[0]; fr.h = v[1];
    fr.comps = 3;
    fr.prec = (v[2] > 255) ? 16 : 8;
    const size_t px = (size_t)fr.w * fr.h;
    const int bytes = (fr.prec > 8) ? 2 : 1;
    if (d.size() - p < px * 3 * bytes) return false;

    fr.plane.assign(3, std::vector<OPJ_INT32>(px));
    const unsigned char* s = &d[p];
    for (size_t i = 0; i < px; ++i) {
        for (int c = 0; c < 3; ++c) {
            if (bytes == 1) fr.plane[c][i] = s[i * 3 + c];
            else fr.plane[c][i] = (s[(i * 3 + c) * 2] << 8) | s[(i * 3 + c) * 2 + 1];
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// command line: the same keys as nvj2k_bench-03
// ---------------------------------------------------------------------------

struct Args {
    std::string input, output;
    std::string algo = "irrev";   // irrev (9/7) | rev (5/3)
    int codeBlock = 32;
    int levels = 6;               // resolutions, same meaning as -n in opj
    double rate = 0.0;            // compression ratio; 0 = lossless
    int repeat = 1;
    int batch = 1;                // frames a worker takes at a time
    int threads = 1;              // worker threads (our scheme)
    int opjthreads = 1;           // OpenJPEG's own pool inside one frame
    bool decode = false;
    bool info = false;
    bool check = false;
    long targetSize = 0;
    double tol = 0.001;
    double rlo = 1.0, rhi = 200.0;
};

static bool eq(const char* a, const char* b) { return std::strcmp(a, b) == 0; }

static void usage(const char* me) {
    std::printf("usage: %s -i input [-o out] [-a irrev|rev] [-c 32] [-l 6]\n"
                "       [-r ratio | -targetsize bytes] [-repeat N] [-b N]\n"
                "       [-thread N] [-opjthreads K] [-decode] [-info]\n", me);
    std::printf("  -thread      worker threads, each doing whole frames\n");
    std::printf("  -opjthreads  OpenJPEG's own threads inside one frame\n");
    std::printf("  -q           same as -r: the harness feeds back the number\n"
                "               it read from the calibration line, and here\n"
                "               that number is a compression ratio\n");
    std::printf("  -targetsize  find the ratio that lands on this many bytes\n");
    std::printf("  -verify      encode once, decode back, compare with the "
                "source\n");
    std::printf("  -info        calibrate (and check) but measure nothing\n");
    std::printf("  -version     print the version and measure nothing\n");
}

static Args parseArgs(int argc, char** argv) {
    Args a;
    for (int i = 1; i < argc; ++i) {
        const char* k = argv[i];
        const char* v = (i + 1 < argc) ? argv[i + 1] : 0;
        if (eq(k, "-i") && v) { a.input = v; ++i; }
        else if (eq(k, "-o") && v) { a.output = v; ++i; }
        else if (eq(k, "-a") && v) { a.algo = v; ++i; }
        else if (eq(k, "-c") && v) { a.codeBlock = std::atoi(v); ++i; }
        else if (eq(k, "-l") && v) { a.levels = std::atoi(v); ++i; }
        else if (eq(k, "-r") && v) { a.rate = std::atof(v); ++i; }
        else if (eq(k, "-q") && v) { a.rate = std::atof(v); ++i; }
        else if (eq(k, "-repeat") && v) { a.repeat = std::atoi(v); ++i; }
        else if (eq(k, "-b") && v) { a.batch = std::atoi(v); ++i; }
        else if (eq(k, "-thread") && v) { a.threads = std::atoi(v); ++i; }
        else if (eq(k, "-opjthreads") && v) { a.opjthreads = std::atoi(v); ++i; }
        else if (eq(k, "-targetsize") && v) { a.targetSize = std::atol(v); ++i; }
        else if (eq(k, "-tol") && v) { a.tol = std::atof(v); ++i; }
        else if (eq(k, "-rlo") && v) { a.rlo = std::atof(v); ++i; }
        else if (eq(k, "-rhi") && v) { a.rhi = std::atof(v); ++i; }
        else if (eq(k, "-decode")) a.decode = true;
        else if (eq(k, "-info")) a.info = true;
        else if (eq(k, "-verify")) a.check = true;
        else if (eq(k, "-version")) {
            std::printf("opj_bench version 03, 14 September 2026\n");
            std::printf("Build: %s; this file compiled with AVX2: %s\n",
                        OPJ_BENCH_TAG_STR, compiledWithAvx2());
            std::exit(0);
        }
        // Keys that the GPU harness understands and that mean nothing here.
        // Accepted and ignored, so one command line can drive three codecs.
        else if (eq(k, "-d") || eq(k, "-sync") || eq(k, "-qlo") ||
                 eq(k, "-qhi") || eq(k, "-log") || eq(k, "-threadR") ||
                 eq(k, "-threadW") || eq(k, "-maxWidth") || eq(k, "-maxHeight")) {
            ++i;
        }
        else if (eq(k, "-async") || eq(k, "-discard") || eq(k, "-showFrames") ||
                 eq(k, "-noupload") || eq(k, "-nodownload")) {
            // host-side plumbing of the GPU harness; nothing to do here
        }
        // Anything that would change WHAT is encoded is refused rather than
        // ignored: a command line that looks the same while encoding something
        // else is how two runs stop being comparable.
        else if (eq(k, "-cr") || eq(k, "-s") || eq(k, "-outputBitdepth") ||
                 eq(k, "-noMCT") || eq(k, "-noHeader")) {
            std::fprintf(stderr, "ERROR: option %s changes the encoding and is "
                                 "not implemented here. Refusing to run.\n", k);
            std::exit(2);
        }
    }
    if (a.threads < 1) a.threads = 1;
    if (a.opjthreads < 1) a.opjthreads = 1;
    if (a.batch < 1) a.batch = 1;
    if (a.repeat < 1) a.repeat = 1;
    return a;
}

// ---------------------------------------------------------------------------
// encoder
// ---------------------------------------------------------------------------

struct EncSlot {
    opj_image_t* img;
    MemOut out;
    double copyMs;
    EncSlot() : img(0), copyMs(0) {}
};

static opj_image_t* makeImage(const Frame& fr) {
    opj_image_cmptparm_t parm[3];
    std::memset(parm, 0, sizeof(parm));
    for (int c = 0; c < fr.comps; ++c) {
        parm[c].dx = 1; parm[c].dy = 1;
        parm[c].w = (OPJ_UINT32)fr.w; parm[c].h = (OPJ_UINT32)fr.h;
        parm[c].x0 = 0; parm[c].y0 = 0;
        parm[c].prec = (OPJ_UINT32)fr.prec;
        parm[c].sgnd = 0;
    }
    opj_image_t* im = opj_image_create((OPJ_UINT32)fr.comps, parm,
                                       OPJ_CLRSPC_SRGB);
    if (!im) return 0;
    im->x0 = 0; im->y0 = 0;
    im->x1 = (OPJ_UINT32)fr.w; im->y1 = (OPJ_UINT32)fr.h;
    return im;
}

// The parameters of section 3.1, every one of them set explicitly. Defaults
// differ between codecs, and "we did not touch it" is not the same as "it is
// the same on both sides".
static void fillParams(opj_cparameters_t& p, const Args& a, double rate) {
    opj_set_default_encoder_parameters(&p);
    p.tcp_numlayers = 1;                       // one quality layer
    p.cp_disto_alloc = 1;
    p.tcp_rates[0] = (OPJ_FLOAT32)rate;        // 0 means lossless
    p.irreversible = (a.algo == "irrev") ? 1 : 0;   // 9/7 or 5/3
    p.numresolution = a.levels;                // resolutions, like -n
    p.cblockw_init = a.codeBlock;
    p.cblockh_init = a.codeBlock;
    p.prog_order = OPJ_LRCP;
    p.tcp_mct = 1;                             // colour transform on
    p.tile_size_on = OPJ_FALSE;                // no tiling
    p.csty = 0;                                // no SOP, no EPH
    p.res_spec = 0;                            // default precincts
}

// One frame, start to finish, the way an application must do it.
//
// The library TAKES the pixel buffers: after opj_encode the component data
// pointers are null, because OpenJPEG either freed them or moved them into its
// own tile. So every frame needs its own buffers, allocated the library's own
// way, and that allocation is part of the per-frame cost - it is not a trick
// of this harness, it is what any application built on OpenJPEG has to do.
// (Found the hard way: the second frame of the first run wrote into a null
// pointer.)
static size_t encodeOne(EncSlot& s, const Frame& fr, const Args& a,
                        double rate, bool timeCopy) {
    Clock::time_point tc = Clock::now();
    const OPJ_SIZE_T planeBytes =
        (OPJ_SIZE_T)fr.plane[0].size() * sizeof(OPJ_INT32);
    for (int c = 0; c < fr.comps; ++c) {
        if (!s.img->comps[c].data) {
            s.img->comps[c].data = (OPJ_INT32*)opj_image_data_alloc(planeBytes);
            if (!s.img->comps[c].data) {
                std::fprintf(stderr, "ERROR: out of memory for a frame buffer\n");
                std::exit(6);
            }
        }
        std::memcpy(s.img->comps[c].data, &fr.plane[c][0], planeBytes);
    }
    if (timeCopy) s.copyMs += msSince(tc);

    s.out.buf.clear();
    s.out.pos = 0;

    opj_cparameters_t p;
    fillParams(p, a, rate);

    opj_codec_t* codec = opj_create_compress(OPJ_CODEC_JP2);
    if (!codec) return 0;
    opj_set_error_handler(codec, on_error, 0);
    opj_set_warning_handler(codec, on_warn, 0);
    opj_set_info_handler(codec, on_info, 0);

    size_t got = 0;
    if (opj_setup_encoder(codec, &p, s.img)) {
        setPool(codec, a.opjthreads);
        opj_stream_t* st = out_stream(&s.out);
        if (st) {
            if (opj_start_compress(codec, s.img, st) &&
                opj_encode(codec, st) &&
                opj_end_compress(codec, st)) {
                got = s.out.buf.size();
            }
            opj_stream_destroy(st);
        }
    }
    opj_destroy_codec(codec);
    return got;
}

// Finding the ratio that lands on the requested byte count, by halving the
// interval. Same procedure as the quality-factor search for nvJPEG2000.
static double calibrate(const Frame& fr, const Args& a, long target) {
    EncSlot s;
    s.img = makeImage(fr);
    if (!s.img) return 0;
    double lo = a.rlo, hi = a.rhi, best = 0;
    long bestSize = 0;
    double bestMiss = 1e9;
    for (int step = 0; step < 40; ++step) {
        double mid = (lo + hi) / 2.0;
        size_t n = encodeOne(s, fr, a, mid, false);
        if (!n) break;
        double miss = ((double)n - target) / (double)target;
        if (std::fabs(miss) < std::fabs(bestMiss)) {
            bestMiss = miss; best = mid; bestSize = (long)n;
        }
        if (std::fabs(miss) <= a.tol) break;
        if ((long)n > target) lo = mid; else hi = mid;   // bigger ratio, smaller file
    }
    opj_image_destroy(s.img);
    // Printed in the shape the harness parses. The knob is a compression
    // ratio, not a quality factor - the next line says so, because a number
    // under a wrong name is worse than no number.
    std::printf("Calibration: q = %.4f; size = %ld bytes; target = %ld bytes; "
                "miss = %+.4f\n", best, bestSize, target, bestMiss * 100.0);
    std::printf("Calibration knob: OpenJPEG compression ratio, not a quality "
                "factor\n");
    return best;
}

// Encode one frame with the settings in force, decode it back and compare with
// the source. Cheap, and it answers the question that has to be answered before
// any speed number means anything: is this build encoding what we asked for?
// With -a rev the answer must be "bit for bit"; with -a irrev we print PSNR.
static void verify(const Frame& fr, const Args& a, double rate) {
    EncSlot s;
    s.img = makeImage(fr);
    if (!s.img) { std::fprintf(stderr, "ERROR: no image\n"); std::exit(3); }
    size_t n = encodeOne(s, fr, a, rate, false);
    opj_image_destroy(s.img);
    if (!n) { std::fprintf(stderr, "ERROR: the check encode failed\n"); std::exit(7); }

    MemIn in;
    in.data = &s.out.buf[0]; in.len = n; in.pos = 0;
    opj_stream_t* st = in_stream(&in);
    opj_dparameters_t dp;
    opj_set_default_decoder_parameters(&dp);
    opj_codec_t* codec = opj_create_decompress(OPJ_CODEC_JP2);
    opj_set_error_handler(codec, on_error, 0);
    opj_set_warning_handler(codec, on_warn, 0);
    opj_set_info_handler(codec, on_info, 0);
    opj_image_t* im = 0;
    bool ok = opj_setup_decoder(codec, &dp) &&
              opj_read_header(st, codec, &im) &&
              opj_decode(codec, st, im) &&
              opj_end_decompress(codec, st);
    opj_stream_destroy(st);
    opj_destroy_codec(codec);
    if (!ok || !im) {
        std::fprintf(stderr, "ERROR: the check decode failed\n");
        if (im) opj_image_destroy(im);
        std::exit(7);
    }

    long maxDiff = 0;
    double sse = 0;
    size_t count = 0;
    for (int c = 0; c < fr.comps; ++c) {
        const OPJ_INT32* d = im->comps[c].data;
        const size_t px = fr.plane[c].size();
        for (size_t i = 0; i < px; ++i) {
            long diff = (long)fr.plane[c][i] - (long)d[i];
            if (diff < 0) diff = -diff;
            if (diff > maxDiff) maxDiff = diff;
            sse += (double)diff * (double)diff;
            ++count;
        }
    }
    opj_image_destroy(im);

    const double peak = (double)((1 << fr.prec) - 1);
    std::printf("Check: %ld bytes; largest difference per sample = %ld\n",
                (long)n, maxDiff);
    if (maxDiff == 0) {
        std::printf("Check: the decoded frame matches the source bit for bit\n");
    } else {
        double mse = sse / (double)count;
        std::printf("Check: PSNR = %.2f dB\n",
                    10.0 * std::log10(peak * peak / mse));
        if (a.algo == "rev")
            std::fprintf(stderr, "WARNING: -a rev is supposed to be lossless, "
                                 "but the frame came back changed. Do not "
                                 "measure with this build until this is "
                                 "explained.\n");
    }
}

static void runEncode(const Frame& fr, const Args& a, double rate) {
    const int T = a.threads, B = a.batch;
    std::vector<EncSlot> slots((size_t)T);
    for (int t = 0; t < T; ++t) {
        slots[t].img = makeImage(fr);
        if (!slots[t].img) { std::fprintf(stderr, "ERROR: no image\n"); std::exit(3); }
    }

    // Warm-up: first touch of every buffer, and the library's own lazy
    // initialisation, must not land inside the measured region.
    //
    // It runs in the worker threads, not one after another on this one. Done
    // sequentially it costs T frames of single-threaded work - eight seconds
    // at thirty-two threads on 2K, twenty-three on 4K - and although that time
    // stays outside the timer, it is still time the machine spends, and it
    // wrecks the busy-cores figure of anyone measuring the whole process.
    {
        std::vector<std::thread> warm;
        for (int t = 0; t < T; ++t)
            warm.push_back(std::thread([&, t]() {
                encodeOne(slots[t], fr, a, rate, false);
            }));
        for (size_t i = 0; i < warm.size(); ++i) warm[i].join();
    }

    size_t oneSize = slots[0].out.buf.size();
    double ratio = oneSize ? (double)fr.w * fr.h * fr.comps *
                   ((fr.prec > 8) ? 2 : 1) / (double)oneSize : 0;
    std::printf("Compressed stream size = %d KB (%.2f:1)\n",
                (int)(oneSize / 1024), ratio);

    std::atomic<int> next(0);
    const int total = a.repeat;
    double cpu0 = cpuSeconds();
    Clock::time_point t0 = Clock::now();
    std::vector<std::thread> workers;
    for (int t = 0; t < T; ++t) {
        workers.push_back(std::thread([&, t]() {
            for (;;) {
                int start = next.fetch_add(B);
                if (start >= total) return;
                int n = total - start; if (n > B) n = B;
                for (int k = 0; k < n; ++k)
                    encodeOne(slots[t], fr, a, rate, true);
            }
        }));
    }
    for (size_t i = 0; i < workers.size(); ++i) workers[i].join();
    double wall = msSince(t0);
    double cpu1 = cpuSeconds();

    double copyMs = 0;
    for (int t = 0; t < T; ++t) {
        copyMs += slots[t].copyMs;
        opj_image_destroy(slots[t].img);
    }

    std::printf("Total J2K Encode time:\n");
    std::printf("- CPU pipeline from host memory to host memory for %d images "
                "per %d thread%s = %.1f ms; %.1f FPS;\n",
                total, T, (T == 1 ? "" : "s"), wall, total * 1000.0 / wall);
    // Handing the frame over is part of a frame, but knowing its share stops
    // it from becoming an argument later.
    std::printf("- of that, giving the frame to the library (fresh buffers "
                "plus the copy of the pixels): %.1f ms of thread time "
                "(%.1f %% of the wall clock x %d threads)\n",
                copyMs, 100.0 * copyMs / (wall * T), T);
    printCores(cpu0, cpu1, wall);
    std::printf("- OpenJPEG internal threads per frame: %d; total threads: %d\n",
                a.opjthreads, T * a.opjthreads);
}

// ---------------------------------------------------------------------------
// decoder
// ---------------------------------------------------------------------------

static bool decodeOne(const std::vector<unsigned char>& jp2, const Args& a,
                      int* w, int* h) {
    MemIn in;
    in.data = &jp2[0]; in.len = jp2.size(); in.pos = 0;
    opj_stream_t* st = in_stream(&in);
    if (!st) return false;

    opj_dparameters_t dp;
    opj_set_default_decoder_parameters(&dp);
    opj_codec_t* codec = opj_create_decompress(OPJ_CODEC_JP2);
    if (!codec) { opj_stream_destroy(st); return false; }
    opj_set_error_handler(codec, on_error, 0);
    opj_set_warning_handler(codec, on_warn, 0);
    opj_set_info_handler(codec, on_info, 0);

    bool ok = false;
    opj_image_t* im = 0;
    if (opj_setup_decoder(codec, &dp)) {
        setPool(codec, a.opjthreads);
        if (opj_read_header(st, codec, &im) &&
            opj_decode(codec, st, im) &&
            opj_end_decompress(codec, st)) {
            ok = true;
            if (w) *w = (int)(im->x1 - im->x0);
            if (h) *h = (int)(im->y1 - im->y0);
        }
    }
    if (im) opj_image_destroy(im);
    opj_destroy_codec(codec);
    opj_stream_destroy(st);
    return ok;
}

static void runDecode(const std::vector<unsigned char>& jp2, const Args& a) {
    const int T = a.threads, B = a.batch;
    int w = 0, h = 0;
    if (!decodeOne(jp2, a, &w, &h)) {
        std::fprintf(stderr, "ERROR: the first decode failed; not measuring\n");
        std::exit(4);
    }
    std::printf("Decoded frame: %dx%d from %d KB\n", w, h,
                (int)(jp2.size() / 1024));

    // The decoder needs no warm-up beyond the frame just decoded: it allocates
    // its own output image every time, so there are no reusable buffers to
    // touch first.
    std::atomic<int> next(0);
    const int total = a.repeat;
    double cpu0 = cpuSeconds();
    Clock::time_point t0 = Clock::now();
    std::vector<std::thread> workers;
    for (int t = 0; t < T; ++t) {
        workers.push_back(std::thread([&]() {
            for (;;) {
                int start = next.fetch_add(B);
                if (start >= total) return;
                int n = total - start; if (n > B) n = B;
                for (int k = 0; k < n; ++k) decodeOne(jp2, a, 0, 0);
            }
        }));
    }
    for (size_t i = 0; i < workers.size(); ++i) workers[i].join();
    double wall = msSince(t0);
    double cpu1 = cpuSeconds();

    std::printf("Total J2K Decode time:\n");
    std::printf("- CPU pipeline from host memory to host memory for %d images "
                "per %d thread%s = %.1f ms; %.1f FPS;\n",
                total, T, (T == 1 ? "" : "s"), wall, total * 1000.0 / wall);
    printCores(cpu0, cpu1, wall);
    std::printf("- OpenJPEG internal threads per frame: %d; total threads: %d\n",
                a.opjthreads, T * a.opjthreads);
}

// ---------------------------------------------------------------------------

int main(int argc, char** argv) {
    Args a = parseArgs(argc, argv);
    if (a.input.empty()) { usage(argv[0]); return 1; }

    std::printf("SDK version: OpenJPEG-%s\n", opj_version());
    std::printf("Build: %s; this file compiled with AVX2: %s\n",
                OPJ_BENCH_TAG_STR, compiledWithAvx2());
    std::printf("Processing unit: CPU (device id = 0)\n");
    std::printf("Wavelet: %s; code block %dx%d; resolutions %d; "
                "layers 1; LRCP; MCT on; no tiling; no SOP/EPH\n\n",
                (a.algo == "irrev") ? "irreversible 9/7" : "reversible 5/3",
                a.codeBlock, a.codeBlock, a.levels);

    if (a.decode) {
        std::vector<unsigned char> jp2 = readFile(a.input);
        runDecode(jp2, a);
    } else {
        Frame fr;
        if (!readPPM(a.input, fr)) {
            std::fprintf(stderr, "ERROR: %s is not a P6 PPM this harness can "
                                 "read\n", a.input.c_str());
            return 1;
        }
        std::printf("Source frame: %dx%d, %d components, %d bits\n\n",
                    fr.w, fr.h, fr.comps, fr.prec);

        double rate = a.rate;
        if (a.algo == "rev") rate = 0.0;          // lossless has no rate
        else if (a.targetSize > 0) rate = calibrate(fr, a, a.targetSize);

        if (!a.output.empty()) {
            EncSlot s; s.img = makeImage(fr);
            size_t n = encodeOne(s, fr, a, rate, false);
            FILE* f = std::fopen(a.output.c_str(), "wb");
            if (f) { std::fwrite(&s.out.buf[0], 1, n, f); std::fclose(f); }
            opj_image_destroy(s.img);
            std::printf("Wrote %s, %d bytes\n", a.output.c_str(), (int)n);
        }
        if (a.check) verify(fr, a, rate);
        if (!a.info) runEncode(fr, a, rate);
    }

    {
        double mb = peakWorkingSetMB();
        if (mb >= 0) std::printf("- peak working set: %.0f MB\n", mb);
    }

    if (g_poolRefused.load())
        std::fprintf(stderr, "\nWARNING: opj_codec_set_threads(%d) was refused "
                             "%d times; those frames ran on one thread inside "
                             "the library. Do not read the numbers above as a "
                             "%d-thread result.\n",
                     a.opjthreads, g_poolRefused.load(), a.opjthreads);
    if (g_errors.load())
        std::fprintf(stderr, "\nWARNING: the library reported %d errors; the "
                             "numbers above are not trustworthy\n",
                     g_errors.load());
    return g_errors.load() ? 5 : 0;
}
