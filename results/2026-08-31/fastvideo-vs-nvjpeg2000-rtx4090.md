# Fastvideo JPEG2000 vs nvJPEG2000 on RTX 4090

*A snapshot of the article as it stood on 2026-08-31. The living text is at <https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm>; this copy is tied to the measurement run it belongs to and is not edited by hand.*

*Licence: CC BY-ND 4.0. Reprinting in full and quoting are allowed; rewriting and translating are by agreement.*

---

![JPEG2000 lossy: encoding and decoding, fvJPEG2000 and nvJPEG2000 on an RTX 4090](https://www.fastcompression.com/img/blog/jpeg2000-gpu-benchmark/j2k-summary-2026-08-31-1200.webp)

*Encoding and decoding side by side, lossy mode. On the left fvJPEG2000 is 3.9 to 6.6 times faster, on the right the two are level.*

## Overall test results

RTX 4090, matching compressed file size, three repeats per point. Every number in this article comes from one run made on 2026-08-31: encoding, decoding, energy and the quality checks alike.

**At encoding fvJPEG2000 is faster, and by a wide margin.** 1914 frames per second against 292 on 2K lossy, 616 against 160 on 4K. The gap runs from 3.9 to 6.6 times depending on the frame and the mode. This is the typical task: a data stream has to be compressed as fast as possible, and everything there comes down to encoder performance.

**At decoding the two codecs are level.** 1024 frames per second for fvJPEG2000 against 1033 on 2K lossy, and 436 against 438 on 2K lossless — under a percent apart, and it goes both ways. On 4K the gap is larger and also goes both ways: on lossy nvJPEG2000 is ahead by 8 %, 428 against 394; on lossless fvJPEG2000 is ahead by 8 %, 145 against 134.

**Single-frame latency is a separate value, and the winners differ.** In single image mode, where what matters is the response time for one frame rather than throughput, the fvJPEG2000 encoder is 1.5 to 2.5 times faster: 2.6 ms against 5.1 ms on a 2K lossy frame. At decoding a single frame nvJPEG2000 is ahead, by 1.5 to 2.1 times.

Below is how this was measured, why it comes out this way and how to repeat it yourself.

## 1. What is compared and why

There are currently several JPEG2000 codec implementations for the GPU, both commercial and open source. This article compares the two codecs an engineer most often has to choose between.

The first codec comes from the **nvJPEG2000** library by NVIDIA. The library is free, but it ships separately from the CUDA Toolkit: it can be downloaded from the NVIDIA site or installed from a Python package. In the rest of the article this codec is referred to by its full name; in tables it is shortened to **NV**.

The second one is the [JPEG2000 codec](https://www.fastcompression.com/products/gpu-jpeg2000.htm) by **Fastvideo**, further **fvJPEG2000**, in tables **FV**. It ships as part of the [Fastvideo SDK](https://www.fastcompression.com/products/sdk.htm) and is licensed on a commercial basis.

**Why these two codecs?** There are others. Kakadu is a commercial JPEG2000 library from the Australian company Kakadu Software; Comprimato is a commercial GPU JPEG2000 codec from the company of the same name. Neither of them was tested here: we did not ask their developers for permission and we are not going to interpret their license terms for them. The performance measurement procedure is published in full — anyone who holds a license for these products can run the same tests and publish their own results.

There is also the open implementation OpenJPEG, but it runs on the CPU, and the performance gap against a GPU is very large. It makes sense to test that codec separately.

Any engineer's first question is simple: why pay if NVIDIA already has a free solution? Pictures and promises do not answer that question. Measurements do — ones the reader can repeat on their own GPU, on their own images. This article is about how to organize such measurements, and what they showed.

One caveat that matters: **we do not consider NVIDIA a competitor.** fvJPEG2000 is written in CUDA, NVIDIA's own platform, and runs on NVIDIA GPUs. This is a comparative analysis, not an argument: an engineering measurement of two different implementations of one standard, with all the details needed to repeat it.

### The idea of the article in one sentence

**What matters here is not the performance results but the method by which they were obtained.** The results themselves go out of date with every new version of the driver, the library and the GPU; the procedure behind them lasts much longer. That is why the article is built so that it can be read as a manual: how to bring two different codecs to comparable conditions, in which modes speed can be measured and why there are at least four of them, what goes into the measured time, and how to make sure the decoder really restored the image instead of doing only part of the work.

Three rules follow from this, and the text returns to them in every section:

1. **Codecs have to be compared at the same result, not at the same value of the quality parameter.** Quality scales differ from codec to codec, and the common unit of measurement becomes the size of the compressed file in bytes. On top of that, the quality of the restored images has to be controlled as well — only together do these two conditions make the comparison correct.
2. **Encoding speed in fps means nothing without stating the operating mode and codec parameters.** The processing time of a single frame and the overall throughput under streaming processing are different valuess, and they can differ quite a lot.
3. **Speed alone is not enough for a comparison.** Every measurement comes with a full cycle: the image is encoded, decoded and compared with the original.

If this is all the reader takes away, the article has done its job, even if the specific results have changed by then.

This work is the first part of a larger topic. The plans for it are collected in [section 15](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#15-open-project-on-github): the next measurements, and the open project into which the method moves from the article into code.

## 2. Source images

*The first rule requires comparison at the same result. The result depends entirely on what was fed in — so we have to start with the images.*

The measurements use two images that are publicly available and have been used in public JPEG2000 benchmarks since 2019. The files can be downloaded and run locally: [2k_wild.ppm](https://www.fastcompression.com/img/test_j2k/2k_wild.ppm) and [4k_wild.ppm](https://www.fastcompression.com/img/test_j2k/4k_wild.ppm). These are ordinary photographic scenes with a wide range of detail: both smooth areas and fine texture. Such material matters because the compression ratio at a given quality is determined entirely by the content of the frame.

| File | `2k_wild.ppm` | `4k_wild.ppm` |
|---|---|---|
| Resolution | 1920 × 1080 | 3840 × 2160 |
| Channels | 3 | 3 |
| Bit depth | 8 bit | 8 bit |
| Size, MB | 5.93 | 23.73 |

The PPM format was chosen deliberately: it is an uncompressed file with a minimal header — format, dimensions, maximum sample value (in effect, the bit depth) — followed immediately by the image data. Such a file is read quickly and easily, and both codecs get **exactly the same bytes** as input: no difference in unpacking the source, no influence of third-party libraries.

What this set covers and what it does not. Two resolutions are enough to see the main thing: how behavior changes when the frame stops being small for the GPU. A 2K frame does not load an RTX 4090 completely, a 4K frame does — and that changes a lot.

What the set does not cover, although both codecs can do it: **bit depth above eight bits** per channel. Both fvJPEG2000 and nvJPEG2000 can work with data up to 16 bits per channel, and that is exactly where medical images and satellite frames live — the areas JPEG2000 is usually chosen for. They are not covered in these tests: codec behavior at 12 and 16 bits requires a separate data set and a separate analysis. The same goes for 8K frames and larger, multi-tile images and monochrome material.

A separate caveat about the method. The measurements are arranged as "one frame repeated N times", not "N different frames". A 2K frame takes 5.9 MB, a 4K frame 23.7 MB, and both fit entirely into the level 3 cache of a modern CPU. That is, after the first iteration the source data is taken from the cache, not from RAM. For estimating the speed of the algorithm itself this is correct — we measure the codec, not the memory subsystem — but it is not the same as processing a folder of different files.

## 3. How the parameters were chosen

This is a very important part of the work, and whether the results mean anything at all depends on it.

### 3.1. Common denominator

The two codecs can do different things. A comparison only makes sense at those compression parameters that are available to both, and all of them have to be specified explicitly on both sides rather than left "at default": default values may differ.

| Compressed file parameter | FV | NV |
|---|---|---|
| File format | JP2 | stream_type = STREAM_JP2 |
| Wavelet, lossy | -a irrev (CDF 9/7) | irreversible = 1 |
| Wavelet, lossless | -a rev (CDF 5/3) | irreversible = 0 |
| Code-block size | -c 32 | code_block_w = code_block_h = 32 |
| Resolution levels | -l 6 | num_resolutions = 6 |
| Quality layers | 1 | num_layers = 1 |
| Progression order | LRCP | prog_order = LRCP |
| Color transform | enabled | mct_mode = 1 |
| Chroma subsampling | 4:4:4 | full-size components |
| Tiles | disabled | enable_tiling = 0 |
| SOP and EPH markers | disabled | enable_SOP/EPH_marker = 0 |
| Precincts | default | num_precincts_init = 0 |

Four of these rows are not an arbitrary choice but a forced one, and that is worth saying directly.

**Code-block size 32×32.** fvJPEG2000 supports 16×16, 32×32 and 64×64, nvJPEG2000 only 32 and 64, so 16×16 drops out of the comparison. Of the two that remain we took 32×32: it allows a higher degree of parallelism on the GPU.

**One quality layer.** In nvJPEG2000 the number of layers can only be one — the interface accepts no other value. In the fvJPEG2000 encoder there is also one layer. So per-layer quality is left out of the comparison.

**Progression order LRCP.** The fvJPEG2000 encoder produces only LRCP, the decoder understands all five. nvJPEG2000 can do all five when encoding. The common denominator is LRCP.

**SOP and EPH markers disabled.** In nvJPEG2000 they must be disabled, they cannot be turned on. Accordingly they are disabled in fvJPEG2000 as well.

**Chroma subsampling 4:4:4.** Both codecs also support 4:2:2 and 4:2:0, but the mode without chroma loss was taken for the comparison: it does not add yet another variable to the tests and is equally available to both sides. Separate reference points for 4:2:2 and 4:2:0 — only for fvJPEG2000 and with an explanation of why only for it — are collected in [section 9](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#9-chroma-subsampling-reference-points-for-fvjpeg2000).

### 3.2. The two codecs have different quality scales

Here the two sides have to be brought to a common approach, and the two codecs do not offer the same number of ways to set the loss.

**fvJPEG2000 has two, and they can work together.** The first is the quality scale `q` from 0 to 100: it controls quantization, that is, how coarsely the wavelet coefficients are rounded. The file size then comes out as a consequence. The second is PCRD mode (Post-Compression Rate-Distortion, the `-cr` option): you give it the compression ratio you need, and the encoder discards the least significant bits of the code blocks until the compressed frame fits the size that ratio implies. Here it is the other way round: the size is set, and the quality comes out as a consequence. The two ways combine: first quantization at the given `q`, then PCRD down to the given compression ratio.

**nvJPEG2000 has three:** a target signal-to-noise ratio, a quantization step, or a Q-factor on a 1–100 scale. All three tell the encoder how coarsely to encode. A target for file size or compression ratio is not among them.

So there is exactly one common ground, the quality scale: in fvJPEG2000 it is `q`, and of the three nvJPEG2000 scales the Q-factor works the same way. Sections [6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding)–[10](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#10-quality-control) are built on it: fvJPEG2000 encodes at `q` = 85, and nvJPEG2000 searches for the Q-factor that gives a file of the same size. PCRD mode is off in those measurements: nvJPEG2000 has no such mode at all. How it affects encoding speed is measured separately, in [section 11](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#11-pcrd-mode-fixed-file-size-and-encoding-speed).

You cannot simply set 85 on both sides and get the same compression: these are different scales, and the files will come out different in size. And if the sizes of the compressed frame differ, the codecs also do different amounts of work, and any speed comparison loses its value.

How the fvJPEG2000 scale behaves on these two images:

| Quality `q` | 2K ratio | 2K file, kB | 4K ratio | 4K file, kB |
|---|---|---|---|---|
| 80 | 14.2:1 | 429 | 27.7:1 | 878 |
| 83 | 11.8:1 | 517 | 22.5:1 | 1078 |
| 85 | 10.3:1 | 588 | 19.5:1 | 1246 |
| 87 | 9.1:1 | 671 | 16.8:1 | 1449 |
| 90 | 7.3:1 | 828 | 13.2:1 | 1847 |

Note that at the same value of `q` the compression ratio of the two frames differs by almost a factor of two. This is not an error and not a quirk of the codec. The two frames are different images, and there is no point in comparing their compression ratios with each other: at a given quality the compression ratio is determined by the content of the frame. What matters is something else — the same value of `q` does not give the same file size.

### 3.2.1. File size is a result, not a value you set

**The quality parameter does not fix the file size, it fixes the quantization scheme.** The encoder decomposes the image with a wavelet transform and quantizes the coefficients — the more coarsely, the lower the quality. How many bytes come out of that depends on the quality factor and on the content of the frame. File size here is not a parameter but a result.

To see this clearly, it helps to count not the compression ratio but **bits per pixel**: how many bits on average are needed to encode one pixel of the image. The source data is 24 bits per pixel, that is, eight bits per channel.

| Mode | 2K, bpp | 4K, bpp |
|---|---|---|
| Lossy, q 85 | 2.32 | 1.23 |
| Lossless | 11.44 | 8.65 |

**What follows from this in practice.**

First, **the phrase "compression 20:1" means nothing without stating the image.** The same value of the quality parameter on another frame will give another compression ratio. When codecs are compared somewhere "at 20:1 compression", the first question is: measured on what, exactly?

Second, **a value of the quality parameter cannot be carried from one project to another and expected to give the same file size.** If a fixed size is exactly what is needed — for example, to fit into a given bandwidth or into storage capacity — then what is required is not a quality parameter but bitrate control, which reduces the size of the compressed frame to the required value. In fvJPEG2000 this is done by PCRD mode ([section 3.2](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#32-the-two-codecs-have-different-quality-scales)); it is not used in this comparison, and how it affects speed is in [section 11](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#11-pcrd-mode-fixed-file-size-and-encoding-speed).

Third, this is exactly why the comparison of the two codecs is built **on matching the size of the output file**, not on matching the value of the quality parameter. Otherwise one of the sides would be doing less work, and any comparison of speed would be meaningless.

### 3.3. We compare at the same compressed file size

**Why can’t two codecs be compared at the same quality setting?** Because their quality scales are different: the same number in the settings gives a different file size and a different amount of distortion in each codec. So the comparison runs on a common denominator — the compressed file size: only at an equal file size do the two codecs do comparable work.

Hence the rule: **compare not at the same value of the quality parameter but at the same result.** Here "result" means **the size of the compressed file in bytes**. Not "roughly similar quality", not "the same quality factor", but precisely the size in bytes that is visible in the file properties.

The reason is that the amount of work depends directly on the file size. A file twice as large means twice as much encoded data that the encoder has to process. If one codec produces a file a third smaller than the other, it also does less work, and comparing their speed is pointless: the codec that produced the smaller file will look faster.

File size is also convenient because it is defined unambiguously. The compression ratio depends on what is counted as the source size, and a quality estimate depends on which quality measure was chosen.

The procedure is as follows. fvJPEG2000 encodes the reference file at quality 85. Then nvJPEG2000 searches for its Q-factor by bisection: it encodes, looks at the size, moves the boundary, repeats — until it hits the target to within one tenth of a percent.

The result of the search:

| Image | 2K lossy | 4K lossy |
|---|---|---|
| Target, bytes | 601,703 | 1,275,547 |
| Q found | 87.29 | 87.14 |
| Result, bytes | 601,940 | 1,274,517 |
| Deviation | 0.04% | 0.08% |

The sizes are matched to better than one tenth of a percent — the codecs have an equal amount of work.

**How much the mapping between the two scales depends on the frame.** The values 87.29 and 87.14 are very close, which suggests that the two quality scales map onto each other by a constant factor. This was worth checking: if it were so, the value found could be carried from image to image.

The check was run separately, as follows: the same search is repeated with a tolerance twice as strict (0.05% by size), at three quality levels and from two different initial search intervals — [1, 100] and [50, 99]. The second is needed to separate a property of the codecs from an artifact of the search procedure itself.

| FV quality | Equivalent for 2K | Equivalent for 4K | Difference |
|---|---|---|---|
| 80 | 74.86 | 74.77 | 0.10 |
| 85 | 87.29 | 87.17 | 0.12 |
| 90 | 94.63 | 94.56 | 0.07 |

The conclusion: **the two quality scales differ, but they are very close to each other**, and finding the exact correspondence is outside the scope of this work. It may well depend on the content of the frame as well. The value found carries over to another image as a good first approximation, but a search for a specific file size still has to be done again. That is exactly why in the procedure the search is done for each image separately, and not once for the whole set.

For lossless mode there is nothing to search for: there is no quality parameter there at all, and both codecs must produce a file that decodes back exactly. The sizes of the compressed files:

| Image | FV file, kB | NV file, kB | Ratio |
|---|---|---|---|
| 2K lossy | 588 | 587 | 10.3:1 |
| 4K lossy | 1246 | 1244 | 19.5:1 |
| 2K lossless | 2896 | 2896 | 2.1:1 |
| 4K lossless | 8754 | 8754 | 2.8:1 |

A compression ratio of about 2:1 for a lossless compression algorithm is a usual value for JPEG2000 on photographic material, and it matches what we publish on the pages about RAW compression.

## 4. Method: codec speed is not a single number

![measurement modes: single images, batch, multithreaded mode and multithreaded mode with batching](https://www.fastcompression.com/img/blog/jpeg2000-gpu-benchmark/j2k-four-modes-1200.webp)

*One GPU and one frame give four different speeds - and all four are correct. The difference is which work overlaps with which.*

*This section is about the second rule: a speed in frames per second means nothing unless the mode is stated.*

The same codec on the same GPU can produce different speed values. The difference is not in how the measurement is taken, but in what work is done in the same amount of time — in effect, in the way the work is parallelized. So the first question in any comparison is not only "how many frames per second", but also "in which mode was this value obtained".

### 4.1. Measurement modes

1. **Single image mode** — in Fastvideo SDK applications this is processing of one image, `single image mode`, once or repeated many times (the `-repeat` option). When the frame is processed many times, processing of the next frame starts only after work on the previous one is fully finished, and the work runs in one thread. In effect we average the running time over thousands of repeats, and there is no overlap between frames. This gives **the processing time of a single frame** — exactly the value you need when response time matters. It is stable and repeatable to within one percent over a large number of repeats.
2. **Batch mode.** Several frames are combined by software into one larger virtual frame, so that this large frame is loaded into the GPU for processing in one go. The number of processed frames at the output stays the same, because the combining of frames is virtual. There are no separate measurements for this mode in the article: it never turns out to be the fastest one, so in the tables of sections [6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding) and [7](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#7-decoding) batching always goes together with threads.
3. **Multithreaded mode, several threads.** Several CPU threads, each with its own codec state and its own queue of GPU jobs (CUDA stream). Processing of different frames then overlaps — different frames are processed on the GPU at the same time — which increases the speed.
4. **Multithreaded mode with batching.** In addition, several frames are combined into one larger virtual frame, so that more data is loaded into each processing thread at once. This is the fastest mode in terms of maximum performance.

The first mode answers the question "how much time is needed to process one frame", the others answer "how many frames per second can we process". These are different quantities, not different accuracy for the same task: in multithreaded mode and in batch mode the latency of a single frame is **worse** than in single image mode — that is the price of higher overall throughput.

There is, of course, also the option of processing images on several GPUs at once, but this article does not cover it. What is discussed here is compression and decompression performance on a single GPU.

How much this matters: with fvJPEG2000 encoding 2K with lossy compression, single image mode gives 381 frames per second, while the best combination of threads and batch gives 1914. That is a difference of five times, on the same GPU, on the same frame, at the same compression. With nvJPEG2000 on the same task the picture is quite different: 198 and 292, that is, about 1.5 times. The same question "how many frames per second" has different answers for the two codecs depending on the mode — so it matters which mode you are in.

### 4.2. What is included in the measured time and what is not

The second question after the mode is what exactly falls inside the measured time.

![how the JPEG2000 codec time is measured: from the image in host RAM to the result back in host RAM](https://www.fastcompression.com/img/blog/jpeg2000-gpu-benchmark/j2k-measurement-boundaries-1200.webp)

*The boundaries in multithreaded mode: the timer starts when the image is in host RAM and stops when the result is back in host RAM. The transfers over the bus are inside the measured time on both sides, and so is Tier-2 on the CPU — it is part of the algorithm. Time spent on disk and waiting for the reader and writer queues is outside. In single image mode the boundary is a different one, described below.*

**The rule depends on the mode, and that has to be said outright.**

**In single image mode** the timer runs from the data where the codec picks it up to the result on the other side: for the encoder, from the source frame in GPU memory to the compressed image in host memory; for the decoder, from the compressed image in host memory to the reconstructed frame in GPU memory. The transfer of the pixels themselves over the bus is outside the count — on neither side.

**In multithreaded mode** the timer runs from host memory to host memory in both directions: the transfers over the bus are inside the measured time on both sides.

**Why the difference.** In single image mode frames go one at a time, and the codec itself reports the time of each of its stages — it can be measured from the inside. In multithreaded mode work on several frames runs on the GPU at once, and the time of one stage of one frame cannot be separated from the work on its neighbours; the only observable fact is that a frame has been processed whole. So the boundaries can only be external ones: when the data left host memory and when the result came back to it.

**What time is measured.** The measured time includes all the work of the codec, all its stages one after another. For the encoder this is data preparation and color transform, the wavelet transform, quantization and EBCOT Tier-1 on the GPU, then the transfer of the result to the CPU and Tier-2 — building the compressed image. For the decoder it is the same in reverse order. The fact that part of the work runs on the CPU is not a flaw of the measurement but a property of JPEG2000: not every stage of this algorithm can be parallelized efficiently.

Separately about the part of the work that runs on the CPU. The heaviest stage of JPEG2000, EBCOT Tier-1, is computed on the GPU. Tier-2 — building the compressed image out of the finished packets when encoding, parsing its structure when decoding — is arranged differently in the two codecs, and what is known about it differs as well.

**In fvJPEG2000** Tier-2 runs on the CPU, both when encoding and when decoding.

**In the nvJPEG2000 decoder** it runs on the CPU as well, and the NVIDIA documentation states this directly: "Tier 2 decode stage (first stage of decode) is run on the CPU. All other stages of the decoding process are offloaded to the GPU" ([docs.nvidia.com](https://docs.nvidia.com/cuda/nvjpeg2000/introduction.html)). In the program this is the `nvjpeg2kStreamParse` step: it takes the compressed image from host memory and parses its structure.

**For the nvJPEG2000 encoder the documentation makes no such definite statement.** All it says is that the library uses both the GPU and the CPU to create JPEG2000 bitstreams, that the source image must be in GPU memory and that the compressed image is written to host memory. Which part of the work goes to the CPU is not stated, and we did not look at the encoder with a profiler. So we do not claim it either: that the CPU is at work during encoding follows from the documentation, that Tier-2 in particular runs on it does not. This item is listed in [section 16](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#16-what-remains-unverified), among the unverified ones.

**All CPU work is inside the measured time on both sides.** Taking this part out of the brackets would be incorrect: in fvJPEG2000 the CPU work is included in the measured time, so it must be included for nvJPEG2000 as well.

The work that runs on the CPU is inside the measured time in both modes and on both sides. The disk is excluded everywhere: nothing is written out, otherwise we would also be measuring the speed of the storage device. Waiting for the reader and writer queues is outside the count. Frames per second in multithreaded mode is the total number of frames divided by the time of the slowest thread.

### 4.2.1. The boundaries in the NVIDIA samples are drawn differently

In NVIDIA's open sample set `CUDALibrarySamples` the measurement boundaries are drawn differently, and that is worth naming: without it the numbers from their publications and the numbers in this article look comparable when they are not.

**The decoding sample.** Frames are processed strictly one at a time: one decoder state, one queue of GPU jobs, a wait after every frame. The `-b` option, described as a batch size, groups only the reading of files from disk and does not change how the work is done.

The timer wraps a single call to `nvjpeg2kDecodeImage`. Parsing of the compressed image — `nvjpeg2kStreamParse`, that is Tier-2, which NVIDIA's own documentation calls the first stage of decoding — is added to the total separately, but its duration is rounded to whole seconds while parsing a frame takes milliseconds. It contributes zero. Allocation of GPU buffers, reading the file and writing the result are outside the timer, and there is no copy of the finished frame back to host memory in the measured loop at all.

So the number that sample prints is the time of the part of the algorithm that runs on the GPU: without Tier-2 and without the transfers. Our single-frame measurement also excludes the transfer of the pixels, but it includes Tier-2, which is part of the algorithm.

**The encoding sample.** Frames go one at a time there as well. The timer wraps the whole loop and includes `nvjpeg2kEncodeRetrieveBitstream` — the copy of the compressed image into host memory. Uploading the source frame to the GPU stays outside: it is done while reading the file. That is exactly the boundary of our own single image mode.

We did not bring our decoding measurements to their boundary. Parsing the compressed image is Tier-2, that is **part of the JPEG2000 decoding algorithm** and not a preparation for it; NVIDIA's own documentation calls it the first stage of decoding. A measurement that leaves it out shows the time of a part of the algorithm, not of the whole of it.

### 4.3. The optimum is found by search, not assigned

The number of CPU threads and the batch size are not a "reasonable choice" but values found by search. The optimum lies inside the range, and in different tasks it may be in a different place. For the fvJPEG2000 encoder at 2K batching helps noticeably: eight threads with a batch of two give 1914 frames per second against 1776 for eight threads without batching, while sixteen threads turn out to be slower than eight. At 4K the picture is different: 8×1, 16×2 and 8×4 give 616, 610 and 605 frames per second — the same value within the spread between measurement series. A large frame loads the GPU even without batching, and there is nothing left to add.

That is why the measurement conditions publish **the full list of combinations used**, not the winning one: what is reproduced is the procedure, not a ready-made combination. Six combinations were tried, written as "number of threads × batch size": 8×1, 8×2, 16×2, 8×4, 32×1 and 32×2. The notation 16×2 reads as follows: sixteen CPU threads, each with two frames at a time.

**The last two were added in this series of measurements, and here is why.** The earlier grid had no point where the threads are many and the frame in a thread is one — so it had never been checked what simply giving the codec more CPU threads does. On a 32-core processor, 32 threads is the whole machine, and such a point answers a direct question: is it enough to give the library more threads? The answer is in [section 6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding), and it is not the same for the two codecs.

The tables below give all six combinations and, separately, the best one for each codec. In the rest of the article, instead of "the best combination of number of threads and batch size", we say **the best combination of threads and batch** for short.

**An important caveat: batching works differently in the two codecs.** This has to be said outright, otherwise the same word in the tables would mean two different things.

First, about what the notation itself means. **8×2 is eight CPU threads, and in each of them two frames are in flight on the GPU at the same time.** There are exactly eight CPU threads at any batch size; they do not double. Something else doubles — the number of jobs the GPU computes at the same moment: not eight, but sixteen.

In fvJPEG2000 these two frames go into the codec in a single call: the batch is real, and the codec handles them as one job. This is a standard capability of Fastvideo SDK.

nvJPEG2000 has no such call. Not a single function in the library accepts an array of images — only one image per call. So the GPU load is built up differently: **each thread creates as many independent codec states and as many CUDA streams as the batch size specifies.** The thread submits encoding of the first frame to its first stream, and immediately after it, without waiting for the result, the second frame to the second stream, and only then waits for both. The calls are asynchronous and the streams are independent, so both frames are computed on the GPU at the same time.

**What this is built from.** Everything here is standard: multiple codec states, CUDA streams and asynchronous calls are all regular features of the NVIDIA library and of CUDA, and there are no workarounds involved. Only one thing is missing from the library — a call that accepts several frames at once. So the order of the calls has to be built by hand: the library provides the building blocks, but not a ready-made mode.

This is also worth saying because **it does not work by itself**. A program that simply calls nvJPEG2000 one frame per thread — and that is exactly how the NVIDIA samples are built — will get eight simultaneous jobs instead of sixteen, and the result will be lower. How much lower can be seen at one and the same number of threads: on a 2K lossy frame eight threads give the encoder 205 frames per second without the technique and 245 with a batch of two, that is 1.2 times more. For the decoder on that same task the starting point is not measured reliably ([section 8](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#8-where-the-speedup-comes-from)), so take the neighbouring one: on 4K lossy eight threads give 208 frames per second without the technique and 428 with four frames in flight — twice as much.

We still report exactly these values and take them as the best for nvJPEG2000: the comparison must be against the maximum that can be obtained from the library, not against what the standard way of using it gives.

### 4.4. What was not measured

Tiles, decoding of a selected region, bit depth above eight bits, multi-component transforms beyond the standard ones, operation on Jetson. Some of this exists on only one of the two sides and is compared by a feature table, not by speed; some of it is a separate piece of work.

## 5. Test system

*A performance result without a description of the conditions it was obtained in is useless. All the test conditions are listed here, with the software and hardware parameters, together with the date; this matters.*

| Item | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 4090, 24 GB |
| GPU driver | 610.88 |
| GPU maximum power | 450 W |
| CPU | AMD, 32 threads |
| RAM | 128 GB |
| Fastvideo JPEG2000 codec (FV) | Fastvideo SDK 0.23.1.0, CUDA 13.3 |
| nvJPEG2000 library (NV) | version 0.11.0.51 |
| Operating system | Windows 11 |
| Bus speed, measured | 25.2 GB/s from CPU to GPU |
| Measurement series per point | 3, the tables show the median |
| Measurement date | 31 August 2026 |

All the measurements are run by a single script: it prepares the reference files, runs the quality search, measures the performance of both implementations, checks the quality of the restored image and prints a ready table. A full run with three repeats per point takes about an hour. The script picks how many frames to process in each test on its own: first a short speed probe, then a calculation that makes the measuring window the same length everywhere. So a fast point and a slow point are measured for equally long rather than over an equal number of frames, and the run is built the same way on any GPU.

## 6. Encoding

![JPEG2000 encoding speed on RTX 4090: fvJPEG2000 and nvJPEG2000 at the best combination of threads and batch size](https://www.fastcompression.com/img/blog/jpeg2000-gpu-benchmark/j2k-encode-4090-2026-08-31-1200.webp)

*Encoding in multithreaded mode: for each codec the number of threads and the batch size that give the best speed. Same values as in the tables below.*

*The results follow. Their value rests entirely on sections [3](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#3-how-the-parameters-were-chosen) and [4](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#4-method-codec-speed-is-not-a-single-number): the same file size on both sides, the same compression parameters and a chosen operating mode.*

Every cell in the tables below is frames per second. The "single" row comes from single image mode, the other six from multithreaded mode with different combinations of "number of threads × batch size". The best value in a column is in bold, and the same combination is named in the "optimum" row. The two frames are split into two tables so that each stays narrow.

The bottom row is **how many CPU cores are busy on average** when the codec runs at its optimum. It was measured separately, together with the energy ([section 12](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#12-energy-per-frame-and-cpu-load)), and it is here because speed alone does not say what it cost: on a server that is doing something else as well, busy cores are as much a resource as watts.

**2K frame, 1920 × 1080**

| Mode | Lossy, FV | Lossy, NV | Lossless, FV | Lossless, NV |
|---|---|---|---|---|
| single | 381 | 198 | 329 | 146 |
| 8×1 | 1776 | 205 | 1120 | 158 |
| 8×2 | **1914** | 245 | **1179** | 164 |
| 16×2 | 1687 | 278 | 1039 | 178 |
| 8×4 | 1910 | 226 | 1136 | 165 |
| 32×1 | 1308 | 275 | 858 | 164 |
| 32×2 | 1450 | **292** | 912 | **187** |
| Optimum | 8×2 | 32×2 | 8×2 | 32×2 |
| CPU cores busy | 7.0 | 29.5 | 7.2 | 29.8 |

**4K frame, 3840 × 2160**

| Mode | Lossy, FV | Lossy, NV | Lossless, FV | Lossless, NV |
|---|---|---|---|---|
| single | 195 | 128 | 140 | 56 |
| 8×1 | **616** | 134 | **371** | 62 |
| 8×2 | 572 | 148 | 369 | 63 |
| 16×2 | 610 | **160** | 322 | **64** |
| 8×4 | 605 | 143 | 333 | 63 |
| 32×1 | 565 | 158 | 294 | 63 |
| 32×2 | — | — | — | — |
| Optimum | 8×1 | 16×2 | 8×1 | 16×2 |
| CPU cores busy | 7.5 | 14.7 | 7.6 | 14.8 |

The dashes in the 32×2 row of the 4K table mean the combination was not measured at all: thirty-two threads with two frames each on 4K do not fit in GPU memory for the fvJPEG2000 encoder. A combination that drops out for one codec is not measured for the other either — otherwise the table would carry a cell filled on one side and empty on the other, and it would read as "the other codec was slower here" when in truth it was never measured.

**How many times faster is fvJPEG2000 than nvJPEG2000 at encoding?** On 2K lossy it is 1914 frames per second for fvJPEG2000 against 292 for nvJPEG2000, which is 6.6 times; on 4K lossy it is 616 against 160, or 3.9 times. In single image mode the gap is smaller: from 1.5 to 2.5 times. The compressed files are the same size for both codecs.

| Encoding | FV over NV single image mode | FV over NV threads and batch |
|---|---|---|
| 2K, lossy | 1.93x | 6.55x |
| 2K, lossless | 2.25x | 6.31x |
| 4K, lossy | 1.53x | 3.86x |
| 4K, lossless | 2.49x | 5.77x |

**In single image mode the fvJPEG2000 encoder is 1.5 to 2.5 times faster than the nvJPEG2000 encoder.** This is encoding latency — the response time for one frame, not throughput: one frame, one CPU thread, no overlap between frames, files of the same size. In milliseconds per frame, fvJPEG2000 against nvJPEG2000: 2K lossy — 2.6 against 5.1; 2K lossless — 3.0 against 6.8; 4K lossy — 5.1 against 7.8; 4K lossless — 7.1 against 17.8. This is about encoding only; decoding gives a different picture, it is in the next section.

**The nvJPEG2000 encoder gains almost nothing from multithreaded mode.** All its results sit in a narrow band: from 205 to 292 frames per second on 2K and from 134 to 160 on 4K. Going from single images to 8 threads increases the speed by only three and a half percent; after that only a denser load on the card adds a little. For comparison, fvJPEG2000 on the same task speeds up by a factor of 4.7 when going from single images to 8 threads.

**A word about thirty-two threads — the part of the grid that is new here.** What was being checked is whether it is enough to give the library more CPU threads. For nvJPEG2000 on 2K lossy 32×2 did come out ahead — 292 frames per second against 278 for 16×2 — but that is a gain of 5 %, and the repeats on these points disagree by more, so it cannot be called a win; on 4K thirty-two threads give nothing at all. For fvJPEG2000 thirty-two threads at encoding are **worse** than eight: 1308 and 1450 against 1914. The encoder already fills the card with eight threads, and the extra threads only add work for the CPU.

Look at the CPU cores row. At its optimum fvJPEG2000 occupies 7.0 to 7.6 cores, nvJPEG2000 from 14.7 to 29.8. So the NVIDIA encoder not only delivers fewer frames but takes twice as much CPU for it on 4K and four times as much on 2K.

We checked whether this was a bug in the benchmark harness. A separate check runs on the 2K frame, at the best combination of threads and batch for nvJPEG2000, as a single run with no averaging over series: the encoder gives 279 frames per second. If the copy of the image from host memory into GPU memory is removed from the same loop, the result is 323 — 16 % more.

The copy does cost time, as it should, but even without it the encoder stays six times slower than fvJPEG2000, and multithreading still gives it almost no speedup.

The same benchmark harness, the same GPU, the same threading scheme — and the decoder of the same library speeds up by a factor of 3.5 under it. So the cause is not how the benchmark harness is written, but that the nvJPEG2000 encoder and decoder are built differently.

## 7. Decoding

![JPEG2000 decoding speed on RTX 4090: fvJPEG2000 and nvJPEG2000 at the best combination of threads and batch size](https://www.fastcompression.com/img/blog/jpeg2000-gpu-benchmark/j2k-decode-4090-2026-08-31-1200.webp)

*Decoding in multithreaded mode with batching: for each decoder the number of threads and the batch size that give the best speed were used.*

The tables are built the same way as in the previous section: rows are modes and combinations, columns are codecs, and the bottom row is how many CPU cores are busy at the optimum.

**2K frame, 1920 × 1080**

| Mode | Lossy, FV | Lossy, NV | Lossless, FV | Lossless, NV |
|---|---|---|---|---|
| single | 144 | 298 | 116 | 237 |
| 8×1 | 425 | 310 | 272 | 360 |
| 8×2 | 640 | 751 | 365 | 403 |
| 16×2 | 873 | 764 | 425 | 412 |
| 8×4 | **1024** | **1033** | 425 | **438** |
| 32×1 | 596 | 532 | 395 | 369 |
| 32×2 | 883 | 719 | **436** | 411 |
| Optimum | 8×4 | 8×4 | 32×2 | 8×4 |
| CPU cores busy | 7.6 | 4.1 | 28.6 | 3.5 |

**4K frame, 3840 × 2160**

| Mode | Lossy, FV | Lossy, NV | Lossless, FV | Lossless, NV |
|---|---|---|---|---|
| single | 96 | 193 | 59 | 91 |
| 8×1 | 244 | 208 | 133 | 108 |
| 8×2 | 348 | 318 | 130 | 125 |
| 16×2 | 377 | 323 | 140 | 125 |
| 8×4 | 350 | **428** | 120 | **134** |
| 32×1 | 330 | 207 | **145** | 108 |
| 32×2 | **394** | 335 | 141 | 124 |
| Optimum | 32×2 | 8×4 | 32×1 | 8×4 |
| CPU cores busy | 25.9 | 4.8 | 27.8 | 3.4 |

One cell in the 2K table needs a caveat: for nvJPEG2000 at 8×1 the measurements split in two — the same point on the same machine gives now 310 frames per second, now 539. The table carries the median of the run, 310; the analysis is in [section 8](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#8-where-the-speedup-comes-from).

Here the picture is different, and it depends on the mode.

**Which JPEG2000 decoder is faster on a GPU?** At the best combination of threads and batch size the two codecs are level: on 2K lossy 1024 frames per second for fvJPEG2000 against 1033 for nvJPEG2000, on 2K lossless 436 against 438 — under a percent apart, and it goes both ways. On 4K the gap is larger: on lossy nvJPEG2000 is ahead by 8 % (428 against 394), on lossless fvJPEG2000 is ahead by 8 % (145 against 134). In single image mode nvJPEG2000 is 1.5 to 2.1 times faster. Below is the breakdown by frame and mode:

| Decoding | Single image mode | Threads and batch |
|---|---|---|
| 2K, lossy | NV by 2.07x | NV by 0.8 % |
| 2K, lossless | NV by 2.04x | NV by 0.3 % |
| 4K, lossy | NV by 2.01x | NV by 8 % |
| 4K, lossless | NV by 1.53x | FV by 8 % |

**In single image mode the nvJPEG2000 decoder is 1.5 to 2.1 times faster.** On three of the four combinations of conditions it is exactly twice. This result is not in favour of fvJPEG2000, and where the time of a single frame matters it is the one that counts.

**At the best combination of threads and batch the gap disappears.** On the 2K frame the difference between the decoders is under a percent and it goes both ways: 1024 frames per second against 1033 on lossy and 436 against 438 on lossless. On the 4K frame the gap is about eight percent, and it goes both ways as well: on lossy nvJPEG2000 is ahead, 428 against 394; on lossless fvJPEG2000 is ahead, 145 against 134.

**The optimum of the fvJPEG2000 decoder has moved to thirty-two threads** on three tasks out of four, and the gain there is small: on 2K lossless 32×2 gives 436 frames per second against 425 for 16×2, that is 2.7 %. The CPU cores row should be read together with that. Where the optimum landed on thirty-two threads, the decoder occupies 26 to 29 cores; where it landed on eight, 7.6. What exactly that 2.7 % cost we cannot say: cores are counted only at the point that turned out to be the optimum, and nobody measured the CPU load at 16×2. But the order of the price is visible, and the choice between a few percent of speed and noticeably fewer busy cores is not one a table makes for you.

The files from the two encoders are of the same size, but inside they are built differently, and in theory one of them could give the decoder less work. This is checked by cross-decoding: each decoder is run on a file made by the other encoder. The difference across all eight combinations of conditions did not exceed one and a half percent, and in half of them it was under three tenths of a percent. So the decoder comparison is correct: the files put the same load on them, and the result applies to the decoders themselves.

## 8. Where the speedup comes from

![Share of the encode and decode time by stage for fvJPEG2000 on an RTX 4090](https://www.fastcompression.com/img/blog/jpeg2000-gpu-benchmark/j2k-stages-4090-2026-08-31-1200.webp)

*Where the time goes inside one frame. EBCOT Tier-1 takes half to three quarters of it, and Tier-2 runs on the CPU — that is why threads and batching help as much as they do.*

**Where does the speed difference between the codecs come from?** It adds up from three parts: how well each stage is parallelised inside, whether batching is available, and how multithreading behaves. nvJPEG2000 has no batching at all, and its encoder barely speeds up with threads — from single image mode to eight threads it gains 3.5 percent, while fvJPEG2000 on the same task speeds up 4.7 times.

The speedup accumulates on several levels at once, and they do different things.

**Inside each stage of the JPEG2000 algorithm.** This is the lowest level, and the tables do not show it at all: each stage — the wavelet transform, quantization, EBCOT Tier-1 — is itself spread over thousands of parallel GPU threads (CUDA threads). How efficiently that is done determines the frame processing time in any mode. The most accurate timing per stage comes from a profiler. The fvJPEG2000 codec has an `-info` option that prints the running time of every stage of encoding or decoding for a given frame.

**Batching** glues several frames into one for processing: the GPU sees one large frame instead of several small ones. nvJPEG2000 has no batching, and its role is played by the technique from [section 4.3](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#43-the-optimum-is-found-by-search-not-assigned) — several frames in flight on the GPU at the same time within a single thread. Neither of the two overlaps stages — they only increase the load. Hence a consequence that the measurements confirmed: batching helps at 2K and is useless or harmful at 4K, where a single frame already loads the card. For the fvJPEG2000 encoder at 4K the best combination turned out to be 8×1, that is, eight threads with no batching at all — in lossy mode and in lossless mode alike. But it is ahead of its nearest neighbour by less than the repeats disagree among themselves, so the honest way to put it is that batching gives nothing at 4K.

**Multithreading** parallelizes the work, and processing of one frame can run in parallel with processing of another frame on the GPU.

**Separate read and write pools** reduce the latency related to the disk. They are not used in these tests: the disk is excluded. But fvJPEG2000 does have that option.

A separate breakdown shows how large the contribution of each technique is. Take a 2K frame in lossy mode and look at how many times the frames per second grow as extra techniques are switched on — first for the encoders, then for the decoders. There are no new measurements here: all speeds are taken from the tables of sections [6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding) and [7](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#7-decoding), from the "2K, lossy" rows.

It is calculated as follows. Single image mode is taken as the unit — there frames go one at a time and nothing overlaps. Then multithreading is switched on without batching, that is, the 8×1 combination: the ratio to single image mode shows what multithreading gave. Then the best combination of threads and batch is taken; the ratio to 8×1 shows what the move to it added. The last column is the product of the first two, that is, the total speedup relative to single image mode.

In the table below the first three rows are frames per second, taken directly from [the table in section 6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#encoding-speed-table). The last three are ratios of those numbers; they are rounded, but computed from the unrounded frames per second.

| Encoder | fvJPEG2000 | nvJPEG2000 |
|---|---|---|
| Single image mode | 381 | 198 |
| 8×1 | 1776 | 205 |
| Optimum | 1914 (8×2) | 292 (32×2) |
| What multithreading gave | 4.7x | 1.0x |
| What the move to the optimum gave | 1.1x | 1.4x |
| Total speedup | 5.0x | 1.5x |

**The row "what the move to the optimum gave" means different things for the two encoders**, and that has to be said directly. For fvJPEG2000 the best combination turned out to be 8×2: the same number of threads, only batching was added — so 1.1x here is the contribution of batching in its pure form. For nvJPEG2000 the best one turned out to be 32×2: four times as many threads and two frames in flight in each of them — so 1.4x is the contribution of both changes at once. nvJPEG2000 has no batching at all: two frames at a time are obtained by the technique from [section 4.3](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#43-the-optimum-is-found-by-search-not-assigned) — separate codec states and separate job queues within a thread.

The nvJPEG2000 encoder gets no speedup from multithreading at all — the factor is 1.035, that is, three and a half percent, which is smaller than the spread of the measurements themselves. Everything it gains comes not from multithreading but from a denser load on the card: more threads and two frames in flight in each. In total this is 1.5 times against 5.0 for fvJPEG2000 — and that is exactly where the gap comes from that reaches six and a half times in [section 6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding).

For the decoders the picture is different, and the gap there is much smaller.

In the table below the speeds are taken from the table in [section 7](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#7-decoding), the "2K, lossy" rows. For both decoders the best combination is eight threads, the same as in the 8×1 row: only the number of frames in flight inside a thread changes. So both sides are compared here in their pure form.

| Decoder | fvJPEG2000 | nvJPEG2000 |
|---|---|---|
| Single image mode | 144 | 298 |
| 8×1 | 425 | 310 |
| Optimum | 1024 (8×4) | 1033 (8×4) |
| What multithreading gave | 3.0x | 1.0x |
| What the move to the optimum gave | 2.4x | 3.3x |
| Total speedup | 7.1x | 3.5x |

This reads as follows: multithreading makes the fvJPEG2000 decoder three times faster, and a batch of four frames adds another 2.4 times, together 7.1 times relative to single image mode. For the nvJPEG2000 decoder the two steps fall out quite differently: multithreading gives it almost nothing, while four frames in flight inside a thread speed it up 3.3 times; together that is 3.5 times.

**For the nvJPEG2000 encoder nothing at all comes from the number of CPU threads** — the factor is 1.035, which is zero within the spread of the measurements. Everything it gains beyond a single frame comes from several frames being in flight inside a thread, that is from the technique of [section 4.3](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#43-the-optimum-is-found-by-search-not-assigned), which its own samples do not use.

**For the decoder that cannot be said**, and the reason has to be named. The factor of 1.0 in the table above is computed from the 8×1 cell, and that is the one place in this article where the measurements split in two — now 310 frames per second, now 539. Until that cell is settled, the decoder speedup cannot be split into two steps: both factors are computed from it. Only the total is solid — 3.5 times from single image mode to the best combination — and it does not depend on the disputed cell. The nvJPEG2000 decoder starts from a single frame twice as fast but scales half as well, which is why the two meet at the optimum.

**How the frame processing time is distributed between the stages of JPEG2000.** The Fastvideo test application with the `-info` option prints the time of every stage separately. The stages in the table below are named as in that output and follow the same order — for the encoder from the source pixels to the compressed image, for the decoder the other way round. The numbers are the median of five runs from the same series of 31 August, a 2K frame and a 4K frame, lossy compression; the logs of all runs are in the repository.

**This is an estimate, not a measurement, and here is why.** The codec reports stage times only for a single frame: when running with repeats it does not print them at all — this breakdown is only meant for estimating where the time goes. So one-off costs land inside every stage: the first kernel launch, the card coming up to speed and the synchronizations that the option itself inserts. How much that is can be seen in the two bottom rows of the table: the sum of the stages is 4.65 ms against a real 2.62 ms for encoding 2K. The extra two milliseconds are smeared across the stages, and they distort the fast stages on a small frame most of all: the color transform with the level shift takes 0.69 ms on 2K and 0.74 ms on 4K, although the frame is four times larger. So almost all of that time does not depend on the frame size and is not work. The shares in the table should be read as an order of magnitude, not as exact percentages.

**The breakdown exists only for fvJPEG2000.** The nvJPEG2000 library does not report stage times; its test application prints only the total, so the codecs cannot be compared stage by stage — the table describes how one codec is built, not an advantage of one over the other.

Two rows of the table are worth decoding. **The color transform and the level shift** come first for the encoder and, in the inverse direction, last for the decoder, so in the table this is a single row with numbers on both sides. **Buffers gathering** is the collection of the finished code-blocks into one contiguous buffer before the transfer to the CPU.

In the table below the shares are rounded to whole percent, so a column may add up to 99 or 101. The bottom row is the time of a single frame in single image mode from sections [6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding) and [7](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#7-decoding), for comparison with the sum of the stages.

| Stage | Where | Encoding 2K | Encoding 4K | Decoding 2K | Decoding 4K |
|---|---|---|---|---|---|
| Color transform and level shift | GPU | 15% | 11% | 5% | 4% |
| Wavelet transform | GPU | 8% | 8% | 6% | 6% |
| EBCOT Tier-1 | GPU | 57% | 51% | 73% | 60% |
| Buffers gathering | GPU | 4% | 3% | — | — |
| Copy over the bus | — | 1% | 2% | 1% | 1% |
| Tier-2 | CPU | 15% | 26% | 15% | 29% |
| Sum of the stages, ms | — | 4.65 | 6.67 | 8.05 | 12.28 |
| Real frame time, ms | — | 2.62 | 5.13 | 6.96 | 10.41 |

**About quantization.** It has no row of its own in this output: it is not separated into a stage, it runs on the GPU inside the neighbouring stages and has no timer of its own. One more item of the output is not a stage and did not make it into the table — the line "PCRD is disabled": it confirms that the search for a given file size is switched off in these measurements, as stated in sections [3.2.1](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#321-why-the-same-quality-gives-different-compression) and [11](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#11-pcrd-mode-fixed-file-size-and-encoding-speed). Writing the finished file to disk is printed separately by the program and marked as excluded from the count.

Three conclusions from this estimate are large enough that the one-off costs do not cancel them.

**The main work is entropy coding, EBCOT Tier-1.** From a half to three quarters of the whole time, and it is exactly what determines the speed of the codec. Everything else together weighs less.

**The CPU work grows with the frame size, the GPU work almost does not.** Tier-2 takes 0.72 ms on 2K and 1.73 ms on 4K when encoding, 1.23 and 3.60 ms when decoding — that is, two and a half to three times more on a frame four times larger. Over the same step the GPU stages add tenths of a millisecond. This is exactly the CPU work mentioned in [section 4.2](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#42-what-is-included-in-the-measured-time-and-what-is-not), and on a large frame it turns from a detail into a quarter of the time.

**The inverse color transform and level shift in the decoder weigh little** — 0.39 ms out of eight on 2K. This matters for comparing the decoders: the nvJPEG2000 test application leaves the result as separate planes and does not do this work ([section 16](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#16-what-remains-unverified)). Its contribution is small and does not affect the conclusion.

**How repeatable the results are.** Each point was measured three times; the median goes into the tables. A point whose three repeats disagreed by more than 7% is measured again, up to two extra runs, and the median is then taken over all five. On average the spread is small: 4.5% for fvJPEG2000 on encoding and 2.1% on decoding, 2.8% and 3.6% for nvJPEG2000.

But the average is not the whole story. Out of a hundred and ten points with repeats, eleven still disagreed by more than seven percent after the extra runs — and the run report names them one by one, with the spread and the number of runs. For most of them the cause is visible in the power draw of the card: on the slow repeat the card takes noticeably fewer watts, that is, it was simply not being fed — something else took the CPU time at that moment. Throttling would look the other way round, with the power at the limit. The main conclusions in this article rest on differences of several times, clearly larger than any such spread, but a single cell of a table should be read with that caveat in mind.

**One cell is built differently from the rest, and it is worth telling in detail** — not because it matters for the conclusions, but because it is exactly the kind of case that sections on method are written for. nvJPEG2000, decoding 2K lossy, 8×1: here the repeats do not scatter, they split in two. We measured this point twenty more times in a row. Nine launches gave 309 frames per second, eleven gave 539, and inside each group the values agree to a tenth. The state is decided once when the program starts and holds for the whole run, from the first frame to the last.

It is not heat and it is not another program on the machine. The GPU clock is the same in both states, 2745 MHz, the temperature 46 to 52 degrees, GPU utilisation 97 and 98 percent; the neighbouring point 8×2, measured in between, ran evenly the whole time. What differs is something else: **the slow state spends 45% more CPU time per frame** — 13.3 against 9.2 milliseconds of a core — and the card, given less work, draws 135 watts instead of 171. So it is the CPU side of decoding that slows down. The cause appears to be on the operating system side — most likely in how it placed eight threads across a 32-core processor — but we could not establish it, and we are not going to pass a guess off as an explanation.

The table in [section 7](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#7-decoding) carries the median of the run, 310. The neighbouring cells, though, argue for 539: on nvJPEG2000 decoding, thirty-two threads with one frame each give exactly what eight threads with one frame each give — 369 against 360 on 2K lossless, 207 against 208 on 4K lossy, 108 against 108 on 4K lossless. On 2K lossy 32×1 gives 532, and with the value 539 the cell joins that same row, while with 310 it stays the only exception. We keep the measured value anyway and name the doubt out loud: fitting a number to a rule is a reliable way to get a tidy table and a wrong result. The logs of all twenty launches are in the repository.

A separate note on the dependence on data volume. In lossless compression there is five times more data, and both sides run into the efficiency of entropy decoding — there the results nearly converge. In lossy compression there is little work, and then the fixed per-frame overhead decides, and fvJPEG2000 loses on that: the gap in milliseconds barely grows, even though there is five times more work.

## 9. Chroma subsampling: reference points for fvJPEG2000

*Why this section. The whole comparison above runs on material without subsampling, i.e. 4:4:4 — that is a correct common denominator. But in real pipelines chroma is often subsampled, and the question "how much does it give" is asked all the time. Here are a few reference points, so that the order of magnitude is known.*

**What chroma subsampling is.** The human eye distinguishes changes in brightness noticeably better than changes in color. A technique more than half a century old is built on this: the image is converted from red-green-blue into luma plus two color differences, and the color differences are stored at a lower resolution.

- **4:4:4** — chroma is stored in full, nothing is thrown away;
- **4:2:2** — chroma is subsampled by two horizontally;
- **4:2:0** — by two both horizontally and vertically, that is, a quarter of the samples is left in the color channels.

It helps to count in terms of input data: at 4:4:4 there are three samples per pixel, at 4:2:2 two, at 4:2:0 one and a half. That is, **before encoding** there is 1.5 and 2 times less data respectively. Hence the double effect: the file comes out smaller, and encoding is faster, because there is physically less work.

An important caveat: this is loss **on top of** what quantization gives. On photographic material it is hard to notice; on sharp color edges — for example, on colored text, diagrams, titles — it is visible at once. That is why film production and master copies stay at 4:4:4, while streaming and broadcast move to 4:2:2 and 4:2:0.

**Why nvJPEG2000 is not in this table.** Not because the library cannot do it, but because the comparison would be incorrect. The NVIDIA codec takes components already brought to the required size: the subsampling itself would have to be done outside, by third-party code. Then the measured time would include the time of our subsampling filter, and it would no longer be the codecs being compared. Such a comparison is worth making, but separately and with the filter stated explicitly.

The "Single" and "Multithreaded" columns of the table below give encoding fps.

The quality parameter is the same in all rows, `q` = 85: only the sampling mode changes. PSNR is computed against the original full-color frame, so it also includes the loss from subsampling — that is exactly the price one needs to know in advance.

| Frame | Format | File, kB | Ratio | Single | Multithreaded | PSNR, dB |
|---|---|---|---|---|---|---|
| 2K | 4:4:4 | 588 | 10.3:1 | 379 | 1920 | 40.4 |
| 2K | 4:2:2 | 508 | 12.0:1 | 397 | 2007 | 38.6 |
| 2K | 4:2:0 | 457 | 13.3:1 | 412 | 2108 | 37.3 |
| 4K | 4:4:4 | 1246 | 19.5:1 | 196 | 574 | 42.0 |
| 4K | 4:2:2 | 1123 | 21.6:1 | 212 | 689 | 40.8 |
| 4K | 4:2:0 | 1042 | 23.3:1 | 225 | 728 | 39.9 |

The 4:4:4 row here is the same configuration as in [section 6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding), but the results are slightly different: 379 and 1920 against 381 and 1914. These are different parts of one measurement run, and the discrepancy fits within the spread between repeats given in [section 8](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#8-where-the-speedup-comes-from). Values should be compared within one table, not between tables.

**What follows from this.** There is a gain, but it is noticeably more modest than the volume of the input data would suggest. At 4:2:2 there is a third less data before encoding, while the file shrinks by 13% (2K) and by 10% (4K); at 4:2:0 there is half as much data, while the file shrinks by 22% and by 16%. The reason is simple: after the conversion to luma and color differences the chroma channels already compress harder than the luma one, and the codec has already taken most of that redundancy. Subsampling takes away what is left.

Speed grows about as modestly: at 2K, from 4:4:4 to 4:2:0, encoding gets 9% faster in single image mode and 10% faster in multithreaded mode; at 4K, 15% and 27%. On large frames the effect is stronger, because there more time goes into processing the samples themselves rather than into the fixed overhead.

Quality, however, drops quite noticeably: at 2K, from 4:4:4 to 4:2:0, 3.1 dB is lost; at 4K, 2.1 dB. Part of this loss is irreversible — subsampled chroma cannot be restored, whereas quantization can be relaxed simply by raising the quality parameter.

Hence the practical conclusion: if the task is to make the file smaller, raising the compression ratio at 4:4:4 is usually a better deal than moving to 4:2:0. Subsampling makes sense where it is already present in the input stream (the material came from the camera in 4:2:2 and there is no point in converting it to 4:4:4), or where the constraint is not on the file but on the volume of data that has to be pushed through the pipeline.

## 10. Quality control

**How do you check that the two codecs were compared under the same conditions?** Three checks. In lossless mode the decoded frame must match the source bit-for-bit — it did, for both codecs, in all four combinations. In lossy mode, at an equal file size, PSNR is compared, and the difference between the codecs is a few tenths of a decibel. And the measurements were made on builds without a watermark, which the program verified.

*Third rule: speed alone is not enough for a comparison.*

Measuring speed without checking the result guarantees nothing: a decoder that does less work than it should looks faster. So on every run, for each of the eight combinations of conditions, a full cycle is performed: the image is encoded, decoded and compared with the original.

**Lossless mode: exact match.** All four combinations — both codecs, both frames — produced a decoded image bit-for-bit equal to the original. This is a mandatory condition: if there were no match in even one case, it would no longer be lossless compression and there would be nothing to compare the speeds against.

**Lossy mode: signal-to-noise ratio.** The comparison runs at a matched file size, so the table answers a direct question — at the same file size, who has less distortion.

| Image | fvJPEG2000, dB | nvJPEG2000, dB | Difference |
|---|---|---|---|
| 2K | 40.42 | 40.60 | 0.18 |
| 4K | 41.97 | 42.23 | 0.26 |

The difference favours nvJPEG2000, but it is small. For a sense of scale: a difference of 1 dB on photographic material is usually already indistinguishable by eye, and tenths lie within what the choice of parameters inside a single codec gives. So at an equal file size the quality of the two implementations is practically the same — and that is exactly the conclusion that was needed: it confirms that the speed comparison is made at a comparable result, and not because one codec saves on quality.

**About the watermark.** Demo builds of the codecs put a watermark on the frame, and then the decoded frame cannot be compared directly with the original file: it would be the watermark being measured, not the codec. These measurements were made on a build without the watermark, and the benchmark harness verified this: neither codec had a watermark, so PSNR was computed directly against the original.

The quality check is reproducible on the demo version as well, and no special build is needed for it. The technique is this: the reference for PSNR is not the original file but the frame that came back through a **lossless** round trip on the same build. The watermark is applied before encoding, and lossless mode preserves everything bit-for-bit — so such a reference is exactly what the encoder received, and PSNR measures the encoding loss, not the watermark. The harness also checks this very condition: two independent lossless round trips must match byte for byte. All of this is already built into the script and turns on by itself.

## 11. PCRD mode: a fixed file size and encoding speed

**How much does PCRD mode slow encoding down?** Least of all by 1.40 times on 4K: that is when the base quality is set in advance and PCRD only trims the file to the required size. If quantization is set to q = 100 and PCRD delivers the whole compression ratio, the gap is larger: 1.56 times on 4K and 1.84 on 2K. In single image mode the gap is smaller than in multithreaded mode: on 2K it is 1.84 times against 2.76.

In the previous sections both codecs worked the same way: we set a quality parameter, and the size of the compressed file came out as a consequence. In production that is not always the case. Often the bandwidth of the channel or the capacity of the medium is known in advance, and the frame has to fit a given size: compress by exactly a factor of twenty, or fit into so many megabytes.

The fvJPEG2000 codec can do this directly: in PCRD mode you set the compression ratio you need, and the encoder itself decides which least significant bits to discard in order to reach it. nvJPEG2000 has no such mode, so this whole section is about fvJPEG2000 only: there is nothing to compare.

**Quantization and PCRD mode work in sequence, quantization first, then PCRD.** The wavelet coefficients are quantized according to the quality parameter, and then PCRD discards as many least significant bits as it takes to reach the given compression ratio ([section 3.2](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#32-the-two-codecs-have-different-quality-scales)). That is how it is normally used: the base quality is chosen in advance, on frames of the same kind, and the `-cr` option sets the final file size.

Two measurements follow. The first shows how fast PCRD mode itself runs at different compression ratios. The second answers the main question of this section: how much slower the encoder is when a file of one and the same size is produced with this mode and without it.

**First, the mode itself at different compression ratios.** Quantization here ran at `q` = 100, that is, it was relatively weak, and the resulting compression ratio was set mainly by the `-cr` option.

The table below is about encoding only: PCRD mode works on the encoder side, the decoder knows nothing about it and simply reads a finished file. The values were obtained in single image mode — frames are processed one at a time, without multithreading and without batching ([section 4.1](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#41-four-measurement-modes)).

| Frame | Compression ratio | File, kB | Encoder, fps |
|---|---|---|---|
| 2K | 5:1 | 1213 | 200 |
| 2K | 10:1 | 602 | 212 |
| 2K | 20:1 | 295 | 223 |
| 4K | 5:1 | 4662 | 128 |
| 4K | 10:1 | 2408 | 122 |
| 4K | 20:1 | 1182 | 130 |

Encoding speed hardly depends on which compression ratio was requested: at 4K it is 128, 122 and 130 frames per second at 5:1, 10:1 and 20:1. That is what one should expect while quantization stays at `q` = 100: the amount of data to encode is the same, and the compression ratio changes only how many least significant bits are discarded afterwards.

**Now the main point: how much PCRD mode slows encoding down.** To keep the comparison correct, every variant produces a file of one and the same size — the size that quality `q` = 85 gives: 588 kB at 2K and 1246 kB at 4K. That is the quality sections [6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding)–[10](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#10-quality-control) work at. The same size is reached in four ways: by quantization alone, without PCRD, and by three more where PCRD brings the size down — at `q` = 90, 95 and 100.

The "single image mode" and "threads and batch" columns below give frames per second in two measurement modes: one frame at a time, and at the combination of thread count and batch size that came out best for that row (given in brackets). The "slowdown" column shows how many times slower a row is than the first row for the same frame — the one with PCRD off. The file sizes agree across all rows to better than one tenth of a percent, so the rows can be compared with each other.

All the numbers in the table below come from a single run, so they can be divided by one another. The rows without PCRD are the same mode that produced [the table in section 6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#encoding-speed-table); the speeds measured here differ from the published ones by a few percent.

| Frame | Quality `q` and mode | Single image mode | Slowdown | Threads and batch | Slowdown | PSNR, dB |
|---|---|---|---|---|---|---|
| 2K | 85, no PCRD | 358.5 | — | 1879 (8×2) | — | 40.41 |
| 2K | 90 and PCRD | 211.5 | 1.70× | 823 (8×1) | 2.28× | 39.80 |
| 2K | 95 and PCRD | 201.5 | 1.78× | 755 (8×1) | 2.49× | 39.74 |
| 2K | 100 and PCRD | 194.6 | **1.84×** | 681 (8×1) | **2.76×** | 39.25 |
| 4K | 85, no PCRD | 187.2 | — | 614 (8×1) | — | 41.97 |
| 4K | 90 and PCRD | 134.1 | 1.40× | 400 (8×1) | 1.54× | 41.50 |
| 4K | 95 and PCRD | 129.1 | 1.45× | 362 (8×1) | 1.70× | 41.51 |
| 4K | 100 and PCRD | 120.1 | **1.56×** | 314 (8×1) | **1.96×** | 41.24 |

**How much the encoder slows down depends on whether quantization was set.** If quantization stays at `q` = 100 and the compression ratio is reached by PCRD alone, the encoder runs 1.56 times slower at 4K and 1.84 times slower at 2K. If quantization is set in advance, part of the speed comes back: at 4K the gap narrows from 1.56 to 1.40 times. About a quarter to a third comes back, and it cannot come back in full — the PCRD stage itself remains in any case, and the first row does not have it at all.

**In multithreaded mode the gap is larger than in single image mode.** At 2K it is 1.84 times by single frames and 2.76 times at the best combination of threads and batch; at 4K, 1.56 and 1.96 times. The difference is substantial: if a system is sized by total throughput, what PCRD mode takes away will be noticeably more than single image mode suggests.

**At one and the same file size PCRD mode also gives slightly worse image quality.** At 2K the PSNR is 39.25 dB against 40.41 dB in the row without PCRD; at 4K, 41.24 against 41.97. The pattern is the same in every row: the lower the quality level, the less data reaches the entropy encoder, so compression runs faster. `q` = 90 is faster than `q` = 95, and `q` = 95 is faster than `q` = 100. By PSNR the two combinations are almost equal, and both are noticeably better than PCRD alone.

**What remains is to work out which quality to set.** In the table above the best variant is `q` = 90, but there is a gap between it and `q` = 85: at 85 the frame already comes out at the required size and PCRD has nothing to trim, while at 90 the natural size is already one and a half times the target. The optimum lies somewhere between them, so `q` = 86, 87 and 88 were measured separately.

This is a separate run, so the absolute speeds in it are slightly higher than in the table above — a different measurement session. What has to be compared are the ratios, and they agree: the "100 and PCRD" row gives 1.79 times at 2K and 1.54 times at 4K here, against 1.84 and 1.56 in the previous run. All measurements are in single image mode, and the file sizes are matched to better than one tenth of a percent.

| Frame | Quality `q` and mode | Encoder, fps | Slowdown | PSNR, dB |
|---|---|---|---|---|
| 2K | 85, no PCRD | 372.1 | — | 40.42 |
| 2K | 86 and PCRD | 228.4 | 1.63× | 40.40 |
| 2K | 87 and PCRD | 227.1 | 1.64× | 40.23 |
| 2K | 88 and PCRD | 230.3 | 1.62× | 39.98 |
| 2K | 100 and PCRD | 207.4 | 1.79× | 39.25 |
| 4K | 85, no PCRD | 194.4 | — | 41.97 |
| 4K | 86 and PCRD | 145.1 | **1.34×** | 42.00 |
| 4K | 87 and PCRD | 142.7 | 1.36× | 41.89 |
| 4K | 88 and PCRD | 142.2 | 1.37× | 41.67 |
| 4K | 100 and PCRD | 126.6 | 1.54× | 41.24 |

**The nearest quality above turns out to be the best one.** At 4K `q` = 86 gives the smallest gap of all the variants — 1.34 times — and a PSNR of 42.00 dB, that is, no worse than a file of the same size compressed by quantization alone (41.97). At 2K the speed at 86, 87 and 88 is the same to within one percent, while PSNR falls: 40.40, 40.23 and 39.98 dB. So here too the nearest value above is the one to take.

The rule that follows is simple: set the base quality one or two units above the value at which the frame already comes out at the size you need. PCRD then has very little left to trim, encoding slows down the least, and the image quality stays at the level of ordinary quantization.

**Where the gap comes from can be seen in the time of the individual encoding stages.** The `-info` option prints that time for a single frame ([section 8](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#8-where-the-speedup-comes-from)), and two separate components are visible there. The first is the PCRD stage itself: the first row does not have it, the others do. The second is the EBCOT Tier-1 time: the higher the quality, the more data reaches the entropy encoder and the longer that stage runs.

As in [section 8](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#8-where-the-speedup-comes-from), one thing has to be kept in mind here: the `-info` option synchronises the stages against each other, so their sum comes out larger than the real frame processing time. These numbers can be compared between rows, but the column must not be added up.

| 4K, quality `q` and mode | Tier-1, ms | PCRD, ms |
|---|---|---|
| 85, no PCRD | 3.37 | — |
| 90 and PCRD | 3.94 | 1.85 |
| 95 and PCRD | 4.25 | 1.81 |
| 100 and PCRD | 4.84 | 1.77 |

In all three rows that have a PCRD stage it takes about the same time — around 1.8 ms. The Tier-1 time, on the other hand, grows as quantization gets weaker: 3.37, 3.94, 4.25 and 4.84 ms. At 2K the picture is the same: 2.76, 3.22, 3.41 and 3.70 ms, with the PCRD stage taking 1.5 to 1.7 ms. The file is the same size in all four rows; only the way it was produced differs.

**Why the tables say `q` = 100 when no quality parameter was set.** This was checked separately: setting `q` = 100 explicitly together with `-cr` gives the same numbers as leaving the quality parameter out — at 4K, 120.6 against 120.1 frames per second and a PSNR of 41.24 in both cases. So without a quality parameter the encoder quantizes exactly as it does at `q` = 100.

**What follows from this.** If the file size is not fixed and may vary from frame to frame, it is better to work with a quality parameter alone: that is both faster and better in quality. If the size is fixed — by the bandwidth of the channel, the write speed of the medium or a customer requirement — it is better to choose the quantization first, one or two units above the value at which the frame already comes out at the required size, and leave PCRD mode for the fine adjustment. Two ways of producing one and the same file can differ in speed by up to 2.8 times, so the mode of operation is better chosen while the system is being designed than after it has been built.

## 12. Energy per frame and CPU load

![Energy per frame, fvJPEG2000 and nvJPEG2000 on an RTX 4090, encoding and decoding](https://www.fastcompression.com/img/blog/jpeg2000-gpu-benchmark/j2k-energy-4090-2026-08-31-1200.webp)

*Joules per frame, less is better. On encoding the gap is 3.4 to 6.1 times; on decoding the speeds are nearly equal, and a frame still costs fvJPEG2000 1.3 to 1.8 times less.*

**How much energy does one frame cost?** It is easier to count the other way round: watts divided by joules per frame give the frame rate that a given power limit allows. At a limit of 100 W, fvJPEG2000 encodes 4K lossy at about 280 frames per second, nvJPEG2000 at about 83.

*Speed answers the question "how many frames will one GPU process". The energy the GPU consumes also matters a great deal.*

- **How many cards will fit.** A power supply is rated for a certain wattage, and how many cards fit into one chassis depends on the draw of a single card.
- **Where to put the heat.** Every joule spent turns into heat, and it has to go somewhere. In an airborne or embedded enclosure this limit can be reached before the available compute is exhausted.
- **How long the battery lasts.** On a drone or a portable rig the energy budget is finite, and joules per frame translate directly into a number of frames.
- **What it costs.** In a data center kilowatt-hours are money, and cooling costs come on top of what the cards draw.

**How to convert one into the other.** Joules per frame multiplied by frames per second give watts. The reverse conversion is more useful: the watts you have, divided by joules per frame, give the speed you can afford. With 100 watts allocated to compression, 4K lossy encoding gives about 280 frames per second on fvJPEG2000 and about 83 on nvJPEG2000.

**How the energy was measured.** We measure the energy the GPU consumes and attribute it to one frame. Power alone is no good for comparing codecs: the one that draws fewer watts but runs longer costs more. Joules per frame account for both the draw and the running time.

**Why an average makes sense here.** In every measurement the same kind of operation runs one after another: the same frame is encoded thousands of times with the same compression parameters. The frames differ neither in size nor in content, and the card is in a steady state. So the average energy per frame is the energy of any single frame, not a mix of different work. Were there different frames and different modes in the stream, the same average would hide the differences between them.

There are two meters, and they are independent.

- **Power sampling.** The `nvidia-smi` tool that ships with the NVIDIA driver reports the current draw of the card in watts. We sample it ten times a second, average over the run and multiply by the duration. The method is simple, but short spikes between samples are lost, and the whole running time of the program is counted, including start-up and buffer preparation.
- **The cumulative energy counter inside the card.** The card itself keeps a count of the millijoules spent since the driver was loaded — a ready-made total, with nothing lost between two readings. The value is read through NVML, NVIDIA's management interface (`nvmlDeviceGetTotalEnergyConsumption`). Not every model has this counter; the RTX 4090 does.

**The differential method and what it gave.** The counter is read from outside the program: a reading is taken before the run and after it, so fixed costs land inside it — starting the process, preparing buffers, the card coming up to speed. To remove them, each point is measured twice, on N frames and on 2N, and the energy of one frame is taken as the difference divided by N: everything that does not scale with the number of frames drops out of the difference.

The conclusion for anyone repeating this: a long run is enough, the difference between two runs adds nothing noticeable and costs twice as much time. The right way is to measure a window inside the loop itself — to start counting after a hundred frames, when the card is already up to speed — but for that the program has to read the counter on its own. We will do that in the next series of tests.

**Both meters gave the same answer:** the disagreement is 2 % at the median point and 10 % at the worst. The tables below show the counter readings computed by the differential method.

In both tables, for each codec the number of threads and the batch size that give the best speed were used. The power limit of the card is 450 watts. The last column is how many CPU cores are busy on average; the same numbers are in the bottom rows of the tables in sections [6](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#6-encoding) and [7](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#7-decoding).

**Encoding.**

| Frame | Mode | Codec | J/frame | Card power, W | CPU cores busy |
|---|---|---|---|---|---|
| 2K | lossy | fvJPEG2000 | 0.122 | 230 | 7.0 |
| 2K | lossy | nvJPEG2000 | 0.523 | 156 | 29.5 |
| 2K | lossless | fvJPEG2000 | 0.224 | 258 | 7.2 |
| 2K | lossless | nvJPEG2000 | 1.373 | 249 | 29.8 |
| 4K | lossy | fvJPEG2000 | 0.355 | 230 | 7.5 |
| 4K | lossy | nvJPEG2000 | 1.199 | 186 | 14.7 |
| 4K | lossless | fvJPEG2000 | 0.729 | 264 | 7.6 |
| 4K | lossless | nvJPEG2000 | 4.195 | 259 | 14.8 |

**Decoding.**

| Frame | Mode | Codec | J/frame | Card power, W | CPU cores busy |
|---|---|---|---|---|---|
| 2K | lossy | fvJPEG2000 | 0.178 | 177 | 7.6 |
| 2K | lossy | nvJPEG2000 | 0.254 | 255 | 4.1 |
| 2K | lossless | fvJPEG2000 | 0.435 | 179 | 28.6 |
| 2K | lossless | nvJPEG2000 | 0.794 | 343 | 3.5 |
| 4K | lossy | fvJPEG2000 | 0.517 | 176 | 25.9 |
| 4K | lossy | nvJPEG2000 | 0.653 | 279 | 4.8 |
| 4K | lossless | fvJPEG2000 | 1.384 | 182 | 27.8 |
| 4K | lossless | nvJPEG2000 | 2.471 | 325 | 3.4 |

**What the tables show.** On encoding nvJPEG2000 draws fewer watts than fvJPEG2000: 156 against 230 on 2K lossy. But it produces six and a half times fewer frames for those watts, and per frame it comes out 4.3 times more expensive. Across all four tasks the energy gap runs from 3.4 to 6.1 times.

On decoding the speeds are nearly equal, while the card works differently: 176–182 watts for fvJPEG2000 against 255–343 for nvJPEG2000. Per frame this gives a gain of 1.3 to 1.8 times: 0.178 joules against 0.254 on 2K lossy and 0.435 against 0.794 lossless.

**On the CPU it is the other way round, and that has to be said too.** On encoding nvJPEG2000 occupies 14.7 to 29.8 cores against our 7.0 to 7.6. On decoding it is the reverse: nvJPEG2000 gets by on three to five cores, while fvJPEG2000 occupies 26 to 29 on three tasks out of four, because its optimum there landed on thirty-two threads. The speed gain for that is small: on 2K lossless 32×2 is 2.7 % faster than 16×2. How many cores that same task takes at sixteen threads we did not measure — cores are counted only at the optimum — but if the CPU is needed for something else in the system, those percent are worth giving up for a smaller point.

**What these figures do not include.** Both quantities refer to the GPU: everything on the board is counted, the CPU is not. We do not report the energy the CPU consumed: the GPU has a counter of its own that applies to it alone, while on the CPU too many things run at the same time to separate the codec's share from the total reliably.

## 13. What this means in practice

*Here the measurement results are turned into a decision — what to choose for your task.*

**Encoding — fvJPEG2000 is faster**, in all eight combinations of conditions: by 1.5 to 2.5 times in single image mode, that is on single-frame latency, and by 3.9 to 6.6 times at the best combination of threads and batch, that is on throughput. The gap is explained mainly by the fact that the nvJPEG2000 encoder barely speeds up from multithreading: 8 threads give it a speedup of 1.035 times against 4.7 for fvJPEG2000. On top of that it occupies two to four times more CPU cores.

**Decoding — level** at the best combination of threads and batch: on 2K the difference is under a percent and goes both ways, on 4K it is about eight percent and also goes both ways — nvJPEG2000 ahead on lossy, fvJPEG2000 on lossless. In single image mode, however, nvJPEG2000 is 1.5 to 2.1 times faster, and where the time of a single frame matters that is decisive. On decoding it is also noticeably lighter on the CPU: three to five cores against our seven, and against twenty-six on three tasks out of four.

**Quality at an equal file size is the same** — the PSNR difference is within three tenths of a decibel in favour of nvJPEG2000, that is, practically indistinguishable by eye.

**Energy per frame** repeats the speed picture but does not amplify it: on encoding the energy gap is close to the speed gap or slightly smaller — 4.3 times against 6.6 on 2K lossy. On decoding, at nearly equal speed, a frame costs fvJPEG2000 1.3 to 1.8 times less.

Next, these conclusions are worth translating into the language of tasks, because in different applications the requirements for the encoder and the decoder can differ a great deal.

**Where encoding is required.** These are camera applications, embedded systems among them: the data comes from cameras and has to be compressed right away, and no slower than the given frame rate. Both values matter here: throughput and single-frame latency — in real-time capture a frame has to be compressed before the next one arrives. On encoding latency fvJPEG2000 is ahead by 1.5 to 2.5 times.

- **Camera and industrial pipelines.** The stream from the sensor goes through transform algorithms and then into JPEG2000, with no intermediate frames written.
- **Satellite and aerial imaging.** Compression happens on board, then the data is transmitted and decoded on the ground. The encoder works where power, weight and the communication channel are limited, which means the price of a frame in joules and the performance of a single GPU matter a lot.
- **Film scanning and digital cinema package (DCP) mastering.** Thousands of frames in a row, each in JPEG2000 lossless or at high quality; the winner is whoever processes the whole material faster.
- **Microscopy and medical imaging.** The frames are large, capture is continuous, and resolution keeps growing.

**Where decoding is what matters.** These are applications for viewing and processing finished material.

- **Playback of digital cinema packages and master material.** A stream of frames has to be decoded in real time, without drops and with minimal latency; single image mode matters here: every frame must arrive on time.
- **Working through archives.** Terabytes of already compressed material, and on this task the free NVIDIA library should work very well.
- **Viewing and selective delivery of images** — satellite, medical, cartographic: the user opens a frame and waits, so the time to decode a single frame and put it on the monitor matters.

**And one more thing, about hitting a given file size.** If the pipeline has to fit a given bandwidth of the channel or the medium, that shows up in the speed: PCRD mode in fvJPEG2000 runs slower than a fixed quality parameter — by 1.3 to 1.8 times in single image mode and by 1.5 to 2.8 times at the best combination of threads and batch. The smaller gap is when the base quality has been set and PCRD only brings the size down; the larger one is when PCRD does all the work ([section 11](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#11-pcrd-mode-fixed-file-size-and-encoding-speed)). This has to be built into the calculation up front, rather than found out on a finished system.

All the results above were obtained on two ordinary photographic frames. On your material — with noise, with text, with medical or satellite specifics — the ratios will be different. [Send us your frames](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#contact-form): we will run them through both codecs by the same procedure and return the table and the decoded images, so that the conclusion is yours, not ours.

## 14. How to reproduce

*This is the section everything else was written for: a method is worth something only when you can run it yourself.*

All measurements are done by a single Python script. It builds the benchmark harness for nvJPEG2000 itself, prepares the reference files, searches for the quality setting that gives the same file size, runs encoding and decoding, and prints the table. The source images are published on the site. There are no hidden steps in the procedure: the output of every run, together with the full command line, is saved to a log, and any result can be reproduced by hand.

A full run with three repeats per point takes about an hour. The script picks the number of frames in each test itself, so that the measuring window is the same length everywhere — a fast point does not degenerate into a fraction of a second of measuring, and a slow one does not stretch out of proportion.

What goes into the measured time does not have to be taken on trust. The measuring part of the Fastvideo SDK ships as source, the nvJPEG2000 program is in our open repository (`bench/nvj2k_bench.cpp`), and the NVIDIA samples are in `CUDALibrarySamples` under a BSD licence. The boundaries described in sections [4.2](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#42-what-is-included-in-the-measured-time-and-what-is-not) and [4.2.1](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#421-measurement-boundaries-in-the-nvidia-samples) were read off those files, and every one of them can be found there by eye.

All of it is publicly available — the script, the benchmark harness, the results and the logs. Where exactly, and how to use it, is the next section.

## 15. Open project on GitHub

The script and the benchmark harness are published on GitHub: [github.com/fastvideo/jpeg2000-benchmark](https://github.com/fastvideo/jpeg2000-benchmark)

**Why it exists.** Any codec comparison published by one of the parties rightly raises the question: were the conditions cherry-picked? The answer to that question is not assurances, but the ability to take the procedure and run it yourself, on your own GPU and your own images, and to check the sources. The results in this article were obtained for the chosen images and for one GPU. The repository is a way to get the results of your own tests.

The second reason is simpler: the method is awkward to retell. It is far clearer to show it as code, where every decision is visible — which switches are set, what is included in the measured time and what is not, exactly how the quality search works and how the quality check is computed.

**What is there now:**

- the script that performs all the measurement stages described in this article;
- the source code of the nvJPEG2000 benchmark harness — the very one whose timing rule is analyzed in [section 4.2](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#42-what-is-included-in-the-measured-time-and-what-is-not);
- the results of every measurement run: ready tables, the same data in machine-readable form, and the raw logs of every run;
- **this article in full** — next to the results it refers to;
- links to the source images;
- a short README: what this is, how to run it, what you get.

**Why the article is there too.** The repository is a standalone entry point: people arrive here from search, fork from here, carry a copy to a machine with no internet. A repository where you cannot read the procedure without opening a browser and finding the right page works only halfway. There is still only one text: the repository holds a **snapshot of the article** with a date and a link to the original, and it is updated only by exporting from the original, not by hand. The snapshot is tied to the results folder of the same measurement run — so a year later it is clear which revision of the method produced those results.

**What we want to add next** — as new measurements become ready, with no deadlines:

- OpenJPEG as a third participant in the comparison — the CPU implementation everyone else is usually compared against, and it is open;
- results on other GPUs and at other bit depths, as they are obtained;
- a separate page describing exactly what changed between measurement runs: driver version, library version, codec version.

**How to use this.** The simplest way is to make your own copy of the repository (a fork) and run the measurements yourself: in a topic like this, someone else's results are worth less than your own. nvJPEG2000 is free and downloadable from the NVIDIA site. The fvJPEG2000 codec is run as follows:

- **speed** is reproduced on the demo version of the SDK — it is freely downloadable, the link is in the repository;
- **the quality check** is also reproduced on the demo version: as the PSNR reference the script takes the frame after a lossless round trip on the same build, as described in [section 10](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#10-quality-control), so the watermark does not enter the calculation;
- **a build without the watermark** is only needed by those who want to compare the decoded frame directly with the source file. It is provided on request — [write to us](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#contact-form), and we will send it.

The license on the script and the benchmark harness is permissive — the only expected form of participation here is a fork. The SDK libraries come under their own license, which is stated separately.

Remarks on the procedure go to the repository's issues section: an error in the method is more useful found before the next numbers are published than after.

## 16. What remains unverified

The list is kept in the open, because it is part of the method: the reader must see where a conclusion is backed by measurement and where by reasoning. Five items out of eight are closed by measurement; three remain.

**Closed.**

1. **Each decoder read the file of its own encoder.** This was the main threat to the conclusion: files of the same size are not necessarily of the same internal complexity, and a comparison of decoders could in fact turn out to be a comparison of what the encoders produced. Cross-decoding was carried out across all eight combinations of conditions: nowhere did the difference exceed one percent, and in two cases it is zero. The conclusion about the decoders held.
2. **Quality control across all eight combinations of conditions.** Done, the results are in [section 10](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#10-quality-control): with lossless compression — an exact match for both codecs; with lossy compression — a PSNR difference within three tenths of a decibel.
3. **The matching Q value.** What was checked is what the item was created for: whether this is a trace of the search procedure itself. The search was run from two different starting intervals and at three quality levels: the values found barely depend on the choice of interval, that is, the procedure adds nothing of its own. The scales of the two codecs are very close but do not coincide: between two frames the equivalents found differ by 0.07–0.12. We did not establish the exact correspondence of the scales, that is a separate task. Details in [section 3.3](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#33-we-compare-at-the-same-compressed-file-size).
4. **Reference points for chroma subsampling.** Measured, [section 9](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#9-chroma-subsampling-reference-points-for-fvjpeg2000).
5. **The speed of PCRD mode when quantization is set.** Measured in a separate run, results in [section 11](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#11-pcrd-mode-fixed-file-size-and-encoding-speed). At one and the same file size PCRD alone slows encoding down by 1.6 to 1.8 times in single image mode and by 2.0 to 2.8 times at the best combination of threads and batch; a well chosen base quality narrows the gap to 1.3 to 1.8 times and at the same time gives a better PSNR.

**Remaining.**

1. **The decoder's output format.** The nvJPEG2000 benchmark harness leaves the result as separate planes. If the fvJPEG2000 decoder assembles them into interleaved RGB inside the measured interval, that is work done by only one side. The stage breakdown showed that the inverse transforms — MCT and the level shift — take about five percent of the time in the fvJPEG2000 decoder. That is less than the gap between the codecs, so it does not affect the conclusion, but for an exact comparison the correction is worth keeping in mind.
2. **Why one point has two stable states.** nvJPEG2000 decoding, 2K lossy, 8×1 gives now 309 frames per second, now 539, and the state is decided when the program starts and holds for the whole run. What is known is that the slow state spends 45% more CPU time per frame while the GPU runs at the same clock and the same temperature. So it is the CPU side, not the card. What exactly slows it down — thread placement across the cores, the state of the scheduler, or something else — we did not establish. This is the only cell in the article it applies to; the other twenty-three nvJPEG2000 decoding points repeat to within a couple of percent.
3. **Profiling of the nvJPEG2000 encoder.** The conclusion that the encoder gains almost nothing from multithreading is drawn from external signs: from the measurements themselves (1.035x from eight threads), from a separate test with image copying to the GPU switched off, from the absence of a batch interface in the header file, and from the design of the NVIDIA samples. All the signs agree, but there is still no direct confirmation from a profiler. The same goes for where Tier-2 runs in the nvJPEG2000 encoder: the NVIDIA documentation names the CPU stage only for the decoder, and about the encoder it says only that both the GPU and the CPU are used.

## 17. What comes next

This article is a first step, not a conclusion. Below is what is planned next: first the measurements, then the place where all of it lives permanently.

**Upcoming measurements.**

| Topic | What it gives |
|---|---|
| 12 and 16 bit, monochrome | this is exactly where medical and satellite imaging live |
| Other cards | RTX 5090, professional and server cards |
| Jetson | the same codec on an embedded platform |
| 8K and multi-tile frames | where a frame no longer fits into memory as a whole |

The first two topics are already clear in their setup and will most likely become separate articles. At 12 and 16 bits it is not only the data volume that changes but the material itself: medical images and satellite frames are built differently from photographic scenes. The results of this series cannot be carried over to them — they were not part of the measurements. For Jetson a draft is already written — there the main quantity is not speed but energy per frame, and results from a desktop card do not carry over, not even as ratios.

**Open project.** Everything needed to reproduce this is in the `jpeg2000-benchmark` repository — it is described in [section 15](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#15-open-project-on-github). New measurements from the list above will go there as well, together with the conditions and dates.

## Rights to this material

**The text of the article** is under the CC BY-ND 4.0 license: it may be reprinted in full and quoted, including in commercial publications, with a link to the source; rewriting and translating — by agreement with us, and we usually do not object. The reason for the restriction is simple: a rewritten description of the procedure circulating under our name harms both the reader and the measurements themselves.

**The measurement results and tables** are under the CC BY 4.0 license, without that restriction: they may be carried over into your own materials, reassembled and used for further calculations. If you changed something, say what exactly.

The source link in both cases: Fastvideo, `<article address>`, measurements of `<date>`. Please state the measurement conditions next to the results: without them the result is not reproducible, and a result that has outlived its conditions is worse than no result at all.

Neither of these licenses applies to the images.

## Appendix. What is known about the nvJPEG2000 encoder from open sources

Four observations from open sources. The first is a direct quotation from the documentation, the other three are indirect; all of them are consistent with the measurement results.

**The NVIDIA documentation names the CPU stage only for the decoder.** About the decoder it says directly: Tier-2 runs on the CPU, all the other stages are offloaded to the GPU. About the encoder it says only that the library uses both the GPU and the CPU and that the compressed image is written to host memory; which part of the work goes to the CPU is not stated ([docs.nvidia.com](https://docs.nvidia.com/cuda/nvjpeg2000/introduction.html)).

**The NVIDIA sample set has a pipelined decoding sample and no pipelined encoding sample.** The `nvJPEG2000-Decoder-Pipelined` sample shows decoding through several CUDA streams. The standard encoder sample processes frames strictly one after another: one CUDA stream, one encoder state, synchronization after every frame.

**The library interface has no function that takes an array of images.** Neither for encoding nor for decoding: only `nvjpeg2kEncode` and `nvjpeg2kDecodeImage`, for one frame. Checked against the header file, not the documentation.

**In NVIDIA's own samples the decoder gets noticeably more attention than the encoder.** The official `CUDALibrarySamples` set for nvJPEG2000 contains three decoding samples — a plain one, a pipelined one (`nvJPEG2000-Decoder-Pipelined`) and partial tile decoding — and one encoding sample, the plain one ([github.com/NVIDIA/CUDALibrarySamples](https://github.com/NVIDIA/CUDALibrarySamples/tree/master/nvJPEG2000)). There is no pipelined sample for the encoder. This is indirect evidence, but it agrees with everything else the measurements show.

It is worth noting separately which results NVIDIA publishes itself. Public materials contain measurements **for decoding** — for example, in the blog post about the nvImageCodec library, which discusses accelerated decoding of medical images: it gives the GPU models, the image sizes, and a comparison with a CPU implementation ([developer.nvidia.com](https://developer.nvidia.com/blog/advancing-medical-image-decoding-with-gpu-accelerated-nvimagecodec/)). We were unable to find published results for JPEG2000 encoding — neither in the library documentation nor in the blog. This is an observation, not a reproach: they may simply never have been published.

**For decoding, our nvJPEG2000 figures are higher than the figures NVIDIA publishes itself.** The nvJPEG2000 blog post of 24 June 2021 carries a chart of decoding speed for a 1920 × 1080 8-bit 4:4:4 image, lossless, 5-3 wavelet — the same conditions as in [section 7](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#7-decoding). From the chart, an RTX A6000 gives 75 images per second at batch size 1 and 166 at batch size 20; an A100 gives 64 and 162, a T4 gives 41 and 48 ([developer.nvidia.com](https://developer.nvidia.com/blog/accelerating-jpeg-2000-decoding-for-digital-pathology-and-satellite-images-using-the-nvjpeg2000-library/)). The text of the post says 232 images per second at batch size 20, which disagrees with the chart under that same paragraph; we take the chart. On our RTX 4090 the same decoder gives 237 images per second for a single image and 438 at the best combination of threads and batch — against 75 and 166 on NVIDIA's A6000, three times more for a single image and 2.6 times more in batch.

NVIDIA's figures and ours are taken at different measurement boundaries: theirs excludes the parsing of the compressed image on the CPU, ours includes it ([section 4.2.1](https://www.fastcompression.com/blog/fastvideo-vs-nvjpeg2000.htm#421-measurement-boundaries-in-the-nvidia-samples)). No other published measurements of this library exist, so we quote these — with the caveat that they understate the gap rather than overstate it.
