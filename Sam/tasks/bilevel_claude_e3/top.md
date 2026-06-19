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

# SCEPCal optimization, epoch 3: map the offset × rear-length plane

## Context

This is epoch 3 of my optimization campaign for the SCEPCal crystal
calorimeter and its readout. Epochs 1–2 bracketed the width and front-length
optimum (a plateau around width 11 cm, front 16 cm), so this epoch freezes
those two and characterizes the two geometry parameters not yet scanned:
the projective offset and the rear section length.

- **Width fixed at 11 cm**, **front length fixed at 16 cm**.
- **Projective offsets 2, 6, 10, and 14 cm** × **rear lengths 9, 13, 17,
  and 21 cm** (16 geometries).
- **300 electrons at 1 GeV** per geometry.
- Tune the **cluster radius over 20 to 150 mm (15-point grid)** and the
  **per-hit energy threshold over 0 to 1.0 GeV (5-point grid)**, scoring
  `snr_energy`.
- After the run is verified, scan the readout with the `bilevel_digi` skill
  using its **default grid** (this checks that the readout choice stays
  geometry-independent in the new region).

Call the run `cl3` (the skills place the config and outputs in this run's
campaign area automatically; SLURM is handled by the `bilevel_run` skill's
runner). I want the same short report as before: best geometry and whether to
trust it, the readout operating point, and what each scanned parameter does.

## Todo

Use the `bilevel_config` skill to build the validated configuration for the
scan I described, then the `bilevel_run` skill's full-runner to run and
verify it on SLURM (16 geometries), then the `bilevel_digi` skill on run
`cl3`, then the `bilevel_ana` skill on run `cl3`. Each skill is one command
with one status token. Write the report `./analysis.md` with sections **Best
point, Trends, Readout, Reliability, Conclusion** — geometry numbers from the
`bilevel_ana` digest, readout numbers (the operating point and every `note:`
line, copied) from the `bilevel_digi` digest. Finish with `done`: the best
geometry, its score, the readout operating point, and the main caveat.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=16`.
- The full-runner printed `RUN_VERIFIED run=cl3 roots=16` with a job id.
- The readout scan printed `DIGI_VERIFIED run=cl3`.
- The digest printed `ANA_OK geometries=16`.
- `./analysis.md` exists with sections Best point, Trends, Readout,
  Reliability, and Conclusion; quotes the best score and the trend tag of
  each swept geometry parameter (offset and rear length); quotes the readout
  operating point (Sa and N) with its s_err and power; states whether the
  cluster radius is pinned at a search bound; and copies every digest
  `note:` line.
