---
name: bilevel_config
description: Turn a natural-language bilevel detector-optimization scan description into a VALID, validated bilevel_opt YAML config by running ONE bundled command (build.sh). Never hand-write the YAML; never source env or validate separately — build.sh does all of it.
---

# bilevel_config — generate + validate a bilevel YAML with ONE command

A bilevel scan needs a ~30-line YAML (geometry sweep + sim + inner-loop
optimizer). **Do NOT hand-write that YAML, and do NOT source any environment or
run a separate validation.** This skill ships `build.sh`, which does everything
in one shot: it sources the env, runs the generator, and validates that the
config parses. Your ONLY job is to translate the natural-language scan into the
right flags and run that one command.

## The one command

Run exactly this, filling in the `--geom`/`--opt`/`--events`/`--momentum`
values from the scan you were given:

```bash
bash /srv/skills/bilevel_config/build.sh \
  --name <RUN_NAME> --scheme srv \
  --geom <PARAM:VALS[:UNIT]> [--geom ...] \
  --events <N> --particle e- --momentum <GeV> \
  --optimize-method brute \
  --opt <NAME:LO:HI:GRID> [--opt ...] \
  --score snr_energy
```

You do NOT choose where the config goes: it is placed in this run's campaign
area automatically (`/srv/runs/<campaign>/<RUN_NAME>.yaml` — the success token
shows the exact path as `out=`). Explicit `--out`/`--runs-dir` flags still
work when a task demands a specific location, but normally you omit them.

It prints **one** line:

- `CONFIG_VALIDATED geometries=<G> out=<path>` → success. Call `done` immediately.
- `CONFIG_FAIL <reason>` → fix the flags and rerun the same command.

Do not run `make_config.py`, `source env.sh`, or `bilevel_opt` yourself —
`build.sh` already does all of that internally. One command, one token, done.

## NL → flags mapping

- **Geometry sweep** → one `--geom` per parameter, `PARAM:VALUES[:UNIT]`:
  - explicit list: `--geom width:5,6,7,8:cm`
  - range (inclusive): `--geom front:6..10..2:cm`
  - a fixed value is a 1-element list: `--geom offset:10:cm`
  - **Aliases** (use these short names): `width`→`scepcal_xtal_theta_width`,
    `front`→`scepcal_xtal_length_f`, `rear`→`scepcal_xtal_length_r`,
    `offset`→`scepcal_projective_offset_r`. Full names also work.
  - Default unit is `cm` if you omit `:UNIT`.
- **"30 e- events at 1 GeV"** → `--events 30 --particle e- --momentum 1`.
- **"brute-optimize cluster radius (10–150 mm, 15-point grid) and energy
  threshold (0–1.0 GeV, 5-point grid)"** →
  `--optimize-method brute --opt R_cluster_mm:10:150:15 --opt E_threshold_GeV:0:1.0:5`.
  The 4th field of `--opt` is the grid resolution.

## Physics language → parameters

Sometimes the scan is written as **plain physics prose** with no flag names, no
parameter code-names, and no commands — a physicist just describing what they
want to optimize, with concrete numbers. Use this glossary to bridge the physics
words to the exact flags, then fill in the one `build.sh` command above. Match on
the **meaning**, and copy the **numbers** verbatim.

| Physicist says… | Flag to emit |
|---|---|
| "crystal width", "how wide each crystal is", crystals "N cm wide" | `--geom width:N,...:cm` |
| "crystal front length", "depth at the front", "front section", crystals "N cm deep at the front" | `--geom front:N,...:cm` |
| "rear length", "rear section" | `--geom rear:N:cm` |
| "projective offset" | `--geom offset:N:cm` |
| "energy resolution", "signal-to-noise on reconstructed energy", "reconstruct the energy best", "cleanest reconstruction" | `--score snr_energy` |
| "cluster radius", "radius of crystals gathered into a cluster", "cluster size", "how the shower is clustered" | `--opt R_cluster_mm:LO:HI:GRID` |
| "per-hit energy threshold", "threshold below which hits are ignored", "noise cutoff" | `--opt E_threshold_GeV:LO:HI:GRID` |
| "N electrons at X GeV", "N e- at X GeV" | `--events N --particle e- --momentum X` |

Rules for the physics register:

