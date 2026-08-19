// ---------------------------------------------------------------------------
// nvJPEG2000 benchmark harness
//
// Mirrors the command line and the printed output of the Fastvideo J2K sample
// applications, so that one and the same run_bench.bat and parse_bench.py can
// drive both codecs and put the results into one table.
//
// Build two executables from this one source:
//   nvj2kEncoderSample.exe   (default)
//   nvj2kDecoderSample.exe   (compile with /DBUILD_DECODER)
//
// Measurement boundaries, identical to the Fastvideo samples:
//   encoder: pixels already in GPU memory  ->  compressed stream in host memory
//   decoder: compressed stream in host memory -> pixels in GPU memory
// The transfer of the pixel side is performed but excluded from the reported
// figure in synchronous mode, and included in asynchronous mode - exactly as
// the Fastvideo samples label it.
// ---------------------------------------------------------------------------

#include <nvjpeg2k.h>
#include <cuda_runtime_api.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

// ---------------------------------------------------------------------------
// error handling
// ---------------------------------------------------------------------------

static void die(const char* what, int code, const char* file, int line) {
    std::fprintf(stderr, "ERROR: %s failed with code %d at %s:%d\n",
                 what, code, file, line);
    std::exit(1);
}

#define CHECK_CUDA(call)                                                       \
    do {                                                                       \
        cudaError_t e_ = (call);                                               \
        if (e_ != cudaSuccess) die(#call, (int)e_, __FILE__, __LINE__);        \
    } while (0)

#define CHECK_NVJ(call)                                                        \
    do {                                                                       \
        nvjpeg2kStatus_t s_ = (call);                                          \
        if (s_ != NVJPEG2K_STATUS_SUCCESS)                                     \
            die(#call, (int)s_, __FILE__, __LINE__);                           \
    } while (0)

static std::atomic<size_t> g_device_bytes(0);

static void* devAlloc(size_t bytes) {
    void* p = nullptr;
    CHECK_CUDA(cudaMalloc(&p, bytes));
    g_device_bytes += bytes;
    return p;
}

// ---------------------------------------------------------------------------
// clock
// ---------------------------------------------------------------------------

typedef std::chrono::high_resolution_clock Clock;

static double msSince(const Clock::time_point& t0) {
    return std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
}

// ---------------------------------------------------------------------------
// PPM / PGM reader, planar output
// ---------------------------------------------------------------------------

struct Image {
    int width = 0;
    int height = 0;
    int comps = 0;
    int precision = 8;              // bits per sample
    int bytesPerSample = 1;
    std::vector<std::vector<unsigned char> > plane;   // one per component
};

static void skipWhitespaceAndComments(FILE* f) {
    int c;
    for (;;) {
        c = std::fgetc(f);
        if (c == '#') {
            while (c != '\n' && c != EOF) c = std::fgetc(f);
        } else if (!std::isspace(c)) {
            std::ungetc(c, f);
            return;
        } else if (c == EOF) {
            return;
        }
    }
}

static int readInt(FILE* f) {
    skipWhitespaceAndComments(f);
    int v = 0;
    if (std::fscanf(f, "%d", &v) != 1) {
        std::fprintf(stderr, "ERROR: malformed PPM/PGM header\n");
        std::exit(1);
    }
    return v;
}

static Image readImage(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) {
        std::fprintf(stderr, "ERROR: cannot open %s\n", path.c_str());
        std::exit(1);
    }
    char magic[3] = {0, 0, 0};
    if (std::fread(magic, 1, 2, f) != 2 || magic[0] != 'P' ||
        (magic[1] != '5' && magic[1] != '6')) {
        std::fprintf(stderr, "ERROR: %s is not a binary PGM (P5) or PPM (P6)\n",
                     path.c_str());
        std::exit(1);
    }
    Image im;
    im.comps = (magic[1] == '6') ? 3 : 1;
    im.width = readInt(f);
    im.height = readInt(f);
    int maxval = readInt(f);
    std::fgetc(f);                     // single whitespace after maxval

    im.bytesPerSample = (maxval > 255) ? 2 : 1;
    im.precision = (maxval > 255) ? 16 : 8;

    const size_t pixels = (size_t)im.width * im.height;
    const size_t interleavedBytes = pixels * im.comps * im.bytesPerSample;
    std::vector<unsigned char> raw(interleavedBytes);
    if (std::fread(&raw[0], 1, interleavedBytes, f) != interleavedBytes) {
        std::fprintf(stderr, "ERROR: %s is shorter than its header claims\n",
                     path.c_str());
        std::exit(1);
    }
    std::fclose(f);

    im.plane.resize(im.comps);
    for (int c = 0; c < im.comps; ++c)
        im.plane[c].resize(pixels * im.bytesPerSample);

    if (im.bytesPerSample == 1) {
        for (size_t i = 0; i < pixels; ++i)
            for (int c = 0; c < im.comps; ++c)
                im.plane[c][i] = raw[i * im.comps + c];
    } else {
        // PPM/PGM store 16-bit samples big-endian
        for (size_t i = 0; i < pixels; ++i) {
            for (int c = 0; c < im.comps; ++c) {
                unsigned char hi = raw[(i * im.comps + c) * 2 + 0];
                unsigned char lo = raw[(i * im.comps + c) * 2 + 1];
                im.plane[c][i * 2 + 0] = lo;
                im.plane[c][i * 2 + 1] = hi;
            }
        }
    }
    return im;
}

static std::vector<unsigned char> readFile(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) {
        std::fprintf(stderr, "ERROR: cannot open %s\n", path.c_str());
        std::exit(1);
    }
    std::fseek(f, 0, SEEK_END);
    long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    std::vector<unsigned char> buf((size_t)n);
    if (n > 0 && std::fread(&buf[0], 1, (size_t)n, f) != (size_t)n) {
        std::fprintf(stderr, "ERROR: short read on %s\n", path.c_str());
        std::exit(1);
    }
    std::fclose(f);
    return buf;
}

