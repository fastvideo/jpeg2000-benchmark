# Third-party software

This repository contains no third-party binaries. Everything listed below is
obtained by the user directly from its vendor and is governed by that vendor's
own licence terms.

| Component            | Where it comes from        | Terms                    |
|----------------------|----------------------------|--------------------------|
| Fastvideo SDK        | fastcompression.com        | Fastvideo licence        |
| nvJPEG2000           | NVIDIA, separate download  | NVIDIA licence           |
| CUDA Toolkit, driver | NVIDIA                     | NVIDIA licence           |

**Fastvideo SDK.** The speed figures can be reproduced with the freely
downloadable demo build. Quality verification requires a build without the
watermark: the watermark is applied before encoding, so on the demo build a
comparison against the original is meaningless. That build is provided on
request.

**nvJPEG2000** does not ship as part of the CUDA Toolkit. It is distributed
separately — downloaded as an archive from the NVIDIA site or installed as
the `nvidia-nvjpeg2k-cu12` package (on Jetson, `nvidia-nvjpeg2k-tegra-cu12`)
— and is not redistributed here. The CUDA Toolkit itself is still required:
the library runs on top of it. The measurement harness in this repository is
our own source code and is covered by `LICENSE`.

**Test images** are published on fastcompression.com and are referenced, not
redistributed here. They may be used for benchmarking and for reproducing
these results.

**Other JPEG2000 implementations** - Kakadu and Comprimato in particular - are
not measured here. We did not approach their vendors, and we do not interpret
their licence terms on their behalf. The procedure is open: anyone holding a
licence can run it and publish the result.
