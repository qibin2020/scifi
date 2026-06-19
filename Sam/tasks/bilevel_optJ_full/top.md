---
Rank: 4
ForceModel: gemma4
ControlModel: gemma4
Campaign: optJ_m1
Skills: bilevel_config, bilevel_run, bilevel_digi, bilevel_ana
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# Optimize the detector by combined merit J — 5-epoch campaign (M1)

## Context

**MANDATORY — read first.** Every `bilevel_config` build in this task, in
EVERY epoch, MUST pass **`--score energy_resolution`**. Do NOT use the default
score. The analysis digest must show `score_fn: energy_resolution`; if it ever
shows `snr_energy`, that epoch is WRONG and must be rebuilt.

I'm optimizing the SCEPCal calorimeter + readout for one combined merit **J**
(geometry energy-resolution × readout fidelity × power discount), printed by
the readout-scan digest as its `J_best` / `J_marginal` / `J_trend` lines. Find
the geometry + readout that maximizes J.

Four geometry design variables and their allowed ranges:
**width** 3–19 cm · **front** 5–28 cm · **rear** 9–33 cm · **offset** 0–18 cm.

You choose which subset to scan each epoch, guided by the previous epoch's
`J_marginal` trends. Inner reco scores **energy_resolution** (cluster radius
20–150 mm 15-pt, energy threshold 0–1 GeV 5-pt); readout scanned by
`bilevel_digi` over its default Sa×N grid; J read from its digest.

**5 epochs, 32 geometries each, 1000 electrons at 1 GeV**; pass `32`
geometries and a `45`-minute wall to the run skill.

**Epoch 1:** width {4, 9, 14, 19} × front {8, 14, 20, 26} × rear {13, 29}
(= 32 geoms), offset 9 fixed. **Epochs 2–5:** from the previous `J_marginal`
lines, scan the two most-active axes more finely (RISES/FALLS at an edge >
PEAKED > FLAT); RISES/FALLS → extend beyond the edge; PEAKED@v → bracket v
finer; a FLAT axis → fix it and open a not-yet-scanned axis. Keep ~32
geometries each epoch and stay within the ranges.

Run names `jf1` … `jf5`.

## Todo

For each epoch k = 1..5:
1. Build the config with `bilevel_config`, **including `--score
   energy_resolution`** and your chosen `--geom` ranges (run name `jf<k>`,
   `--events 1000`, `--opt R_cluster_mm:20:150:15 --opt E_threshold_GeV:0:1:5
   --optimize-method brute`).
2. Run with `bilevel_run` full-runner: `jf<k>.yaml jf<k> 32 45`.
3. Analyze with `bilevel_ana` on `jf<k>` — CONFIRM `score_fn:
   energy_resolution`.
4. Scan readout with `bilevel_digi --workers 32` on `jf<k>`; read `J_best`.
5. Write `./analysis_<k>.md` (Best J point, J trends, next-epoch reasoning).

Then write `./campaign.md` (per-epoch J_best table + overall best J + a
parameter-impact line for width, front, rear, offset, Sa, N). Finish with
`done`: overall best J tuple (geometry, Sa, N, J) and how it improved.

## Expect

- Every epoch: `CONFIG_VALIDATED geometries=32`, `RUN_VERIFIED run=jf<k>`,
  `ANA_OK` with `score_fn: energy_resolution`, `DIGI_VERIFIED run=jf<k>` with
  `best_J=`.
- `./analysis_1.md` … `_5.md` and `./campaign.md` exist; campaign.md shows
  per-epoch J_best, overall best J (>= epoch-1 best), and the parameter-impact
  table.
