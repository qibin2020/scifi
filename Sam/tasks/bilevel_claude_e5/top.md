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

# SCEPCal optimization, epoch 5: confirm the champions at high statistics

## Context

This is the final epoch of my optimization campaign for the SCEPCal crystal
calorimeter and its readout. Epochs 1–4 converged on a broad plateau (scores
0.868–0.874) around width 11–13 cm, front 16 cm, rear 15–21 cm, with the
offset flat. Per-epoch "best" points on a plateau are noise peaks, so this
epoch re-evaluates the leading candidates head-to-head with much higher
statistics instead of scanning new territory.

- Crystals **11 and 13 cm wide** × **rear lengths 15, 19, and 21 cm**
  (6 geometries — these cover the best points of epochs 2, 3, and 4).
- **Front length fixed at 16 cm**, **projective offset fixed at 10 cm**.
- **800 electrons at 1 GeV** per geometry (2.7× the statistics of the
  earlier epochs, same total cost).
- Tune the **cluster radius over 20 to 150 mm (15-point grid)** and the
  **per-hit energy threshold over 0 to 1.0 GeV (5-point grid)**, scoring
  `snr_energy`.
- After the run is verified, scan the readout with the `bilevel_digi` skill
  using its **default grid** (final confirmation of the operating point).

Call the run `cl5` (the skills place the config and outputs in this run's
campaign area automatically; SLURM is handled by the `bilevel_run` skill's
runner). I want the same short report as before, with special attention to
whether ANY candidate wins significantly at this statistics level or whether
the plateau verdict stands.

## Todo

Use the `bilevel_config` skill to build the validated configuration for the
scan I described, then the `bilevel_run` skill's full-runner to run and
verify it on SLURM (6 geometries), then the `bilevel_digi` skill on run
`cl5`, then the `bilevel_ana` skill on run `cl5`. Each skill is one command
with one status token. Write the report `./analysis.md` with sections **Best
point, Trends, Readout, Reliability, Conclusion** — geometry numbers from the
`bilevel_ana` digest, readout numbers (the operating point and every `note:`
line, copied) from the `bilevel_digi` digest. In the Conclusion state
explicitly whether the best candidate beats the second significantly. Finish
with `done`: the best geometry, its score, the significance verdict, and the
readout operating point.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=6`.
- The full-runner printed `RUN_VERIFIED run=cl5 roots=6` with a job id.
- The readout scan printed `DIGI_VERIFIED run=cl5`.
- The digest printed `ANA_OK geometries=6`.
- `./analysis.md` exists with sections Best point, Trends, Readout,
  Reliability, and Conclusion; quotes the best score and the significance of
  best-vs-second; quotes the readout operating point (Sa and N) with its
  s_err and power; states whether the cluster radius is pinned at a search
  bound; and copies every digest `note:` line.
