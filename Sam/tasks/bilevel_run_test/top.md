---
Rank: 3
ForceModel: gemma4
Skills: bilevel_run
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:ro
---

# Run a tiny bilevel optimization via SLURM using the bilevel_run skill

## Context

Run the bilevel optimization for config `/srv/scif_configs/opt_test.yaml` as run
name `opt_test` on SLURM. It is a tiny 2-geometry test, so it schedules and
finishes fast (~3 min). Use the `bilevel_run` skill: run its helper to get the
command string, then `slurm_submit` it — do NOT hand-build the command. There is
no `sbatch`; use the `slurm_submit` / `slurm_status` tools. The SLURM job runs
inside the SciFi container with the bilevel project mapped to `/srv`, so the
submitted command uses `/srv/...` paths. The helper itself lives at
`/srv/skills/bilevel_run/run_cmd.py` in your bash. The run name MUST match a run
block in the config — `opt_test.yaml` defines the run `opt_test`, so use exactly
`opt_test`. Outputs appear under `/srv/runs/opt_test/` (mounted read-only here).

## Todo

1. Get the full-mode command line from the skill helper (run as ONE line, no
   backslash-newline):
   ```bash
   python3 /srv/skills/bilevel_run/run_cmd.py --config /srv/scif_configs/opt_test.yaml --run opt_test --mode full --parallel 4
   ```
   It prints ONE line — that is the command to submit.

2. `slurm_submit` with `command` = that exact printed line, `time_minutes` 30,
   `cpus` 4, `name` "opt_test". Use a SMALL cpus (4) so it schedules instantly.
   Remember the returned job id.

3. Poll `slurm_status` with that job id, running `sleep 30` in bash between
   calls, until it returns `DONE <exit>`.

4. After `DONE 0`, verify the outputs with bash (clean tokens):
   ```bash
   D=/srv/runs/opt_test
   echo "roots=$(ls $D/sim_outputs/*.root 2>/dev/null | wc -l)"
   test -f $D/results/summary.csv && echo SUMMARY_OK || echo SUMMARY_MISSING
   ```
   When `roots=2` and `SUMMARY_OK`, call `done` (include the job id). Otherwise
   report what is missing.

## Expect

- `slurm_status` returned `DONE 0` for the submitted job.
- 2 ROOT files exist under `/srv/runs/opt_test/sim_outputs/`.
- `/srv/runs/opt_test/results/summary.csv` exists.
