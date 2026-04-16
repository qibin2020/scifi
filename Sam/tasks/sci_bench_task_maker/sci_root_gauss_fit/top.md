---
Rank: 2
Timeout: 1800
BashTime: -1
NoMemory: on
---

# Fit a Gaussian with ROOT

## Context

In a ROOT-enabled environment, sample 10000 random points from a Gaussian with
mean=2.5 and sigma=0.7, fill a `TH1F` histogram, fit it with the built-in
`gaus` function, and save the fit parameters to JSON plus a plot to PNG.

You can either reuse the env from `sci_root_install` (if it is still in the
task directory) or create a new one. Either way, set `BashTime: -1` since the
ROOT install is slow.

## Todo

1. Ensure ROOT is available in `./env` (`micromamba run -n work python -c "import ROOT"` should succeed). If not, create the env: `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.11 root -y`
2. Write `gauss_fit.py`:
   - `import ROOT, json`
   - Create a `TH1F("h", "Gaussian", 100, -1, 6)`
   - In a loop, fill it with `ROOT.gRandom.Gaus(2.5, 0.7)` 10000 times (use a fixed `ROOT.gRandom.SetSeed(1234)`)
   - Fit: `h.Fit("gaus", "Q")`  (Q = quiet)
   - Extract the fitted constant, mean, sigma via `h.GetFunction("gaus").GetParameter(0/1/2)`
   - Save them to `fit_params.json` as `{"const": ..., "mean": ..., "sigma": ...}`
   - Draw the histogram + fit and save to `fit.png` via a `TCanvas` and `c.SaveAs("fit.png")`
3. Run: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python gauss_fit.py`

## Expect

- `gauss_fit.py` exists
- `fit_params.json` exists with keys `const`, `mean`, `sigma`; mean is in [2.4, 2.6]; sigma is in [0.6, 0.8]
- `fit.png` exists, valid PNG, > 1 KB
