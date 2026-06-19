---
Rank: 3
ForceModel: gemma4
ControlModel: gemma4
Campaign: optJ_debug
Skills: bilevel_config, bilevel_run, bilevel_digi, bilevel_ana
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# Find the best detector by combined merit J — short debug campaign

## Context

**MANDATORY — read first.** Every `bilevel_config` build in this task, in
EVERY epoch, MUST pass **`--score energy_resolution`**. Do NOT use the default
score. The analysis digest must show `score_fn: energy_resolution`; if it ever
shows `snr_energy`, that epoch is WRONG and must be rebuilt with `--score
energy_resolution`.

I'm optimizing the SCEPCal calorimeter + readout for a single combined merit
**J** (geometry energy-resolution × readout fidelity × power discount), printed
by the readout-scan digest as its `J_best` / `J_marginal` / `J_trend` lines.
This is a SHORT debug run (3 epochs) to check the loop.

Four geometry design variables and their allowed ranges:
**width** 3–19 cm · **front** 5–28 cm · **rear** 9–33 cm · **offset** 0–18 cm.

You choose which subset to scan each epoch, guided by the previous epoch's
`J_marginal` trends. Inner reco scores **energy_resolution** (cluster radius
20–150 mm 15-pt, energy threshold 0–1 GeV 5-pt); readout scanned by
`bilevel_digi` over its default Sa×N grid; J read from its digest.

**3 epochs, 8 geometries each, 100 electrons at 1 GeV** (debug sizes); pass
`8` geometries and a `30`-minute wall to the run skill.

**Epoch 1:** width {5, 11, 17} × front {8, 14, 20} (= 9, fine), offset 9 and
rear 21 fixed. **Epochs 2–3:** from the previous `J_marginal` lines, scan the
two most-active axes (RISES/FALLS at an edge > PEAKED > FLAT); RISES/FALLS →
extend beyond the edge; PEAKED@v → bracket v finer; a FLAT axis → fix it and
open a not-yet-scanned axis (offset, then rear). Stay within the ranges.

Run names `jd1`, `jd2`, `jd3`.

## Todo

For each epoch k = 1, 2, 3:
1. Build the config with `bilevel_config`, **including `--score
   energy_resolution`** and the geometry `--geom` ranges you chose (run name
   `jd<k>`). Example shape:
   `build.sh --name jd<k> --scheme srv --geom width:... --geom front:... --geom
   offset:9:cm --geom rear:21:cm --events 100 --particle e- --momentum 1
   --optimize-method brute --opt R_cluster_mm:20:150:15 --opt
   E_threshold_GeV:0:1:5 --score energy_resolution`.
2. Run with `bilevel_run` full-runner: `jd<k>.yaml jd<k> 8 30`.
3. Analyze with `bilevel_ana` on `jd<k>` — CONFIRM its digest says
   `score_fn: energy_resolution`.
4. Scan readout with `bilevel_digi --workers 16` on `jd<k>`; read `J_best`.
5. Write `./analysis_<k>.md` (Best J point, J trends, next-epoch reasoning).

Then write `./campaign.md` (per-epoch J_best table + overall best J). Finish
with `done`: the overall best J tuple (geometry, Sa, N, J) and how it improved.

## Expect

- Every epoch: `CONFIG_VALIDATED geometries=` (8 or 9), `RUN_VERIFIED
  run=jd<k>`, `ANA_OK`, `DIGI_VERIFIED run=jd<k>` with a `best_J=` value.
- Every epoch's `bilevel_ana` digest shows **`score_fn: energy_resolution`**
  (NOT snr_energy). The best reco `R_cluster_mm` is INTERIOR for at least some
  geometries (energy_resolution does not pin R at the 20 mm bound the way
  snr_energy does).
- `./analysis_1.md`, `_2.md`, `_3.md`, `./campaign.md` all exist; campaign.md
  shows per-epoch J_best and the overall best J, which is >= the epoch-1 best.
