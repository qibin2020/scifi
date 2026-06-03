---
Rank: 2
ForceModel: gemma4
ControlModel: gemma4
Skills: bilevel_run
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs/local_scratch:/srv/runs:rw
---

# Generate the geometry for my shipped bilevel config — locally

## Context

This task ships a ready bilevel config in your working directory:
`./run_local.yaml`. It is a tiny smoke scan (a single geometry, 2 events)
defining the run `run_local`, with outputs going to `/srv/runs`. I only want
the geometry XMLs and the ddsim manifest generated — no simulation, no SLURM,
everything runs locally.

## Todo

Use the `bilevel_run` skill's local workflow on the shipped config: run its
local one-shot runner in **generate** mode for run `run_local`. When it prints
`LOCAL_VERIFIED mode=generate run=run_local geometries=1`, call `done` with a
one-line summary. If it prints `LOCAL_FAIL`, fix what it names and rerun.

## Expect

- The runner printed `LOCAL_VERIFIED mode=generate run=run_local geometries=1`.
- `/srv/runs/run_local/sim_outputs/manifest.json` exists.
- `/srv/runs/run_local/run0000.xml` exists.
