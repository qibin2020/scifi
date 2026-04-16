---
Rank: 3
BashTime: -1
Skills: NERSC_slurm
NoMemory: on
---

# SLURM MNIST GPU

## Todo
Submit a SLURM 1-GPU job (account m2616, 30 min) that creates a torch env and trains a small AlexNet on MNIST for ~500 batches. Wait for completion. Verify model.pt and train.log were produced.

## Expect
- slurm_jobid.txt with the id
- model.pt > 100 KB
- train.log exists
