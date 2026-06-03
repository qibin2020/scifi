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

# Optimize the SCEPCal calorimeter and tell me what wins

## Context

I'm designing the SCEPCal crystal electromagnetic calorimeter and I want the
crystal geometry with the best energy resolution — the cleanest signal-to-noise
on the reconstructed electron energy. Here is what I want to explore:

- Try crystals that are **5, 7, and 9 cm wide**.
- Try crystals that are **8 or 11 cm deep at the front**.
- Keep the **projective offset at 10 cm** and the **rear section at 15 cm**.
- Evaluate every geometry with **100 electrons at 1 GeV**.
- For each geometry, also tune how the shower is clustered: the **radius of
  crystals gathered into a cluster** (anywhere from **20 to 150 mm**) and the
  **per-hit energy threshold** below which hits are ignored as noise
  (**0 to 1 GeV**).

Call the run `epoch_init` (the skills place the config and outputs in this
run's campaign area automatically) and run it on SLURM (no `sbatch` here — SLURM is handled by the `bilevel_run` skill's
runner). When it finishes, I don't want raw numbers — I want a
short report telling me which geometry reconstructs the electron energy best,
whether I can trust that result statistically, and what I should try next.

## Todo

Use the `bilevel_config` skill to build the validated configuration for the
optimization I described, then the `bilevel_run` skill's full-runner to run and
verify it on SLURM (6 geometries), then the `bilevel_ana` skill on run
`epoch_init` to write the report `./analysis.md`. Each skill is one command with
one status token. Finish with `done`: the winning geometry, its score, and the
main caveat.

## Expect

- The builder printed `CONFIG_VALIDATED geometries=6`.
- The run-skill's full-runner printed `RUN_VERIFIED run=epoch_init roots=6` with
  a job id.
- The digest printed `ANA_OK geometries=6`.
- `./analysis.md` exists with sections Best point, Trends, Reliability, and
  Conclusion, quotes the best score, states whether the cluster radius is
  pinned at a search bound, and gives one concrete next-iteration
  recommendation.
