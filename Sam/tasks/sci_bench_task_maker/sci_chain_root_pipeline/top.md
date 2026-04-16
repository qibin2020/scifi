---
Rank: 3
Timeout: 2400
BashTime: -1
NoMemory: on
---

# Full ROOT pipeline (install -> sample -> fit -> plot -> report)

## Context

End-to-end ROOT chained task. Install ROOT via conda-forge, sample a Gaussian,
fit it with `gaus`, save the fit + plot + a markdown report.

## Todo

1. `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.11 root -y` (slow, ~10 min)
2. Write `pipeline.py` that:
   - Sets `ROOT.gRandom.SetSeed(42)`
   - Samples 50000 points from N(5.0, 1.2) into a `TH1F("h", "Gaussian", 100, 0, 10)`
   - Fits with `gaus`
   - Writes `fit_params.json` with `const`, `mean`, `sigma`
   - Saves the histogram + fit overlay to `fit.png`
3. Run the pipeline
4. Write `report.md` (1 paragraph + the embedded image link `![fit](fit.png)`) summarizing the fit results

## Expect

- `fit_params.json` exists with `mean` in `[4.9, 5.1]` and `sigma` in `[1.1, 1.3]`
- `fit.png` exists, > 1 KB
- `report.md` exists, mentions the fit mean and sigma, and includes `![fit](fit.png)` or similar markdown link