// ---------------------------------------------------------------------------
// command line, same keys as the Fastvideo samples
// ---------------------------------------------------------------------------

struct Args {
    std::string input;
    std::string output;
    std::string algo = "irrev";     // irrev | rev
    int codeBlock = 32;
    int levels = 6;                 // number of resolutions
    double quality = 85.0;          // Q factor
    int repeat = 1;
    int batch = 1;
    int threads = 1;
    bool async = false;
    bool discard = false;
    bool info = false;
    bool showFrames = false;
    int device = 0;
    long targetSize = 0;            // bytes; non-zero switches on calibration
    double tol = 0.003;             // calibration: allowed miss, share of target
    double qlo = 1.0;               // calibration: lower end of the search
    double qhi = 100.0;             // calibration: upper end of the search
    bool noupload = false;          // diagnostic: no per-frame host->device copy
    bool decode = false;
};

static bool eq(const char* a, const char* b) { return std::strcmp(a, b) == 0; }

static Args parseArgs(int argc, char** argv) {
    Args a;
#ifdef BUILD_DECODER
    a.decode = true;
#endif
    for (int i = 1; i < argc; ++i) {
        const char* k = argv[i];
        const char* v = (i + 1 < argc) ? argv[i + 1] : nullptr;
        if (eq(k, "-i") && v) { a.input = v; ++i; }
        else if (eq(k, "-o") && v) { a.output = v; ++i; }
        else if (eq(k, "-a") && v) { a.algo = v; ++i; }
        else if (eq(k, "-c") && v) { a.codeBlock = std::atoi(v); ++i; }
        else if (eq(k, "-l") && v) { a.levels = std::atoi(v); ++i; }
        else if (eq(k, "-q") && v) { a.quality = std::atof(v); ++i; }
        else if (eq(k, "-repeat") && v) { a.repeat = std::atoi(v); ++i; }
        else if (eq(k, "-b") && v) { a.batch = std::atoi(v); ++i; }
        else if (eq(k, "-thread") && v) { a.threads = std::atoi(v); ++i; }
        else if (eq(k, "-d") && v) { a.device = std::atoi(v); ++i; }
        else if (eq(k, "-targetsize") && v) { a.targetSize = std::atol(v); ++i; }
        else if (eq(k, "-tol") && v) { a.tol = std::atof(v); ++i; }
        else if (eq(k, "-qlo") && v) { a.qlo = std::atof(v); ++i; }
        else if (eq(k, "-qhi") && v) { a.qhi = std::atof(v); ++i; }
        else if (eq(k, "-async")) a.async = true;
        else if (eq(k, "-discard")) a.discard = true;
        else if (eq(k, "-info")) a.info = true;
        else if (eq(k, "-showFrames")) a.showFrames = true;
        else if (eq(k, "-decode")) a.decode = true;
        else if (eq(k, "-noupload")) a.noupload = true;
        else if (eq(k, "-threadR") || eq(k, "-threadW") ||
                 eq(k, "-s") || eq(k, "-cr") || eq(k, "-maxWidth") ||
                 eq(k, "-maxHeight") || eq(k, "-outputBitdepth") ||
                 eq(k, "-overwriteSourceBitdepth") || eq(k, "-log") ||
                 eq(k, "-repeatTime")) {
            ++i;                       // accepted and ignored, for compatibility
        }
        else if (eq(k, "-noMCT") || eq(k, "-noHeader")) {
            // accepted and ignored
        }
    }
    if (a.threads < 1) a.threads = 1;
    if (a.batch < 1) a.batch = 1;
    if (a.repeat < 1) a.repeat = 1;
    return a;
}

