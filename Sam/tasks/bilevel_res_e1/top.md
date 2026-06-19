---
Rank: 3
ForceModel: gemma4
ControlModel: gemma4
Campaign: resolution
Skills: bilevel_config, bilevel_run, bilevel_digi, bilevel_ana
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# SCEPCal optimization with the energy-resolution score, epoch 1

## Context

I'm designing the SCEPCal crystal electromagnetic calorimeter together with
its readout electronics. This epoch uses the new **energy-resolution** score
for the inner reconstruction (not the old snr_energy): it rewards a stable,
well-contained reconstructed energy while penalizing both per-channel noise
and lost events, so the cluster radius now has a real interior optimum that
depends on the geometry. The overall figure of merit is the combined metric
**J** (geometry resolution × readout fidelity × a power discount), which the
readout-scan digest computes and prints (its `J_best` line).

- Crystals **4, 7, 10, and 13 cm wide** × **10, 14, 18, and 22 cm deep at the
  front** (16 geometries).
- **Projective offset fixed at 10 cm**, **rear length fixed at 25 cm**.
- **300 electrons at 1 GeV** per geometry.
- Optimize the reconstruction by **scoring `energy_resolution`** (this is the
  `--score` value to pass to the config builder), tuning the **cluster radius
  over 20 to 150 mm (15-point grid)** and the **per-hit energy threshold over
  0 to 1.0 GeV (5-point grid)**.
- Run with **16 geometries and a 30-minute wall** (the run skill takes the
  wall minutes as its 4th argument).
- After the run is verified, run the `bilevel_ana` skill on `res1`, then the
  `bilevel_digi` skill on run `res1` with its **default grid** plus
  `--workers 16` — its digest will then include the combined-metric J section.

Call the run `res1` (the skills place the config and outputs in this run's
campaign area automatically; SLURM is handled by the `bilevel_run` skill's
runner). I want a short report telling me the best geometry by resolution,
whether the cluster radius is now a real interior optimum (not pinned at a
bound), the overall best geometry+readout point by J, and what each parameter
does.

## Todo

Use the `bilevel_config` skill to build the validated configuration for the
scan I described, scoring `energy_resolution`. Then the `bilevel_run` skill's
full-runner with the wall argument (16 geometries, 30 minutes). Then the
`bilevel_ana` skill on run `res1`. Then the `bilevel_digi` skill on run `res1`
with `--workers 16`. Each skill is one command with one status token. Write
the report `./analysis.md` with sections **Best point (J), Resolution trends,
Cluster radius, Readout trends, Conclusion** — the geometry/resolution numbers
and the cluster-radius pinning line from the `bilevel_ana` digest, the J
numbers (J_best tuple, J_marginal and J_trend lines, every `note:`) from the
`bilevel_digi` digest. Finish with `done`: the J_best tuple (geometry, Sa, N,
J), whether the cluster radius is interior, and the main caveat.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=16`.
- The full-runner printed `RUN_VERIFIED run=res1 roots=16` with a job id.
- The digest printed `ANA_OK geometries=16`.
- The readout scan printed `DIGI_VERIFIED run=res1` with a `best_J=` value.
- `./analysis.md` exists with sections Best point (J), Resolution trends,
  Cluster radius, Readout trends, and Conclusion; quotes the best resolution
  score; states whether `R_cluster_mm` is INTERIOR or pinned at a bound;
  quotes the J_best line (geometry, Sa, N, J); quotes the J trend of each
  swept geometry parameter; and copies every digest `note:` line.
