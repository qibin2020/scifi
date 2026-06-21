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

# Reproduce v3_opt — 2-conv + einsum HGQ model, EBOP-constrained (~3K) to bit-exact streaming RTL

## Context

Build, from scratch in this (writable) task directory, a hardware-aware quantized **2-conv model with a
per-patch einsum tail** and its **bit-exact streaming Verilog** (architecture below), but training must
**drive the FPGA cost (EBOPs ≈ LUT/DSP) toward a budget of ~3000** via the PID + Pareto callbacks the
`haml_train` skill provides. This is the hard topology (conv2 `padding='same'` → 3-window shift buffer,
QEinsumDense tail). **Use the skills** — both the resource-constrained training and the
einsum-tail convert arithmetic are encoded there. Success = bit-exact RTL verification AND a clearly
resource-reduced model.

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
Input(500) -> QConv1D(8, k25, s25, 'valid', relu, pf=1, FROZEN 10-bit iq)
            -> QConv1D(16, k3, s1, 'same', relu, pf=1)
            -> QDense(16,relu) -> QDense(1,relu)
            -> QEinsumDense('bc,c->bc', 20, bias_axes='c', kernel_initializer='ones')
```
Target = 20-patch sums of `is_primary3000[:, :500]` (per-patch, n_out=20). **EBOP target = 3000**.

## Todo
1. `haml_analyze`: per_patch output (n_out=20), conv2_window=3, `targets.ebops = 3000`.
2. `haml_train`: 2-conv **optimized** template — `FreeEBOPs + BetaPID(3000, warmup=W) + ParetoFront`;
   select most-accurate model within budget; calibrate once on all val; save `model.keras`. `EPOCHS ≫ warmup`.
3. `haml_convert`: kernel core + 3-window mid core + per-patch einsum tail; comb_full golden
   (sign-corrected); Verilator-verify **both modes**. Stage-C (chain == comb_full) must pass first.

## Expect
- `model.keras` exists (calibrated), trained with `FreeEBOPs + BetaPID + ParetoFront`.
- Selected model EBOPs are well below the unconstrained level (clearly constrained toward ~3K). Report EBOPs.
- Convert gates: Stage A ~0, Stage B 0.0, **Stage C = N/N bit-exact**; cores smaller than unconstrained.
- `verify_golden.py --no-pause` AND `--inp-pause 0.3 --seed 42` both `PASSED: All ... match exactly`
  (n_samples × 20 per-patch outputs).