// ---------------------------------------------------------------------------
// header, printed in the same shape as the Fastvideo samples
// ---------------------------------------------------------------------------

static void printHeader(const Args& a) {
    std::printf("SDK version: nvJPEG2000-%d.%d.%d.%d\n",
                NVJPEG2K_VER_MAJOR, NVJPEG2K_VER_MINOR,
                NVJPEG2K_VER_PATCH, NVJPEG2K_VER_BUILD);

    cudaDeviceProp prop;
    CHECK_CUDA(cudaGetDeviceProperties(&prop, a.device));
    std::printf("Processing unit: %s (device id = %d)\n", prop.name, a.device);

    size_t freeB = 0, totalB = 0;
    CHECK_CUDA(cudaMemGetInfo(&freeB, &totalB));
    std::printf("Available GPU memory size: %.2f GB\n",
                (double)freeB / (1024.0 * 1024.0 * 1024.0));

    // host to device bandwidth, pinned, best of five
    const size_t testBytes = 64u * 1024u * 1024u;
    void* hostPinned = nullptr;
    void* devBuf = nullptr;
    CHECK_CUDA(cudaHostAlloc(&hostPinned, testBytes, cudaHostAllocDefault));
    CHECK_CUDA(cudaMalloc(&devBuf, testBytes));
    double best = 0.0;
    for (int i = 0; i < 5; ++i) {
        Clock::time_point t0 = Clock::now();
        CHECK_CUDA(cudaMemcpy(devBuf, hostPinned, testBytes,
                              cudaMemcpyHostToDevice));
        CHECK_CUDA(cudaDeviceSynchronize());
        double ms = msSince(t0);
        double mbs = (double)testBytes / (1024.0 * 1024.0) / (ms / 1000.0);
        if (mbs > best) best = mbs;
    }
    CHECK_CUDA(cudaFree(devBuf));
    CHECK_CUDA(cudaFreeHost(hostPinned));
    std::printf("PCI-Express bandwidth test (host to device): %.0f MByte/s\n\n",
                best);
}

static void printMemory() {
    std::printf("Requested GPU memory size: %.2f GB\n",
                (double)g_device_bytes.load() / (1024.0 * 1024.0 * 1024.0));
}

// ---------------------------------------------------------------------------
// encoder
// ---------------------------------------------------------------------------

struct EncSlot {
    cudaStream_t stream = nullptr;
    nvjpeg2kEncodeState_t state = nullptr;
    std::vector<void*> dplane;
    std::vector<size_t> pitch;
    nvjpeg2kImage_t img;
    unsigned char* bits = nullptr;      // pinned host buffer
    size_t bitsCapacity = 0;
    size_t bitstreamLen = 0;
};

struct EncContext {
    nvjpeg2kEncoder_t handle = nullptr;
    nvjpeg2kEncodeParams_t params = nullptr;
    std::vector<nvjpeg2kImageComponentInfo_t> compInfo;
    nvjpeg2kEncodeConfig_t cfg;
};

