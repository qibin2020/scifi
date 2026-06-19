---
Rank: 3
ForceModel: gemma4
ControlModel: gemma4
Skills: bilevel_config, bilevel_run, bilevel_ana
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# Tiny local-execution check

## Context

A minimal end-to-end check: simulate two crystal geometries and analyze.

- Crystals **5 and 7 cm wide**, **8 cm deep at the front**, projective offset
  10 cm, rear 15 cm.
- **10 electrons at 1 GeV** per geometry.
- Tune the **cluster radius over 20 to 150 mm (15-point grid)** and the
  **energy threshold over 0 to 1 GeV (5-point grid)**, scoring `snr_energy`.

Call the run `locsmoke`.

## Todo

Use the `bilevel_config` skill to build the validated configuration, then the
`bilevel_run` skill's full-runner (2 geometries), then the `bilevel_ana` skill
on run `locsmoke`. Each skill is one command with one status token. Finish
with `done`: the best geometry, its score, and the job id.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=2`.
- The full-runner printed `RUN_VERIFIED run=locsmoke roots=2` with a job id.
- The digest printed `ANA_OK geometries=2`.
