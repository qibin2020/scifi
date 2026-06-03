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

# Seed the shared SCEPCal campaign — run epoch 1 and publish its report

## Context

I'm starting a SCEPCal crystal-calorimeter optimization that several tasks will
share: this task runs the **first epoch**, and a *separate, later* task will pick
up from where this one leaves off by reading a report from shared storage. So
this task both runs the starting scan **and publishes its report to the shared
campaign directory** on `/mnt`.

**The starting scan (epoch 1):**

- Crystals **5, 7, and 9 cm wide** × **8 or 11 cm deep at the front**
  (6 geometries).
- **Projective offset fixed at 10 cm**, **rear length fixed at 15 cm**.
- **100 electrons at 1 GeV** per geometry.
- Tune the **cluster radius over 20 to 150 mm (15-point grid)** and the
  **energy threshold over 0 to 1.0 GeV (5-point grid)**, scoring `snr_energy`.

Name the run `share1` (the skills place the config and outputs in the `share`
campaign area automatically) and run it on SLURM (handled by the `bilevel_run` skill's full-runner — no `sbatch` here).

**Publish step.** After analyzing the run, write the report locally to
`./analysis.md` as usual, and *additionally* publish a copy to shared storage so
the continuation task can find it: create the shared campaign directory
`/mnt/bilevel_epochs/share/` and write the report there as
`/mnt/bilevel_epochs/share/analysis_1.md`. This shared copy is the hand-off — it is how
the later task discovers that epoch 1 is done.

## Todo

Build the validated config for the epoch-1 starting scan with the
`bilevel_config` skill (6 geometries), run and verify it with the `bilevel_run`
skill's full-runner (6 geometries), and analyze the results with the
`bilevel_ana` skill into `./analysis.md`. Then create `/mnt/bilevel_epochs/share/` and
publish the report to `/mnt/bilevel_epochs/share/analysis_1.md`. Finish with `done`:
the best geometry, its score, and that the report has been published to shared
storage for the next epoch.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=6`.
- The full-runner printed `RUN_VERIFIED run=share1 roots=6` with a job id.
- The digest printed `ANA_OK geometries=6`.
- `/mnt/bilevel_epochs/share/analysis_1.md` exists with sections Best point, Trends,
  Reliability, and Conclusion.