static void encoderConfigure(EncContext& ctx, const Image& im, const Args& a) {
    CHECK_NVJ(nvjpeg2kEncoderCreateSimple(&ctx.handle));
    CHECK_NVJ(nvjpeg2kEncodeParamsCreate(&ctx.params));

    ctx.compInfo.resize(im.comps);
    for (int c = 0; c < im.comps; ++c) {
        ctx.compInfo[c].component_width = (uint32_t)im.width;
        ctx.compInfo[c].component_height = (uint32_t)im.height;
        ctx.compInfo[c].precision = (uint8_t)im.precision;
        ctx.compInfo[c].sgn = 0;
    }

    std::memset(&ctx.cfg, 0, sizeof(ctx.cfg));
    ctx.cfg.stream_type = NVJPEG2K_STREAM_JP2;
    ctx.cfg.color_space = (im.comps == 1) ? NVJPEG2K_COLORSPACE_GRAY
                                          : NVJPEG2K_COLORSPACE_SRGB;
    ctx.cfg.rsiz = 0;                       // plain JPEG2000, not HTJ2K
    ctx.cfg.image_width = (uint32_t)im.width;
    ctx.cfg.image_height = (uint32_t)im.height;
    ctx.cfg.enable_tiling = 0;
    ctx.cfg.tile_width = 0;
    ctx.cfg.tile_height = 0;
    ctx.cfg.num_components = (uint32_t)im.comps;
    ctx.cfg.image_comp_info = &ctx.compInfo[0];
    ctx.cfg.enable_SOP_marker = 0;
    ctx.cfg.enable_EPH_marker = 0;
    ctx.cfg.prog_order = NVJPEG2K_LRCP;
    ctx.cfg.num_layers = 1;
    ctx.cfg.mct_mode = (im.comps == 3) ? 1 : 0;
    ctx.cfg.num_resolutions = (uint32_t)a.levels;
    ctx.cfg.code_block_w = (uint32_t)a.codeBlock;
    ctx.cfg.code_block_h = (uint32_t)a.codeBlock;
    ctx.cfg.encode_modes = 0;
    ctx.cfg.irreversible = (a.algo == "irrev") ? 1 : 0;
    ctx.cfg.num_precincts_init = 0;

    CHECK_NVJ(nvjpeg2kEncodeParamsSetEncodeConfig(ctx.params, &ctx.cfg));
    if (ctx.cfg.irreversible) {
        CHECK_NVJ(nvjpeg2kEncodeParamsSpecifyQuality(
            ctx.params, NVJPEG2K_QUALITY_TYPE_Q_FACTOR, a.quality));
    }
    CHECK_NVJ(nvjpeg2kEncodeParamsSetInputFormat(ctx.params,
                                                 NVJPEG2K_FORMAT_PLANAR));
}

static void encoderSlotInit(EncSlot& s, const Image& im, size_t capacity) {
    CHECK_CUDA(cudaStreamCreateWithFlags(&s.stream, cudaStreamNonBlocking));
    s.dplane.resize(im.comps);
    s.pitch.resize(im.comps);
    const size_t planeBytes =
        (size_t)im.width * im.height * im.bytesPerSample;
    for (int c = 0; c < im.comps; ++c) {
        s.dplane[c] = devAlloc(planeBytes);
        s.pitch[c] = (size_t)im.width * im.bytesPerSample;
    }
    std::memset(&s.img, 0, sizeof(s.img));
    s.img.pixel_data = &s.dplane[0];
    s.img.pitch_in_bytes = &s.pitch[0];
    s.img.pixel_type = (im.bytesPerSample == 1) ? NVJPEG2K_UINT8
                                                : NVJPEG2K_UINT16;
    s.img.num_components = (uint32_t)im.comps;
    // The compressed stream is written into pinned host memory: a copy into
    // pageable memory is staged by the driver and serialises the threads.
    CHECK_CUDA(cudaHostAlloc((void**)&s.bits, capacity, cudaHostAllocDefault));
    s.bitsCapacity = capacity;
}

// Pinned copy of the source planes. Uploading from pageable host memory is
// staged by the driver and serialises concurrent threads, which would show up
// as "the encoder does not scale" - an artefact of the harness, not of the
// library. Prepared once, before any measurement.
struct PinnedSource {
    std::vector<void*> plane;
    size_t planeBytes = 0;
    int comps = 0;
};

static PinnedSource pinSource(const Image& im) {
    PinnedSource p;
    p.comps = im.comps;
    p.planeBytes = (size_t)im.width * im.height * im.bytesPerSample;
    p.plane.resize((size_t)im.comps);
    for (int c = 0; c < im.comps; ++c) {
        CHECK_CUDA(cudaHostAlloc(&p.plane[c], p.planeBytes,
                                 cudaHostAllocDefault));
        std::memcpy(p.plane[c], &im.plane[c][0], p.planeBytes);
    }
    return p;
}

// upload one frame into the slot; returns without synchronising
static void encoderUpload(EncSlot& s, const PinnedSource& src) {
    for (int c = 0; c < src.comps; ++c)
        CHECK_CUDA(cudaMemcpyAsync(s.dplane[c], src.plane[c], src.planeBytes,
                                   cudaMemcpyHostToDevice, s.stream));
}

static void encoderOne(EncContext& ctx, EncSlot& s) {
    CHECK_NVJ(nvjpeg2kEncode(ctx.handle, s.state, ctx.params, &s.img,
                             s.stream));
}

static void encoderRetrieve(EncContext& ctx, EncSlot& s) {
    size_t len = s.bitsCapacity;
    CHECK_NVJ(nvjpeg2kEncodeRetrieveBitstream(ctx.handle, s.state,
                                              s.bits, &len,
                                              s.stream));
    CHECK_CUDA(cudaStreamSynchronize(s.stream));
    s.bitstreamLen = len;
}

