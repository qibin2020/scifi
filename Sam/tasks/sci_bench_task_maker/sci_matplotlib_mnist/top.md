---
Rank: 2
Timeout: 900
BashTime: -1
NoMemory: on
---

# MNIST digit grid

## Context

Create a Python env with matplotlib + numpy + scikit-learn (for the openml MNIST
fetch) or torchvision. Download a small subset of MNIST and produce a 4x4 grid of
sample digits as `mnist_grid.png`. The MNIST download is small (~11 MB) and is
cached in the env so subsequent runs are fast.

## Todo

1. Create env: `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.12 -y`
2. Install: `MAMBA_ROOT_PREFIX=./env micromamba run -n work pip install matplotlib numpy scikit-learn`
3. Write `make_grid.py`:
   - Use `sklearn.datasets.fetch_openml('mnist_784', version=1, as_frame=False)` (cache to `./mnist_cache`)
   - Take the first 16 samples
   - Reshape each to 28x28
   - Plot a 4x4 grid via `matplotlib.pyplot.subplots(4, 4)` showing each digit in grayscale
   - Save to `mnist_grid.png` at DPI 100
4. Run: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python make_grid.py`

## Expect

- `make_grid.py` exists
- `mnist_grid.png` exists, valid PNG, > 5 KB (a 4x4 image grid is non-trivial)
