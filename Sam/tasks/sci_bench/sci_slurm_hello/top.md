---
Rank: 1
ForceModel: gemma4
SlurmTool: on
BashTime: -1
Skills: NERSC_slurm
NoMemory: on
---

# SLURM hello

## Todo
There is no `sbatch` here — use the SLURM tools (see the NERSC_slurm skill).
1. `slurm_submit` a tiny CPU job: command `hostname; date; echo OK`,
   `time_minutes` 5, `cpus` 2, `name` "hello". Save the returned job id to
   `slurm_jobid.txt`.
2. Poll `slurm_status` with that id (sleep 30 in bash between calls) until it
   returns `DONE <exit>`.
3. On `DONE 0`, call done.

## Expect
- `slurm_jobid.txt` contains a numeric job id.
- `slurm_status` returned `DONE 0` for that job.
