---
Rank: 3
ForceModel: gemma4
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:ro
---

# Submit a bilevel ddsim job via SLURM

## Context

Run a tiny bilevel ddsim (1 geometry, 2 events) on a compute node via SLURM, then
confirm it produced a ROOT file. There is no `sbatch` here — use the
`slurm_submit` / `slurm_status` tools. The job runs inside the SciFi container
automatically (the command is wrapped for you), with the project mapped to
`/srv`, so the command uses `/srv/...` paths. The ROOT output appears under
`/srv/runs/` (mounted read-only here so you can verify it).

## Todo

1. Submit the ddsim job:
   - `slurm_submit` with command
     `bilevel_opt --config /srv/scif_configs/smoke_slurm.yaml --stage outer --run-mode local --run agent_slurm_test`,
     `time_minutes` 30, `cpus` 4, `name` "bilevel_ddsim".
   - Remember the returned job id.

2. Poll `slurm_status` with that job id, running `sleep 30` in bash between
   calls, until it returns `DONE <exit>`.

3. After `DONE 0`, verify the ROOT output with bash (one clean token):
   ```bash
   test -s /srv/runs/agent_slurm_test/sim_outputs/run0000.root && echo SLURM_ROOT_OK || echo SLURM_ROOT_MISSING
   ```
   When you see `SLURM_ROOT_OK`, call `done` (include the job id). If the job
   `FAILED` or the ROOT is missing, report it.

## Expect

- `slurm_status` returned `DONE 0` for the submitted job.
- `/srv/runs/agent_slurm_test/sim_outputs/run0000.root` exists and is non-empty.
