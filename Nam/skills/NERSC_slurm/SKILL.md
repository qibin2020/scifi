---
name: NERSC_slurm
description: Run work on the NERSC Perlmutter batch system via the slurm_submit / slurm_status tools (the agent has no sbatch — submission is brokered on the host)
---

There is no `sbatch`/`squeue` in this container. SLURM is exposed as two tools,
backed by a host-side broker that handles all NERSC specifics (account,
`-C cpu/gpu`, QOS, the 32-CPUs-per-GPU rule, auth). You only state *what* to run
and *how big*.

## Tools

- `slurm_submit(command, time_minutes, cpus, gpus, name)` → `SLURM_SUBMITTED <id>`
  (or `SLURM_ERR <msg>`). The `command` runs on a compute node; if the task is
  configured with a container wrapper, it runs inside that container with the
  project mapped to `/srv` (so use `/srv/...` paths). Submit long work here —
  never run it inline in bash.
- `slurm_status(job_id)` → `PENDING` | `RUNNING` | `DONE <exit>` | `FAILED <exit>`
  | `UNKNOWN`. Poll it, sleeping ~30s between calls via bash, until `DONE`.

## Resources (high-level only)

- `cpus`: number of CPU cores (CPU job when `gpus` is 0).
- `gpus`: number of GPUs (0 = CPU job). The broker picks the right queue and the
  mandatory 32 CPUs/GPU automatically.
- `time_minutes`: wall-time budget.
- `name`: a short job name.

## Pattern

1. `slurm_submit(...)` → save the job id.
2. Loop: `slurm_status(id)`; if not `DONE`, `sleep 30` in bash and check again.
3. On `DONE 0`, verify the job's outputs with bash, then call `done`. On
   `FAILED`, report the exit code.

Do not try to write SLURM scripts, set `--account`, `-C`, `-q`, or `-c 32`, or
call `sbatch` — none of that is available or needed here.
