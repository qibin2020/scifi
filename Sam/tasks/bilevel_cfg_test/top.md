---
Rank: 3
ForceModel: gemma4
Skills: bilevel_config
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs/cfg_test_scratch:/srv/runs:rw
---

# Build a bilevel scan config from a description, then confirm it parses

## Context

Scan **crystal width 5, 6, 7, 8 cm** and **front length 6, 8, 10 cm**, with
**offset fixed at 10 cm** and **rear length fixed at 15 cm**. Use **5 e- events
at 1 GeV**. Brute-optimize **R_cluster (5–200 mm)** with a 15-point grid and
**E_threshold (0–0.5 GeV)** with a 5-point grid, scoring with `snr_energy`.

That is a 4 × 3 = **12-geometry** scan. The `bilevel_config` skill tells you how
to turn this into a `make_config.py` call. The generator is at
`/srv/skills/bilevel_config/make_config.py`. Write the config to
`/srv/runs/scan.yaml` with run name `cfg_test`, runs dir `/srv/runs`, and the
**srv** path scheme.

## Todo

Run these two commands. Do NOT write any YAML by hand.

1. Build the config (source `env.sh` first — it activates the key4hep python
   that has PyYAML; the bare container python does not):

```bash
cd /srv/bilevel && source ./env.sh >/dev/null 2>&1 && \
python3 /srv/skills/bilevel_config/make_config.py \
  --out /srv/runs/scan.yaml --name cfg_test --runs-dir /srv/runs --scheme srv \
  --geom scepcal_xtal_theta_width:5,6,7,8:cm \
  --geom scepcal_xtal_length_f:6,8,10:cm \
  --geom scepcal_projective_offset_r:10:cm \
  --geom scepcal_xtal_length_r:15:cm \
  --events 5 --particle e- --momentum 1 \
  --optimize-method brute \
  --opt R_cluster_mm:5:200:15 --opt E_threshold_GeV:0:0.5:5 \
  --score snr_energy
```

   Expect a line `CONFIG_OK geometries=12 ...`.

2. Confirm the config parses by generating the geometry XMLs + manifest
   (generate-only, no ddsim — fast):

```bash
cd /srv/bilevel && source ./env.sh >/dev/null 2>&1 && \
  bilevel_opt --config /srv/runs/scan.yaml --stage outer --run-mode generate --run cfg_test >/tmp/gen.log 2>&1 && \
  python3 -c 'import json;print("MANIFEST_OK count="+str(len(json.load(open("/srv/runs/cfg_test/sim_outputs/manifest.json")))))' || { echo GEN_FAIL; tail -8 /tmp/gen.log; }
```

As soon as you see `MANIFEST_OK count=12`, the task is done: **call the `done`
tool** with a one-line summary (e.g. "config built, manifest has 12 geometries").
Run each command once. Only if a command fails (`GEN_FAIL` or no `CONFIG_OK`)
should you read the log tail and fix it.

## Expect

- `make_config.py` printed `CONFIG_OK geometries=12`.
- `/srv/runs/scan.yaml` exists.
- `/srv/runs/cfg_test/sim_outputs/manifest.json` exists with 12 entries
  (`MANIFEST_OK count=12`).
