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

# Confirm the top SCEPCal candidates at 10x statistics

## Context

The SCEPCal optimization campaign just finished, and its summary ships with this
task as `./campaign.md`. The campaign converged on a narrow set of crystal
geometries, but at only **100 electron events per geometry** the top three are
statistically tied — their score differences sit at roughly 0.1–0.5 sigma, well
inside the Monte-Carlo noise. I want a **confirmation epoch** that re-evaluates
those top candidates at **10x the statistics (1000 electron events at 1 GeV per
geometry)** to resolve the tie and tell me whether a single winner has actually
separated out.

The campaign's top-3 geometries, given as (width, front, offset, rear) in cm →
score, are:

1. **(8.5, 11, 12, 14) → 0.8639**
2. **(8.0, 11, 12, 14) → 0.8595**
3. **(8.0, 11, 12, 13) → 0.8553**

These three are *not* a clean grid product on their own — but they do factor
into one if we add a single interpolation point: scanning **width {8, 8.5} cm ×
rear {13, 14} cm** (with **front fixed at 11 cm** and **projective offset fixed
at 12 cm**) gives **4 geometries** that *cover all three top candidates* plus the
fourth corner (8.5, 13). So run this as a **4-geometry confirmation scan covering
the top-3**, rather than three disconnected points.

Keep the reconstruction setup identical to the campaign: tune the **cluster
radius over 20 to 150 mm (15-point grid)** and the **energy threshold over 0 to
1.0 GeV (5-point grid)**, scoring `snr_energy`. Evaluate every geometry with
**1000 electrons at 1 GeV**.

Name the run `confirm`, write its config to `/srv/runs/confirm.yaml`, and run it
on SLURM (handled by the `bilevel_run` skill's full-runner — no `sbatch` here).
Because 1000 events per geometry is a much longer job than the 100-event campaign
epochs, give the full-runner a generous wall time: pass **120** minutes as its
optional 4th argument.

## Todo

Build the validated config with the `bilevel_config` skill (the 4-geometry
width×rear confirmation scan at 1000 events described above), then run and verify
it with the `bilevel_run` skill's full-runner (4 geometries, wall time 120
minutes), and analyze the results with the `bilevel_ana` skill into
`./analysis.md`. Each skill is one command with one status token. Finish with
`done`: whether a single winner is now statistically separated from the rest,
which geometry it is, and its score.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=4`.
- The full-runner printed `RUN_VERIFIED run=confirm roots=4` with a job id.
- The digest printed `ANA_OK geometries=4`.
- `./analysis.md` exists with sections Best point, Trends, Reliability, and
  Conclusion, quotes the best score, and states explicitly whether the best
  point is now significantly separated from the second-best at 1000 events.