// ---------------------------------------------------------------------------
// decoder
// ---------------------------------------------------------------------------

struct DecSlot {
    cudaStream_t stream = nullptr;
    nvjpeg2kDecodeState_t state = nullptr;
    nvjpeg2kStream_t jstream = nullptr;
    std::vector<void*> dplane;
    std::vector<size_t> pitch;
    nvjpeg2kImage_t img;
};

struct DecContext {
    nvjpeg2kHandle_t handle = nullptr;
};

// ---------------------------------------------------------------------------
// calibration: find the Q factor that hits a target compressed size
// ---------------------------------------------------------------------------

static void runCalibration(const Args& a, const Image& im) {
    EncContext ctx;
    Args tmp = a;
    double lo = a.qlo, hi = a.qhi, q = a.quality;
    size_t best = 0;
    // the loop can walk away from its own best guess on the last step, so the
    // closest hit is remembered separately and reported
    double bestQ = a.quality, bestRel = 1e9;
    size_t bestSize = 0;
    const size_t capacity =
        (size_t)im.width * im.height * im.comps * im.bytesPerSample + (1u << 20);

    for (int iter = 0; iter < 18; ++iter) {
        q = 0.5 * (lo + hi);
        tmp.quality = q;

        EncContext c2;
        encoderConfigure(c2, im, tmp);
        EncSlot s;
        encoderSlotInit(s, im, capacity);
        CHECK_NVJ(nvjpeg2kEncodeStateCreate(c2.handle, &s.state));
        PinnedSource src = pinSource(im);
        encoderUpload(s, src);
        CHECK_CUDA(cudaStreamSynchronize(s.stream));
        encoderOne(c2, s);
        encoderRetrieve(c2, s);
        best = s.bitstreamLen;

        for (size_t c = 0; c < src.plane.size(); ++c) cudaFreeHost(src.plane[c]);
        cudaFreeHost(s.bits);
        nvjpeg2kEncodeStateDestroy(s.state);
        for (size_t c = 0; c < s.dplane.size(); ++c) cudaFree(s.dplane[c]);
        cudaStreamDestroy(s.stream);
        nvjpeg2kEncodeParamsDestroy(c2.params);
        nvjpeg2kEncoderDestroy(c2.handle);

        if ((long)best > a.targetSize) hi = q; else lo = q;
        if (a.targetSize > 0) {
            double rel = (double)((long)best - a.targetSize) / a.targetSize;
            double mag = rel < 0 ? -rel : rel;
            if (mag < bestRel) { bestRel = mag; bestQ = q; bestSize = best; }
            if (mag < a.tol) break;
        }
    }
    if (bestSize) { q = bestQ; best = bestSize; }
    const double uncompressed =
        (double)im.width * im.height * im.comps * im.bytesPerSample;
    std::printf("(excluded) 8) Buffer write disabled; size = %d KB (%.1f:1)\n",
                (int)(best / 1024), uncompressed / (double)best);
    std::printf("Calibration: q = %.4f; size = %d bytes; target = %ld bytes; "
                "miss = %.3f %%; ratio = %.2f:1; search = [%.2f, %.2f]; "
                "tol = %.3f %%\n",
                q, (int)best, a.targetSize, 100.0 * bestRel,
                uncompressed / (double)best, a.qlo, a.qhi, 100.0 * a.tol);
    (void)ctx;
}

// ---------------------------------------------------------------------------
// encoder benchmark
// ---------------------------------------------------------------------------

