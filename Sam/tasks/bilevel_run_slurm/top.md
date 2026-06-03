---
Rank: 3
ForceModel: gemma4
ControlModel: gemma4
Skills: bilevel_run
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# Run my shipped bilevel optimization on SLURM

## Context

This task ships a ready bilevel config in your working directory:
`./run_slurm.yaml`. It is a tiny full optimization — **2 geometries**, 2 events
each — defining the run `run_slurm`, so it schedules and finishes fast
(~3 minutes). I want the full optimization (simulation + inner loop) run on
SLURM and the outputs verified. There is no `sbatch` here; SLURM is handled
entirely by the `bilevel_run` skill's runner. Outputs land under
`/srv/runs/run_slurm/`.

## Todo

Use the `bilevel_run` skill's full-runner on the shipped config for run
`run_slurm` (2 geometries). When it prints `RUN_VERIFIED run=run_slurm roots=2`
with a job id, call `done` with a one-line summary that includes the job id.
If it prints `RUN_FAIL`, report what it names.

## Expect

- The run-skill's full-runner printed `RUN_VERIFIED run=run_slurm roots=2`
  with a job id.
- `/srv/runs/run_slurm/results/summary.csv` exists.
