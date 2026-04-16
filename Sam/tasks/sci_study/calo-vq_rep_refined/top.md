---
Rank: 2
BashTime: -1
Skills: common_env, NERSC_slurm
CommonStorage: rw
GPU: slurm
Slurm: on
NoMemory: on
---

# CaloVQ Pipeline — VQ-VAE Calorimeter Shower Generation (Refined)

## Context

**CaloVQ** (arXiv:2405.06605) is a two-stage calorimeter shower simulation framework:
- **Step 1 (VQ-VAE)**: encodes calorimeter data into discrete codebook entries
- **Step 2 (Conditional GPT)**: autoregressively generates code sequences conditioned on incident energy
- **Generation**: GPT samples codes → frozen VQ decoder reconstructs showers → HDF5

Repo: https://github.com/qibin2020/calo-VQ.git. Pre-trained checkpoints in `models/`.

### Dataset 2 Detector Geometry

| Property | Value |
|----------|-------|
| Layers | 45 (along z, uniform spacing) |
| Radial bins per layer | 9 (cell size 4.65 mm) |
| Angular bins per layer | 16 (22.5 deg each) |
| Total voxels | 6480 (45 x 16 x 9) |
| Min readout threshold | 15.15 keV |

### HDF5 Format

```
showers:           float32, (N, 6480)  — voxel energies in MeV
incident_energies: float32, (N, 1)     — incident electron energy in MeV
```
Reshape: `data.reshape(-1, 45, 16, 9)` → `(events, layer, angular, radial)`.

### Environment Pinning

| Package | Constraint | Reason |
|---------|-----------|--------|
| Python | 3.10 | Upstream 3.8.5 too old for CUDA 12.x |
| pytorch-cuda | 12.4 | Host CUDA 12.9 driver |
| pip | <24.1 | Newer rejects PL 1.6.5 metadata |
| numpy | <2.0 | 2.0 removed `np.Inf` |
| setuptools | <68 | Newer breaks PL 1.6.5 |
| pytorch-lightning | 1.6.5 | Required by calo-VQ |
| torchmetrics | 0.6.0 | Compatible with PL 1.6.5 |
| omegaconf | 2.1.1 | Required by calo-VQ |
| test-tube | >=0.7.5 | Required |
| einops | 0.3.0 | Required |

**Source patches**: `running_sanity_check` → `sanity_checking` in `calo_ldm/models/vqvae.py`, `calo_ldm/models/gpt.py`, `calo_ldm/callbacks.py`.

**GPU**: `--gpus 1` (NOT `--gpus 0,` — triggers DDP conflict).

### Generation Command

```bash
python gen-tools.py --out gen_ds2.h5 \
    --model models/ds2-model-final_new/2023-08-10T16-46-18_2_2_64_5h_r1 \
    --type 2 --nevts 1000 --batch-size 100
```

### Geant4 Truth Data

```bash
curl -L -o dataset_2_2.hdf5 "https://zenodo.org/records/6366271/files/dataset_2_2.hdf5?download=1"
```
1.3 GB, 100k Geant4-simulated electron showers, same HDF5 format.

### SLURM Job Spec

Use the NERSC_slurm skill. The generation needs:
- 1 GPU, shared QOS (`-C gpu -q shared -n 1 -c 32 --gpus-per-task=1`)
- Wall time: 10 minutes
- `export SLURM_CPU_BIND="cores"`
- Activate the shared env inside the job script

### Dashboard Specification

`plot_comparison.py` → `summary_dashboard.png`, 2x3 grid (figsize 18x10):

**Style**: blue filled = CaloVQ, orange step outline = Geant4. `density=True`. Cap truth at 10k events.

| Panel | Position | X-axis | Content |
|-------|----------|--------|---------|
| (a) | top-left | log `$E_{inc}$` [MeV] | Incident energy histograms |
| (b) | top-center | log `$E_{tot}$` [MeV] | Total deposited energy histograms |
| (c) | top-right | linear `$E_{tot}/E_{inc}$` | Energy ratio histograms, vline at 1.0 |
| (d) | bottom-left | log-log | Etot vs Einc scatter, y=x line |
| (e) | bottom-center | layer index | Longitudinal profile, mean ± std bands |
| (f) | bottom-right | layer index | Mean sparsity per layer, ylim 0-1 |

Title: `CaloVQ vs Geant4 — DS2 Summary` (fontsize 16, bold).

## Todo

1. **Create shared env** `calovq` via common_env: micromamba for system deps, pip for PL stack (see table).

2. **Clone repo**:
   ```bash
   git clone https://github.com/qibin2020/calo-VQ.git repo
   cd repo && pip install -e . && cd ..
   ```

3. **Patch PL**:
   ```bash
   cd repo && sed -i 's/running_sanity_check/sanity_checking/g' \
       calo_ldm/models/vqvae.py calo_ldm/models/gpt.py calo_ldm/callbacks.py
   cd ..
   ```

4. **Write `run_generate.sh`**: activates env, sets `CUDA_VISIBLE_DEVICES`, runs gen-tools.py, verifies output.

5. **Submit via NERSC_slurm**: 1 GPU shared, 10 min wall. Wait for completion.

6. **Verify generation**:
   ```bash
   python -c "import h5py; f=h5py.File('gen_ds2.h5','r'); print('showers:', f['showers'].shape)"
   ```

7. **Download Geant4 truth** via curl.

8. **Write `plot_comparison.py`** per the dashboard spec above.

9. **Run plotting** (CPU, no SLURM needed).

10. **Verify**: `ls -lh summary_dashboard.png`

## Expect

- `repo/` exists with `gen-tools.py` and `models/`
- `gen_ds2.h5` exists, >10 KB, keys `showers` (1000, 6480) and `incident_energies` (1000, 1)
- `dataset_2_2.hdf5` exists, >1 GB, keys `showers` and `incident_energies`
- `summary_dashboard.png` exists, >50 KB, is a valid PNG
- Generation ran via SLURM (`sbatch` was called, job script exists)
- `plot_comparison.py` runs with exit code 0
- Dashboard has 6 panels with both generated and truth data visible
