---
Rank: 2
BashTime: -1
Skills: common_env
CommonStorage: rw
GPU: local

NoMemory: on
---

# CaloVQ Pipeline — VQ-VAE Calorimeter Shower Generation
## Context

CaloVQ (arXiv:2405.06605) generates fast calorimeter showers using VQ-VAE + GPT. Repo: https://github.com/qibin2020/calo-VQ.git. Pre-trained checkpoints in `models/`.

Geant4 truth for DS2: `https://zenodo.org/records/6366271/files/dataset_2_2.hdf5?download=1` (1.3 GB).

Generation: `python gen-tools.py --out gen_ds2.h5 --model models/ds2-model-final_new/2023-08-10T16-46-18_2_2_64_5h_r1 --type 2 --nevts 1000 --batch-size 100`

Use `--gpus 1` (not `--gpus 0,`). Python 3.10, pytorch-cuda=12.4, pip<24.1, numpy<2.0, setuptools<68, PL 1.6.5. Fix `running_sanity_check` → `sanity_checking` in 3 source files.

## Todo

1. Clone calo-VQ, set up shared env named `calovq` (check `/mnt/sci_envs/calovq` first — reuse if exists) with common_env, fix PL source patches.
2. Write a generation script, run it on the local GPU.
3. Download Geant4 truth from Zenodo.
4. Write a comparison script: 6-panel dashboard (incident energy, total energy, Etot/Einc, scatter, longitudinal profile, sparsity) overlaying generated vs truth. Save as `summary_dashboard.png`.

## Expect

- `gen_ds2.h5` exists with keys `showers` (1000, 6480) and `incident_energies` (1000, 1)
- `dataset_2_2.hdf5` exists, >1 GB
- `summary_dashboard.png` exists, >50 KB
- Generation completed successfully on GPU
