---
Rank: 3
ForceModel: gemma4
ControlModel: gemma4
Campaign: claude
Skills: bilevel_config, bilevel_run, bilevel_digi, bilevel_ana
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# SCEPCal optimization, epoch 2: chase the rising edges, refine the readout

## Context

This is epoch 2 of my optimization campaign for the SCEPCal crystal
calorimeter and its readout. Epoch 1 found the score still rising at the high
edge of both scanned axes (best width 10 cm, front 18 cm), with the width
nearly saturated — so this epoch interleaves the previous grid and pushes
past both edges, without repeating any geometry already simulated.

- Crystals **7, 9, 11, and 13 cm wide** × **12, 16, 20, and 24 cm deep at
  the front** (16 geometries).
- **Projective offset fixed at 10 cm**, **rear length fixed at 15 cm**.
- **300 electrons at 1 GeV** per geometry.
- Tune the **cluster radius over 20 to 150 mm (15-point grid)** and the
  **per-hit energy threshold over 0 to 1.0 GeV (5-point grid)**, scoring
  `snr_energy`.
- After the run is verified, scan the readout with the `bilevel_digi` skill,
  this time with a refined sampling grid around the cheap-power frontier:
  pass `--sa 0.005,0.0075,0.01,0.015,0.02 --bits 6,8,10,12` (keep its other
  defaults).

Call the run `cl2` (the skills place the config and outputs in this run's
campaign area automatically; SLURM is handled by the `bilevel_run` skill's
runner). I want the same short report as before: best geometry and whether to
trust it, the readout operating point, and what each scanned parameter does.

## Todo

Use the `bilevel_config` skill to build the validated configuration for the
scan I described, then the `bilevel_run` skill's full-runner to run and
verify it on SLURM (16 geometries), then the `bilevel_digi` skill on run
`cl2` with the Sa/bits grid above, then the `bilevel_ana` skill on run `cl2`.
Each skill is one command with one status token. Write the report
`./analysis.md` with sections **Best point, Trends, Readout, Reliability,
Conclusion** — geometry numbers from the `bilevel_ana` digest, readout
numbers (the operating point and every `note:` line, copied) from the
`bilevel_digi` digest. Finish with `done`: the best geometry, its score, the
readout operating point, and the main caveat.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=16`.
- The full-runner printed `RUN_VERIFIED run=cl2 roots=16` with a job id.
- The readout scan printed `DIGI_VERIFIED run=cl2`.
- The digest printed `ANA_OK geometries=16`.
- `./analysis.md` exists with sections Best point, Trends, Readout,
  Reliability, and Conclusion; quotes the best score and the trend tag of
  each swept geometry parameter; quotes the readout operating point (Sa and
  N) with its s_err and power; states whether the cluster radius is pinned
  at a search bound; and copies every digest `note:` line.
