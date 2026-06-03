---
Rank: 3
ForceModel: gemma4
Skills: bilevel_config
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro
---

# Build a bilevel scan config from this description

## Context

You have the `bilevel_config` skill. It builds a validated bilevel YAML config
from a scan description with a single command — the skill doc gives you that
command and how to map a scan to its flags. Follow the skill.

The scan to build:

- Scan **crystal width** at **5, 6, 7, and 8 cm**.
- Scan **crystal front length** at **8 and 10 cm**.
- Keep **projective offset fixed at 10 cm** and **rear length fixed at 15 cm**.
- Simulate **30 electron events at 1 GeV**.
- Brute-optimize the **cluster radius** over **10 to 150 mm with a 15-point grid**
  and the **energy threshold** over **0 to 1.0 GeV with a 5-point grid**, scoring
  with `snr_energy`.

This is a 4 × 2 = **8-geometry** scan.

## Todo

Use the `bilevel_config` skill to build the config for the scan above, deriving
the skill's flags from the numbers in the scan. When the skill's command prints
`CONFIG_VALIDATED geometries=8`, call `done` with a one-line summary. If it
prints `CONFIG_FAIL`, fix the flags and run it again.

## Expect

- The skill's command printed `CONFIG_VALIDATED geometries=8`.
- The config exists at the path the token printed (`out=...`).
