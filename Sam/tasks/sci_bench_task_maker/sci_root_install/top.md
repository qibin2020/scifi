---
Rank: 2
Timeout: 1800
BashTime: -1
NoMemory: on
---

# Install ROOT via conda-forge

## Context

Install CERN ROOT into a writable micromamba environment from conda-forge, then
import it from Python and capture the version string. ROOT install is slow
(~5-10 min), be patient and set `BashTime: -1` so the long-running install does
not get cut off.

## Todo

1. `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.11 root -y`
   (this is the slow step; the install pulls in ~1 GB of dependencies)
2. Verify the install: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python -c "import ROOT; print(ROOT.gROOT.GetVersion())"`
3. Capture the version string to `root_version.txt` (the file should contain a single line like `6.32.04`).

## Expect

- `env/` directory exists with a `work` env containing ROOT
- `root_version.txt` exists, contains a version string matching `^6\.\d+`