static void benchEncode(const Args& a, const Image& im) {
    const double uncompressedMB =
        (double)im.width * im.height * im.comps * im.bytesPerSample /
        (1024.0 * 1024.0);
    const size_t capacity =
        (size_t)im.width * im.height * im.comps * im.bytesPerSample + (1u << 20);

    std::printf("Input image: %s (%dx%d pixels; %dx%d-bit channel(s)) - %.1f MB\n",
                a.input.c_str(), im.width, im.height, im.comps, im.precision,
                uncompressedMB);
    std::printf("Tile size: %dx%d\n", im.width, im.height);

    PinnedSource src = pinSource(im);

    if (!a.async) {
        // ------------------------- synchronous -----------------------------
        EncContext ctx;
        encoderConfigure(ctx, im, a);
        EncSlot s;
        encoderSlotInit(s, im, capacity);
        CHECK_NVJ(nvjpeg2kEncodeStateCreate(ctx.handle, &s.state));
        printMemory();

        // warm-up
        encoderUpload(s, src);
        CHECK_CUDA(cudaStreamSynchronize(s.stream));
        encoderOne(ctx, s);
        encoderRetrieve(ctx, s);

        double codecMs = 0.0, totalMs = 0.0;
        for (int i = 0; i < a.repeat; ++i) {
            Clock::time_point t0 = Clock::now();
            if (!a.noupload) {
                encoderUpload(s, src);
                CHECK_CUDA(cudaStreamSynchronize(s.stream));
            }
            Clock::time_point t1 = Clock::now();
            encoderOne(ctx, s);
            encoderRetrieve(ctx, s);
            double frame = msSince(t1);
            codecMs += frame;
            totalMs += msSince(t0);
            if (a.showFrames)
                std::printf("  %6.2f ms Total time\n", frame);
        }

        const double ratio =
            (double)im.width * im.height * im.comps * im.bytesPerSample /
            (double)s.bitstreamLen;
        std::printf("(excluded) 8) Buffer write disabled; size = %d KB (%.1f:1)\n",
                    (int)(s.bitstreamLen / 1024), ratio);

        const double mbs = uncompressedMB * a.repeat / (codecMs / 1000.0);
        std::printf("Total encode time excluding host-to-device transfer "
                    "for %d images = %.1f ms; %.0f MB/s; %.1f FPS;\n",
                    a.repeat, codecMs, mbs, a.repeat * 1000.0 / codecMs);
        if (a.info) {
            std::printf("Total encode time for %d images = %.1f ms; %.0f MB/s; "
                        "%.1f FPS;\n",
                        a.repeat, totalMs,
                        uncompressedMB * a.repeat / (totalMs / 1000.0),
                        a.repeat * 1000.0 / totalMs);
        }
        if (!a.discard && !a.output.empty()) {
            FILE* f = std::fopen(a.output.c_str(), "wb");
            if (f) {
                std::fwrite(s.bits, 1, s.bitstreamLen, f);
                std::fclose(f);
            }
        }
        return;
    }

    // ------------------------- asynchronous --------------------------------
    const int T = a.threads;
    const int B = a.batch;
    std::vector<EncContext> ctxs((size_t)T);
    std::vector<std::vector<EncSlot> > slots((size_t)T);

    for (int t = 0; t < T; ++t) {
        encoderConfigure(ctxs[t], im, a);
        slots[t].resize((size_t)B);
        for (int b = 0; b < B; ++b) {
            encoderSlotInit(slots[t][b], im, capacity);
            CHECK_NVJ(nvjpeg2kEncodeStateCreate(ctxs[t].handle,
                                                &slots[t][b].state));
        }
    }
    printMemory();

    if (a.noupload) {
        for (int t = 0; t < T; ++t)
            for (int b = 0; b < B; ++b) {
                encoderUpload(slots[t][b], src);
                CHECK_CUDA(cudaStreamSynchronize(slots[t][b].stream));
            }
    }

    // warm-up on the first slot of every thread
    for (int t = 0; t < T; ++t) {
        encoderUpload(slots[t][0], src);
        CHECK_CUDA(cudaStreamSynchronize(slots[t][0].stream));
        encoderOne(ctxs[t], slots[t][0]);
        encoderRetrieve(ctxs[t], slots[t][0]);
    }

    std::atomic<int> next(0);
    const int total = a.repeat;

    Clock::time_point t0 = Clock::now();
    std::vector<std::thread> workers;
    for (int t = 0; t < T; ++t) {
        workers.push_back(std::thread([&, t]() {
            for (;;) {
                int start = next.fetch_add(B);
                if (start >= total) return;
                int n = total - start;
                if (n > B) n = B;
                if (!a.noupload)
                    for (int b = 0; b < n; ++b)
                        encoderUpload(slots[t][b], src);
                for (int b = 0; b < n; ++b)
                    encoderOne(ctxs[t], slots[t][b]);
                for (int b = 0; b < n; ++b)
                    encoderRetrieve(ctxs[t], slots[t][b]);
            }
        }));
    }
    for (size_t i = 0; i < workers.size(); ++i) workers[i].join();
    double wall = msSince(t0);

    std::printf("Total J2K Encode time:\n");
    std::printf("- GPU pipeline including all transfers for %d images "
                "per %d thread%s = %.1f ms; %.1f FPS;\n",
                total, T, (T == 1 ? "" : "s"), wall, total * 1000.0 / wall);
    std::printf("- GPU and CPU pipelines including image reader and writer "
                "threads: %.1f ms\n", wall);
}

// ---------------------------------------------------------------------------
// decoder benchmark
// ---------------------------------------------------------------------------

