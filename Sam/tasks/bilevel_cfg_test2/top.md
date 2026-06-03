---
Rank: 3
ForceModel: gemma4
Skills: bilevel_config
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro
---

# Optimize the SCEPCal crystal calorimeter for me

## Context

I'm designing the SCEPCal crystal electromagnetic calorimeter, and I want to find
the crystal geometry that gives me the best energy resolution — the cleanest
signal-to-noise on the reconstructed electron energy.

Here is what I want to explore:

- Try crystals that are **5, 6, 7, and 8 cm wide**.
- Try crystals that are **8 or 10 cm deep at the front**.
- Keep the **projective offset at 10 cm** and the **rear section at 15 cm**.
- Evaluate every geometry with **30 electrons at 1 GeV**.
- For each geometry, also tune how the shower is clustered:
  - how large a **radius of crystals to gather into a cluster** — try anywhere
    from **10 to 150 mm**;
  - and the **per-hit energy threshold** below which hits are ignored as noise —
    try anywhere from **0 to 1 GeV**.

Pick whichever crystal geometry, cluster radius, and threshold reconstruct the
electron energy best.

## Todo

Use the `bilevel_config` skill to build the configuration that captures the
optimization I described above. The skill explains how to translate what I asked
for — the crystal sizes, the electrons, and the clustering I want tuned — into
its command. Run that command. When it prints `CONFIG_VALIDATED geometries=8`,
call `done` with a one-line summary. If it prints `CONFIG_FAIL`, adjust and run
it again.

## Expect

- The skill's command printed `CONFIG_VALIDATED geometries=8`.
- The config exists at the path the token printed (`out=...`).
