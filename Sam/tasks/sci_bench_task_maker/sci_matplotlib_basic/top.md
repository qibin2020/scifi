---
Rank: 1
Timeout: 600
NoMemory: on
---

# Plot a sine wave with matplotlib

## Context

Create a writable Python environment, install matplotlib + numpy, write a small
script that plots `sin(x)` for `x in [0, 2*pi]`, and save the figure to `out.png`.
The system overlay is read-only — you must put the env inside the task directory
(use `MAMBA_ROOT_PREFIX=./env`).

## Todo

1. `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.12 -y`
2. `MAMBA_ROOT_PREFIX=./env micromamba run -n work pip install matplotlib numpy`
3. Write `plot.py` that uses numpy to make 200 points over `[0, 2*pi]`, plots
   `sin(x)`, labels axes, saves to `out.png` at DPI 100, figsize 5x4 inches.
4. Run it: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python plot.py`
5. Verify `out.png` exists and is at least 1 KB.

## Expect

- `plot.py` exists and uses matplotlib (not a copied or downloaded file)
- `out.png` exists, is a valid PNG (file starts with the PNG magic bytes), file size > 1 KB