- **A list of sizes is a multi-value `--geom`**: "crystals 5, 6, 7, and 8 cm
  wide" → `--geom width:5,6,7,8:cm`. "8 or 10 cm deep at the front" →
  `--geom front:8,10:cm`.
- **A single "keep / fix it at N cm" value is a 1-element `--geom`**: "keep the
  projective offset at 10 cm" → `--geom offset:10:cm`; "rear section at 15 cm" →
  `--geom rear:15:cm`. Fixed values still need their own `--geom`.
- **"tune / optimize / find the best X over A to B"** → brute-optimize X:
  `--optimize-method brute` plus `--opt <NAME>:A:B:GRID`. Use the grid count the
  physicist states; if they give only a range, default the grid to **15** for the
  cluster radius and **5** for the energy threshold.
- **Always finish with `--score snr_energy`** whenever the goal is energy
  resolution / signal-to-noise on reconstructed energy (the only score there is).
- The geometry count is the product of the multi-value lists (e.g. 4 widths × 2
  front lengths = 8). Fixed 1-element geoms do not multiply it.

**Worked physics → flags.** Prose: *"I want the crystal geometry with the best
signal-to-noise on reconstructed electron energy. Try crystals 5,6,7,8 cm wide
and 8 or 10 cm deep at the front, keep the projective offset at 10 cm and the
rear section at 15 cm, evaluate with 30 electrons at 1 GeV, and tune how the
shower is clustered — the radius of crystals gathered into a cluster (10–150 mm)
and the per-hit energy threshold below which hits are ignored (0 to 1 GeV)."*

```bash
bash /srv/skills/bilevel_config/build.sh \
  --name bench --scheme srv \
  --geom width:5,6,7,8:cm \
  --geom front:8,10:cm \
  --geom offset:10:cm \
  --geom rear:15:cm \
  --events 30 --particle e- --momentum 1 \
  --optimize-method brute \
  --opt R_cluster_mm:10:150:15 --opt E_threshold_GeV:0:1.0:5 \
  --score snr_energy
```

→ `CONFIG_VALIDATED geometries=8 out=<campaign area>/bench.yaml`. Then call `done`.

## Valid vocabulary (do not invent names)

- **Geometry params (or their aliases above)**: `scepcal_xtal_theta_width`,
  `scepcal_projective_offset_r`, `scepcal_projective_offset_x`,
  `scepcal_xtal_length_f`, `scepcal_xtal_length_r`, `scepcal_mainlayer_reargap`,
  `scepcal_timinglayer_gap`, `scepcal_timing_xtal_depth`,
  `scepcal_timing_xtal_length`.
- **Optimize methods**: `brute` (default for these scans),
  `differential_evolution`, `dual_annealing`, `shgo`, `L-BFGS-B`, `bounded`.
- **Inner optimized params**: `R_cluster_mm`, `E_threshold_GeV`.
- **Score**: `snr_energy` (only option).

## Path scheme (`--scheme`)

- `--scheme srv` (use this): project at `/srv`, detector at
  `/srv/detector_config/...`, `runs_dir` `/srv/runs`. This is what the tasks
  bind.

## Worked example

NL: *"scan crystal width 5,6,7,8 cm and front length 6,8,10 cm, fix offset=10 and
rear=15, 5 e- events at 1 GeV, brute-optimize R_cluster (5–200 mm, 15-grid) and
E_threshold (0–0.5 GeV, 5-grid)."*

```bash
bash /srv/skills/bilevel_config/build.sh \
  --name bench --scheme srv \
  --geom width:5,6,7,8:cm \
  --geom front:6,8,10:cm \
  --geom offset:10:cm \
  --geom rear:15:cm \
  --events 5 --particle e- --momentum 1 \
  --optimize-method brute \
  --opt R_cluster_mm:5:200:15 --opt E_threshold_GeV:0:0.5:5 \
  --score snr_energy
```

→ `CONFIG_VALIDATED geometries=12 out=<campaign area>/bench.yaml`. Then call `done`.

## Notes

- `build.sh` handles all boilerplate the generator needs: `brute` grid sizes, the
  heatmap `fixed:`/`axes:` split, and skipping key4hep sourcing for the (instant)
  generate-only validation. You never touch these.
- If you ever need the raw generator's full flag list:
  `python3 /srv/skills/bilevel_config/make_config.py --help`. But for a normal
  scan, the one `build.sh` command above is all you need.
