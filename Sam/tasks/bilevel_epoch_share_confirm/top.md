---
Rank: 3
ForceModel: gemma4
ControlModel: gemma4
Campaign: share
Skills: bilevel_config, bilevel_run, bilevel_ana
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
CommonStorage: rw
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# Confirm the shared campaign's winner at 10x statistics

## Context

An optimization campaign for the SCEPCal crystal calorimeter lives in shared
storage at `/mnt/bilevel_epochs/share/` as numbered reports (`analysis_1.md`,
`analysis_2.md`, …). The campaign ended on a statistical plateau: its top
geometries are tied within the noise at 100 events per geometry. I want the
final word: re-evaluate the leading candidates at **1000 electron events at
1 GeV** per geometry (10x statistics, so the noise floor drops well below the
observed score differences) and tell me whether a single winner separates.

How to pick the candidates: read all the shared reports and take the
best-scoring geometry of each epoch; from the overall best and its closest
runners-up, form a covering scan of **exactly 4 geometries** — a 2 x 2 grid
over the two geometry parameters where the top candidates differ, with the
parameters they agree on held fixed. Keep the reconstruction setup unchanged:
cluster radius **20 to 150 mm (15-point grid)**, energy threshold **0 to
1.0 GeV (5-point grid)**, scoring `snr_energy`.

Run name `share_confirm` (the skills place the config and outputs in the
`share` campaign area automatically). This job
simulates 4 x 1000 events, so give the runner a **120-minute** wall time (its
optional 4th argument). When done, publish the verdict to the shared campaign
as `/mnt/bilevel_epochs/share/confirm.md` (in addition to the local report).

## Todo

Read the reports in `/mnt/bilevel_epochs/share/`, pick the candidates and the 2 x 2
covering scan as described, then: build the validated config with the
`bilevel_config` skill (1000 events, 4 geometries), run and verify with the
`bilevel_run` skill's full-runner (G=4, wall 120), analyze with the
`bilevel_ana` skill into `./analysis.md`, and publish the report to
`/mnt/bilevel_epochs/share/confirm.md`. Finish with `done`: whether a single winner
is now statistically separated, which geometry, and its score.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=4` and the scanned
  geometry values cover the best points of the shared reports.
- The run-skill's full-runner printed `RUN_VERIFIED run=share_confirm roots=4`
  with a job id.
- The digest printed `ANA_OK geometries=4`.
- `/mnt/bilevel_epochs/share/confirm.md` exists with the four sections (Best point,
  Trends, Reliability, Conclusion) and an explicit statement whether the best
  geometry is now significantly separated from the second best.
