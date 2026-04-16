---
Rank: 4
BashTime: -1
Skills: NERSC_slurm
NoMemory: on
---

# SLURM train + local eval

## Todo
Submit MNIST training as a 1-GPU SLURM job (m2616). When done, load model.pt locally and run inference on the test set. Save eval.json (accuracy > 0.90) and notes.md.

## Expect
- slurm_jobid.txt
- model.pt > 100 KB
- eval.json accuracy > 0.90
- notes.md
