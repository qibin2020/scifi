---
Rank: 3
Timeout: 3600
BashTime: -1
Skills: NERSC_slurm
NoMemory: on
---

# Submit MNIST training to a SLURM GPU node

## Context

Use the `NERSC_slurm_maker` skill to generate a 1-GPU SLURM script that creates
a python env, installs torch+torchvision, and runs a short MNIST AlexNet
training (same recipe as `sci_mnist_train_local`). Submit, wait, and verify the
checkpoint is produced.

## Todo

1. Write `train.py` with the small AlexNet MNIST training loop (~500 batches, batch size 64, save `model.pt`, write `train.log`).
2. Use the `NERSC_slurm_maker` skill to generate a 1-GPU `shared` SLURM script with:
   - Account: `m2616`
   - 1 GPU, 32 CPUs
   - Wall time: 30 minutes
   - Command: micromamba env setup + `python train.py` (the script body should set `MAMBA_ROOT_PREFIX=./env`, create the env, install torch torchvision, and run train.py)
3. `sbatch` the script. Save the job id.
4. Poll until the job finishes.
5. Verify `model.pt` and `train.log` exist in the task directory.

## Expect

- The SLURM script exists in the task directory
- `slurm_jobid.txt` with the job id
- `model.pt` > 100 KB
- `train.log` exists with training progress
