---
Rank: 5
ThinkTime: -1
BashTime: -1
GPU: local
NoMemory: on
Skills: common_env, haml_analyze, haml_train, haml_convert
ForceModel: gemma4-thinking
ControlModel: gemma4-thinking
CommonStorage: ro
---

# Reproduce v1_opt2 — 1-conv HGQ model, TIGHT EBOP budget (~1.5K) to bit-exact streaming RTL

## Context

Build, from scratch in this (writable) task directory, a hardware-aware quantized **1-conv drift-chamber
waveform → scalar hit-count regressor** and its **bit-exact streaming Verilog** (architecture below),
EBOP-constrained to a **tight ~1500 budget**. To actually REACH a budget this low the PID needs many
post-warmup epochs (`EPOCHS ≫ WARMUP`, e.g. ~4000) — otherwise it only gets partway and the
Pareto-within-budget selection never engages. You have a three-skill pipeline that encodes the whole
recipe. **Use the skills.** Success = bit-exact RTL verification AND EBOPs that converge near ~1.5K.

### Environment & data
- **Toolchain — use the `common_env` skill (do NOT hardcode a PATH or `source env.sh`).** The full
  HGQ -> da4ml -> RTL stack (`python3, jax(CUDA), keras, hgq, da4ml, h5py, verilator, make, g++`) is a
  shared env at **prefix** `/mnt/sci_envs/fpga_toolchain`, **env name** `hgq`
  (path `/mnt/sci_envs/fpga_toolchain/envs/hgq`). Call `list_shared_envs`, then `activate_env(env_path="/mnt/sci_envs/fpga_toolchain/envs/hgq")`. After
  activation, every bash call has the tools + `KERAS_BACKEND=jax` injected — run bare `python3 ...`,
  `verilator ...`, `make`. If the env is missing, run the `haml_bootstrap` task first.
- **Data** (read-only, on the shared `/mnt` storage the driver auto-maps): `/mnt/sci_shared/data/{train,val}_v3.h5`.
  **Dataset keys (use these directly — do NOT spend iterations probing):** `waveform500` `(N,500)` = input waveform; `predict500` `(N,)` = scalar hit-count target; `is_primary3000` `(N,3000)` — for the per-patch target use `is_primary3000[:, :500]` summed into 20 patches. (Other keys exist but are unused.)
- **GPU**: a free local GPU is auto-pinned (`CUDA_VISIBLE_DEVICES`); scripts don't preallocate it.
- **Persistence**: do ALL work directly under the **current task directory `./`** (the only persistent location). Do NOT build the project under `/srv` root, `/tmp`, or any absolute path — outputs written elsewhere are discarded when the container exits.
- **TRAINING SCALE — FULL / production.** Train at the template's production scale and the FULL
  dataset: `EPOCHS=1000` for `_ref`/`_opt`, `EPOCHS=4000` for `_opt2` (the templates already default
  to these — do NOT reduce, do NOT set the `_DBG` path). After `trace_minmax`, **report the final
  validation MAE** — the templates print `val MAE ...` and write `mae=...` into `train_status.txt`;
  surface that number in your `done` summary. Full scale yields reference-quality accuracy in addition
  to bit-exactness. (Bit-exactness itself is scale-independent; the fast reduced-scale path is for
  debugging only and is not for this run.)


### Architecture + target
```
Input(500) -> Reshape(500,1) -> QConv1D(5, k25, s25, 'valid', relu, pf=1, FROZEN 10-bit iq)
            -> Flatten -> QDense(16,relu) -> QDense(8,relu) -> QDense(1,relu)
```
Target = 10-bit `predict500` (scalar). **EBOP target = 1500** (tight).

## Todo
1. `haml_analyze`: scalar output, `targets.ebops = 1500`.
2. `haml_train`: 1-conv **optimized** template with `BetaPID(1500, warmup=~500)` + `FreeEBOPs` +
   `ParetoFront`, **`EPOCHS ≈ 4000`** so the PID converges; select the most-accurate model WITHIN the
   ~1.5K budget from the front; calibrate once on all val; save `model.keras`.
3. `haml_convert`: per-window decompose, comb_full golden, hand wrapper, Verilator-verify **both modes**.

## Expect
- `model.keras` exists (calibrated), trained with `FreeEBOPs + BetaPID(1500) + ParetoFront`.
- The model converged to a tight budget: **selected/final EBOPs ≤ ~3000** (near 1.5K), reported. The
  Pareto-within-budget selection should have engaged (a model at/below the budget was chosen).
- Convert gates pass (Stage-1 ~0, Stage-2 0.0); cores are the smallest of the v1 variants.
- `verify_golden.py --no-pause` AND `--inp-pause 0.3 --seed 42` both `PASSED: All ... match exactly`.
