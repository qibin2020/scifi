---
Rank: 2
BashTime: -1
NoMemory: on
Skills: common_env
---

# ROOT Gaussian histogram fit

## Context

Use the `root_env` skill to set up a ROOT environment. The skill handles
env discovery at `/mnt/sci_envs/` and installation if no env is found.

## Todo

1. Use the root_env skill to obtain a working ROOT environment
2. Write `gauss_fit.py` that samples 10000 points from N(2.5, 0.7) into a TH1F(100 bins, range -1 to 6), fits with `gaus`, saves fit parameters to `fit_params.json` and histogram plot to `fit.png`
3. Run the script in the ROOT environment

## Expect

- `fit_params.json` exists with keys `const`, `mean`, `sigma`; mean in [2.4, 2.6]; sigma in [0.6, 0.8]
- `fit.png` exists, valid PNG, > 1 KB
