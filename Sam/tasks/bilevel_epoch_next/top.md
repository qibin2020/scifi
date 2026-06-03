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

# Run the next SCEPCal optimization epoch from the previous report

## Context

The previous optimization epoch is finished, and its report ships with this
task: `./previous_analysis.md`. I want you to continue the optimization —
read that report and run the next epoch that follows from it.

Derive the next scan from the report's Trends and Reliability, using the
`bilevel_ana` skill's trend rules:

- A parameter that **RISES** to the edge of its scanned range → extend it:
  scan **4 new values beyond the previous edge** (keep the previous spacing).
- A parameter that is **FLAT** → fix it at the previous best value.
- Parameters that were already fixed stay at their previous values.
- Keep the reconstruction setup unchanged: cluster radius **20 to 150 mm with
  a 15-point grid**, energy threshold **0 to 1.0 GeV with a 5-point grid**,
  scoring with `snr_energy`.
- Evaluate every geometry with **100 electrons at 1 GeV**.

That makes the next epoch a **4-geometry** scan. Call the run `epoch_next`,
write its config to `/srv/runs/epoch_next.yaml`, and run it on SLURM (handled
by the `bilevel_run` skill's runner — no `sbatch` here). Then analyze the new
results and give me the report for the epoch after this one.

## Todo

Read `./previous_analysis.md`, derive the next scan from it as described
above, then: build the validated config with the `bilevel_config` skill, run
and verify it with the `bilevel_run` skill's full-runner (4 geometries), and
analyze the results with the `bilevel_ana` skill into `./analysis.md`. Each
skill is one command with one status token. Finish with `done`: the winning
geometry, its score, and what the next epoch should try.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=4`.
- The new scan follows the previous report: the parameter that RISES
  (`scepcal_xtal_theta_width`) is extended beyond its previous edge of 9 cm,
  and the FLAT parameter (`scepcal_xtal_length_f`) is fixed at 11 cm.
- The run-skill's full-runner printed `RUN_VERIFIED run=epoch_next roots=4`
  with a job id.
- The digest printed `ANA_OK geometries=4`.
- `./analysis.md` exists with sections Best point, Trends, Reliability, and
  Conclusion, quotes the best score, and gives one concrete recommendation
  for the next epoch.
