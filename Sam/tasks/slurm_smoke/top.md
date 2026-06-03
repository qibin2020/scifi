---
Rank: 3
ForceModel: gemma4
SlurmTool: on
BashTime: -1
NoMemory: on
---

# SLURM broker smoke test

## Todo

Verify the SLURM tools work end to end by running one trivial job. There is no
`sbatch` in this shell — use the `slurm_submit` and `slurm_status` tools.

1. Submit a tiny job:
   - `slurm_submit` with command `hostname; date; echo BROKER_OK`,
     `time_minutes` 5, `cpus` 2, `gpus` 0, `name` "bksmoke".
   - It returns `SLURM_SUBMITTED <jobid>`. Remember that job id.

2. Wait for it to finish. Call `slurm_status` with the job id; between calls run
   `sleep 30` in bash. Repeat until it returns `DONE <exit>` (or `FAILED`).

3. When `slurm_status` returns `DONE 0`, call `done` with a one-line summary
   including the job id. If it returns `FAILED`, report the exit code.

## Expect

- `slurm_submit` returned `SLURM_SUBMITTED` followed by a numeric job id.
- `slurm_status` eventually returned `DONE 0` for that job id.
