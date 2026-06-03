---
name: bilevel_config
description: Turn a natural-language bilevel detector-optimization scan description into a VALID bilevel_opt YAML config by invoking the bundled make_config.py generator (never hand-write the YAML), then validate it with a local generate-stage run.
---

# bilevel_config — generate a bilevel-optimization YAML from one command

A bilevel scan needs a ~30-line YAML (geometry sweep + sim + inner-loop
optimizer). **Do NOT hand-write that YAML.** This skill ships a generator,
`make_config.py`, that emits a correct config from a few flags. Your job is to
translate the natural-language scan into one short `make_config.py` invocation,
then run the generate stage once to confirm it parses.

The generator lives next to this file. Refer to it as
`/srv/bilevel/scifi/Nam/skills/bilevel_config/make_config.py` if the skill dir is
mounted, or use the absolute host path the task gives you. (When run on the
login node it is at
`/pscratch/sd/b/binus/Playground/AIS_design_det/scifi/Nam/skills/bilevel_config/make_config.py`.)

## Step 1 — build the config (one bash command)

`make_config.py` needs PyYAML. The bare container python may lack it, so source
the project `env.sh` first (it activates the key4hep python that has PyYAML):

```bash
cd /srv/bilevel && source ./env.sh >/dev/null 2>&1 && \
python3 <MAKE_CONFIG_PY> \
  --out <CONFIG_PATH> --name <RUN_NAME> --runs-dir /srv/runs --scheme srv \
  --geom <PARAM:VALS[:UNIT]> [--geom ...] \
  --events <N> --particle e- --momentum <GeV> \
  --optimize-method <METHOD> \
  --opt <NAME:LO:HI:GRID> [--opt ...] \
  --score snr_energy
```

It prints `CONFIG_OK geometries=<G> total_runs=<T> out=<path>` on success.

## NL → flags mapping

- **Geometry sweep** → one `--geom` per parameter, `PARAM:VALUES[:UNIT]`:
  - explicit list: `--geom scepcal_xtal_theta_width:5,6,7,8:cm`
  - range (inclusive): `--geom scepcal_xtal_length_f:6..10..2:cm`
  - a fixed value is just a 1-element list: `--geom scepcal_projective_offset_r:10:cm`
  - Aliases accepted: `width`→`scepcal_xtal_theta_width`, `front`→`scepcal_xtal_length_f`,
    `rear`→`scepcal_xtal_length_r`, `offset`→`scepcal_projective_offset_r`.
  - Default unit is `cm` if you omit `:UNIT`.
- **"5 e- events at 1 GeV"** → `--events 5 --particle e- --momentum 1`.
  Optional: `--plusminus-percent`, `--theta-min`, `--theta-max` (default 60/120),
  `--seed-start`/`--seed-end` (default 0/0).
- **"brute-optimize R (5–200mm) and E_threshold (0–0.5)"** →
  `--optimize-method brute --opt R_cluster_mm:5:200:15 --opt E_threshold_GeV:0:0.5:5`.
  The 4th field of `--opt` is the grid resolution; for `brute` it is also used as
  the brute grid size automatically.

## Valid vocabulary (do not invent names)

- **Scannable geometry params**: `scepcal_xtal_theta_width`,
  `scepcal_projective_offset_r`, `scepcal_projective_offset_x`,
  `scepcal_xtal_length_f`, `scepcal_xtal_length_r`, `scepcal_mainlayer_reargap`,
  `scepcal_timinglayer_gap`, `scepcal_timing_xtal_depth`,
  `scepcal_timing_xtal_length`. (These exist as `<constant>`s in
  `DectDimensions_IDEA_o2_v01.xml`.)
- **Optimize methods**: `brute` (needs grid sizes — supplied automatically),
  `differential_evolution`, `dual_annealing`, `shgo`, `L-BFGS-B`, `bounded`.
- **Inner algorithm**: `seeded_radius_cog` (default). Its optimized params are
  `R_cluster_mm` and `E_threshold_GeV`.
- **Score**: `snr_energy` (only option).

## Path schemes (`--scheme`)

Two container mount layouts — pick the one matching how the config will be RUN:

- `--scheme srv` (default): project at `/srv`. Detector paths
  `/srv/detector_config/...`. Use for SLURM / `enter_scifi_container.sh` runs
  (like opt_iterA).
- `--scheme bilevel`: project at `/srv/bilevel`. Detector paths
  `/srv/bilevel/detector_config/...`. Use for the local agent-mount tasks.

`repo_root` is always `/srv/k4geo` and `runs_dir` defaults to `/srv/runs` in both.
Override the detector prefix entirely with `--base <prefix>` if needed.

## Step 2 — validate (generate-only, fast, no ddsim)

Run the outer loop in `generate` mode; it writes per-geometry XMLs and a
`manifest.json` with one entry per geometry × seed × particle:

```bash
bilevel_opt --config <CONFIG_PATH> --stage outer --run-mode generate --run <RUN_NAME> \
  >/tmp/gen.log 2>&1 \
  && python3 -c 'import json;print("MANIFEST_OK count="+str(len(json.load(open("/srv/runs/<RUN_NAME>/sim_outputs/manifest.json")))))' \
  || { echo GEN_FAIL; tail -15 /tmp/gen.log; }
```

`count` should equal G × (seed_end−seed_start+1) × n_particles. Stop as soon as
you see `MANIFEST_OK`; do not re-run.

## Worked example

NL: *"scan crystal width 5,6,7,8 cm and front length 6,8,10 cm, fix offset=10 and
rear=15, 5 e- events at 1 GeV, brute-optimize R_cluster (5–200mm) and
E_threshold (0–0.5 GeV)."*

```bash
python3 <MAKE_CONFIG_PY> \
  --out /srv/runs/cfg/scan.yaml --name myscan --runs-dir /srv/runs --scheme srv \
  --geom scepcal_xtal_theta_width:5,6,7,8:cm \
  --geom scepcal_xtal_length_f:6,8,10:cm \
  --geom scepcal_projective_offset_r:10:cm \
  --geom scepcal_xtal_length_r:15:cm \
  --events 5 --particle e- --momentum 1 \
  --optimize-method brute \
  --opt R_cluster_mm:5:200:15 --opt E_threshold_GeV:0:0.5:5 \
  --score snr_energy
```

→ `CONFIG_OK geometries=12 total_runs=12`. Then the Step-2 generate gives
`MANIFEST_OK count=12`.

## Gotchas the generator already handles

- `brute` requires `brute_grid_sizes` (one per opt param) — added automatically
  from each `--opt` grid field.
- The 1-valued geom params become the heatmap `fixed:` block; the multi-valued
  ones become the (≤2) heatmap `axes`.
- `run_mode: generate` sets `key4hep.run_setup: false` (no key4hep sourcing
  needed just to write XMLs), so the generate validation is instant.
