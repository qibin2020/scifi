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

# Continue the shared SCEPCal campaign — one more epoch from shared storage

## Context

This is a continuation task for a SCEPCal optimization campaign whose progress
lives in shared storage at `/mnt/bilevel_epochs/share/`. The campaign's reports are
numbered there as `analysis_1.md`, `analysis_2.md`, … — one per completed epoch.
This task runs **exactly one more epoch**, and it is meant to be run
**repeatedly**: each invocation adds the next numbered report.

**Your epoch number k** is `(count of existing analysis_*.md reports in
/mnt/bilevel_epochs/share/) + 1`. **Your input** is the highest-numbered existing
report — read `/mnt/bilevel_epochs/share/analysis_<k-1>.md` and derive your scan from
its Trends and Reliability using the `bilevel_ana` trend rules:

- A parameter that **RISES** (or FALLS) to the edge of its scanned range → scan
  **4 values beyond that edge**, keeping the previous spacing.
- A **FLAT** parameter → fix it at its best value.
- If **all** scanned parameters are FLAT → scan a previously-fixed geometry
  parameter instead (first the projective offset, then the rear length): 4
  values around its current value.
- Keep the reconstruction setup unchanged: cluster radius **20 to 150 mm with a
  15-point grid**, energy threshold **0 to 1.0 GeV with a 5-point grid**, scoring
  `snr_energy`. Evaluate every geometry with **100 electrons at 1 GeV**.

That makes this epoch a **4-geometry** scan. Name the run `share<k>` (e.g.
`share2` for the second epoch — the skills place the config and outputs in the
`share` campaign area automatically) and run it on SLURM (handled by the `bilevel_run` skill's full-runner — no
`sbatch` here).

**Publish step.** After analyzing, write the report locally to `./analysis.md`,
and *additionally* publish a copy to shared storage as
`/mnt/bilevel_epochs/share/analysis_<k>.md` so the next invocation can continue from
it.

## Todo

Determine your epoch number k from the reports already in
`/mnt/bilevel_epochs/share/`, read the highest-numbered existing report
(`/mnt/bilevel_epochs/share/analysis_<k-1>.md`), and derive the next scan from it as
described above. Then: build the validated config with the `bilevel_config` skill
(4 geometries), run and verify it with the `bilevel_run` skill's full-runner (4
geometries), and analyze the results with the `bilevel_ana` skill into
`./analysis.md`. Publish the report to `/mnt/bilevel_epochs/share/analysis_<k>.md`.
Finish with `done`: your epoch number k, the winning geometry, and its score.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=4`.
- The full-runner printed `RUN_VERIFIED run=share<k> roots=4` with a job id,
  where k is one more than the number of reports that existed in
  `/mnt/bilevel_epochs/share/` before this epoch.
- The digest printed `ANA_OK geometries=4`.
- `/mnt/bilevel_epochs/share/analysis_<k>.md` exists with sections Best point, Trends,
  Reliability, and Conclusion.