static void decoderSlotInit(DecSlot& s, nvjpeg2kHandle_t handle,
                            int width, int height, int comps,
                            int bytesPerSample) {
    CHECK_CUDA(cudaStreamCreateWithFlags(&s.stream, cudaStreamNonBlocking));
    CHECK_NVJ(nvjpeg2kDecodeStateCreate(handle, &s.state));
    CHECK_NVJ(nvjpeg2kStreamCreate(&s.jstream));
    s.dplane.resize((size_t)comps);
    s.pitch.resize((size_t)comps);
    const size_t planeBytes = (size_t)width * height * bytesPerSample;
    for (int c = 0; c < comps; ++c) {
        s.dplane[c] = devAlloc(planeBytes);
        s.pitch[c] = (size_t)width * bytesPerSample;
    }
    std::memset(&s.img, 0, sizeof(s.img));
    s.img.pixel_data = &s.dplane[0];
    s.img.pitch_in_bytes = &s.pitch[0];
    s.img.pixel_type = (bytesPerSample == 1) ? NVJPEG2K_UINT8 : NVJPEG2K_UINT16;
    s.img.num_components = (uint32_t)comps;
}

static void benchDecode(const Args& a) {
    std::vector<unsigned char> bitstream = readFile(a.input);

    nvjpeg2kHandle_t probe = nullptr;
    CHECK_NVJ(nvjpeg2kCreateSimple(&probe));
    nvjpeg2kStream_t probeStream = nullptr;
    CHECK_NVJ(nvjpeg2kStreamCreate(&probeStream));
    CHECK_NVJ(nvjpeg2kStreamParse(probe, &bitstream[0], bitstream.size(),
                                  0, 0, probeStream));
    nvjpeg2kImageInfo_t info;
    CHECK_NVJ(nvjpeg2kStreamGetImageInfo(probeStream, &info));
    nvjpeg2kImageComponentInfo_t ci;
    CHECK_NVJ(nvjpeg2kStreamGetImageComponentInfo(probeStream, &ci, 0));
    const int comps = (int)info.num_components;
    const int width = (int)info.image_width;
    const int height = (int)info.image_height;
    const int bytesPerSample = (ci.precision > 8) ? 2 : 1;
    nvjpeg2kStreamDestroy(probeStream);
    nvjpeg2kDestroy(probe);

    const double uncompressedMB =
        (double)width * height * comps * bytesPerSample / (1024.0 * 1024.0);

    std::printf("Input image : %s (%dx%d pixels; %d %d-bit channel(s))\n",
                a.input.c_str(), width, height, comps, (int)ci.precision);
    std::printf("Tile count: %u (%ux%u)\n",
                info.num_tiles_x * info.num_tiles_y,
                info.num_tiles_x, info.num_tiles_y);

    if (!a.async) {
        DecContext ctx;
        CHECK_NVJ(nvjpeg2kCreateSimple(&ctx.handle));
        DecSlot s;
        decoderSlotInit(s, ctx.handle, width, height, comps, bytesPerSample);
        printMemory();

        // warm-up
        CHECK_NVJ(nvjpeg2kStreamParse(ctx.handle, &bitstream[0],
                                      bitstream.size(), 0, 0, s.jstream));
        CHECK_NVJ(nvjpeg2kDecodeImage(ctx.handle, s.state, s.jstream, nullptr,
                                      &s.img, s.stream));
        CHECK_CUDA(cudaStreamSynchronize(s.stream));

        double ms = 0.0;
        for (int i = 0; i < a.repeat; ++i) {
            Clock::time_point t1 = Clock::now();
            CHECK_NVJ(nvjpeg2kStreamParse(ctx.handle, &bitstream[0],
                                          bitstream.size(), 0, 0, s.jstream));
            CHECK_NVJ(nvjpeg2kDecodeImage(ctx.handle, s.state, s.jstream,
                                          nullptr, &s.img, s.stream));
            CHECK_CUDA(cudaStreamSynchronize(s.stream));
            double frame = msSince(t1);
            ms += frame;
            if (a.showFrames)
                std::printf("  %6.2f ms Total time\n", frame);
        }
        std::printf("Total decode time excluding device-to-host transfer "
                    "for %d images = %.1f ms; %.1f FPS;\n",
                    a.repeat, ms, a.repeat * 1000.0 / ms);

        // Writing the result is outside the measured region, exactly as the
        // Fastvideo sample treats its own output.
        if (!a.discard && !a.output.empty()) {
            const size_t planeBytes =
                (size_t)width * height * bytesPerSample;
            std::vector<std::vector<unsigned char> > host(comps);
            for (int c = 0; c < comps; ++c) {
                host[c].resize(planeBytes);
                CHECK_CUDA(cudaMemcpy(&host[c][0], s.dplane[c], planeBytes,
                                      cudaMemcpyDeviceToHost));
            }
            FILE* f = std::fopen(a.output.c_str(), "wb");
            if (f) {
                std::fprintf(f, "P%d\n%d %d\n%d\n", comps == 1 ? 5 : 6,
                             width, height,
                             bytesPerSample == 1 ? 255 : 65535);
                std::vector<unsigned char> row((size_t)width * comps *
                                               bytesPerSample);
                for (int y = 0; y < height; ++y) {
                    for (int x = 0; x < width; ++x) {
                        for (int c = 0; c < comps; ++c) {
                            const size_t si =
                                ((size_t)y * width + x) * bytesPerSample;
                            const size_t di =
                                ((size_t)x * comps + c) * bytesPerSample;
                            if (bytesPerSample == 1) {
                                row[di] = host[c][si];
                            } else {
                                row[di + 0] = host[c][si + 1];
                                row[di + 1] = host[c][si + 0];
                            }
                        }
                    }
                    std::fwrite(&row[0], 1, row.size(), f);
                }
                std::fclose(f);
            }
        }
        (void)uncompressedMB;
        return;
    }

    const int T = a.threads;
    const int B = a.batch;
    std::vector<nvjpeg2kHandle_t> handles((size_t)T, nullptr);
    std::vector<std::vector<DecSlot> > slots((size_t)T);
    for (int t = 0; t < T; ++t) {
        CHECK_NVJ(nvjpeg2kCreateSimple(&handles[t]));
        slots[t].resize((size_t)B);
        for (int b = 0; b < B; ++b)
            decoderSlotInit(slots[t][b], handles[t], width, height, comps,
                            bytesPerSample);
    }
    printMemory();

    for (int t = 0; t < T; ++t) {
        CHECK_NVJ(nvjpeg2kStreamParse(handles[t], &bitstream[0],
                                      bitstream.size(), 0, 0,
                                      slots[t][0].jstream));
        CHECK_NVJ(nvjpeg2kDecodeImage(handles[t], slots[t][0].state,
                                      slots[t][0].jstream, nullptr,
                                      &slots[t][0].img, slots[t][0].stream));
        CHECK_CUDA(cudaStreamSynchronize(slots[t][0].stream));
    }

    std::atomic<int> next(0);
    const int total = a.repeat;

    Clock::time_point t0 = Clock::now();
    std::vector<std::thread> workers;
    for (int t = 0; t < T; ++t) {
        workers.push_back(std::thread([&, t]() {
            for (;;) {
                int start = next.fetch_add(B);
                if (start >= total) return;
                int n = total - start;
                if (n > B) n = B;
                for (int b = 0; b < n; ++b)
                    CHECK_NVJ(nvjpeg2kStreamParse(handles[t], &bitstream[0],
                                                  bitstream.size(), 0, 0,
                                                  slots[t][b].jstream));
                for (int b = 0; b < n; ++b)
                    CHECK_NVJ(nvjpeg2kDecodeImage(handles[t],
                                                  slots[t][b].state,
                                                  slots[t][b].jstream, nullptr,
                                                  &slots[t][b].img,
                                                  slots[t][b].stream));
                for (int b = 0; b < n; ++b)
                    CHECK_CUDA(cudaStreamSynchronize(slots[t][b].stream));
            }
        }));
    }
    for (size_t i = 0; i < workers.size(); ++i) workers[i].join();
    double wall = msSince(t0);

    std::printf("Total J2K Decode time:\n");
    std::printf("- GPU pipeline including all transfers for %d images "
                "per %d thread%s = %.1f ms; %.1f FPS;\n",
                total, T, (T == 1 ? "" : "s"), wall, total * 1000.0 / wall);
    std::printf("- GPU and CPU pipelines including image reader and writer "
                "threads: %.1f ms\n", wall);
}

// ---------------------------------------------------------------------------

int main(int argc, char** argv) {
    Args a = parseArgs(argc, argv);
    if (a.input.empty()) {
        std::printf("usage: %s -i input -o output [-a irrev|rev] [-c 32] "
                    "[-l 6] [-q 85] [-repeat N] [-async -thread T -b B] "
                    "[-discard] [-info] [-showFrames] [-targetsize BYTES] "
                    "[-tol SHARE] [-qlo Q] [-qhi Q] "
                    "[-noupload]\n",
                    argv[0]);
        return 1;
    }
    CHECK_CUDA(cudaSetDevice(a.device));
    printHeader(a);

    if (a.decode) {
        benchDecode(a);
    } else {
        Image im = readImage(a.input);
        if (a.targetSize > 0) runCalibration(a, im);
        else benchEncode(a, im);
    }
    return 0;
}
