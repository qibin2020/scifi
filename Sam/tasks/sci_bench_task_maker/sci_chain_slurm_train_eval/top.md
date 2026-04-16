---
Rank: 4
Timeout: 5400
BashTime: -1
Skills: NERSC_slurm
NoMemory: on
---

# SLURM-trained MNIST + local eval

## Context

Mix SLURM batch training with interactive evaluation. Submit a 1-GPU SLURM job
to train an MNIST classifier (account `m2616`, 30 min). After it finishes, load
the resulting checkpoint locally inside the container and run inference on the
test set. Save evaluation metrics to `eval.json`.

## Todo

1. Write `train.py` (small AlexNet, save `model.pt`, write `train.log`).
2. Use the `NERSC_slurm_maker` skill to generate a 1-GPU SLURM script (m2616, 30 min) that creates the env and runs `train.py`.
3. `sbatch` it. Save the job id.
4. Poll `squeue` until the job finishes.
5. Verify `model.pt` exists.
6. Locally (inside this container, not via SLURM): create a torch env if you do not already have one, write `evaluate.py` that loads `model.pt` and runs on the MNIST test set, save `eval.json` with `{"accuracy": ..., "n_test": 10000}`.
7. Write `notes.md` summarizing the workflow: SLURM job id, train log path, checkpoint path, eval accuracy, the local env you used.

## Expect

- `slurm_jobid.txt` with the job id
- `model.pt` > 100 KB
- `eval.json` with `accuracy` > 0.90
- `notes.md` exists with all five items
