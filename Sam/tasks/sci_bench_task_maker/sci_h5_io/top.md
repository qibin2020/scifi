---
Rank: 1
Timeout: 600
NoMemory: on
---

# HDF5 read/write

## Context

Create a Python env with h5py + numpy. Write an HDF5 file `data.h5` containing
two datasets: a `(100, 3)` float array of random numbers (seed 0) and a
`(100,)` array of UTF-8 string labels. Read the file back, verify the shapes
match, and write a small `verify.json` summary.

## Todo

1. `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.12 h5py numpy -y`
2. Write `h5_roundtrip.py`:
   - `np.random.seed(0)`
   - `arr = np.random.randn(100, 3).astype("float32")`
   - `labels = np.array([f"row_{i}" for i in range(100)], dtype="S10")`
   - Write both to `data.h5` using h5py (datasets named `arr` and `labels`)
   - Re-open and read back; assert shapes are `(100, 3)` and `(100,)`
   - Write `verify.json` with `{"arr_shape": [100, 3], "labels_shape": [100], "ok": true}`
3. Run: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python h5_roundtrip.py`

## Expect

- `data.h5` exists, file size > 1 KB
- `verify.json` exists with `"ok": true`
