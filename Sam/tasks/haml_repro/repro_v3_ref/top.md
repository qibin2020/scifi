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

# Reproduce v3_ref — 2-conv + per-patch einsum HGQ model to bit-exact streaming RTL

## Context

Build, from scratch in this (writable) task directory, a hardware-aware quantized **2-conv model with a
per-patch einsum tail** and its **bit-exact streaming Verilog**. This is the hard topology: a second
conv with `padding='same'` forces a 3-window shift buffer, and the QEinsumDense tail must be pulled out
of the trace and realized as a per-patch scale-LUT + multiplier + bias + requant. **Use the skills; do
not re-derive** — especially the einsum-tail integer arithmetic and the streaming gotchas, which are in
the `haml_convert` skill. Success = bit-exact RTL verification (widths are width-adaptive, not fixed).

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


### Architecture to build
```
Input(500)
 -> QConv1D(8,  k25, s25, 'valid', relu, pf=1, input quantizer FROZEN to 10-bit ADC)   # per-patch (20,8)
 -> QConv1D(16, k3,  s1,  'same',  relu, pf=1)                                          # neighbor mix (20,16)
 -> QDense(16, relu) -> QDense(1, relu)                                                  # per-patch DNN (20,1)
 -> QEinsumDense('bc,c->bc', 20, bias_axes='c', kernel_initializer='ones')              # per-patch tail (20,)
```
Target = per-patch primary counts: 20-patch sums of `is_primary3000[:, :500]`, shape (N, 20). Output is
**per-patch (20 values/sample)**. Unconstrained training (plain MSE; no EBOP budget).

## Todo
1. `haml_analyze`: digitization (10-bit), output (per_patch, n_out=20), schema, streaming
   (patch_size=25, n_patches=20, conv2_window=3 because conv2 is padding='same'), eval = comb_full.
   Emit `spec.json` + `common/sci_io.py`; place `general/`.
2. `haml_train`: adapt the 2-conv complex template; calibrate once on all val; save `model.keras`.
3. `haml_convert`: decompose into the per-patch kernel core + 3-window mid core + the per-patch einsum
   tail; build the comb_full golden (sign-corrected); Verilator-verify **bit-exact both modes**. The
   Stage-C gate (chain == comb_full) MUST pass before any Verilog is built.

## Expect
- `model.keras` exists (trained + calibrated).
- Convert gates: Stage A ~0, Stage B 0.0, **Stage C = N/N bit-exact** (chain vs comb_full).
- `verify_golden.py --no-pause` AND `--inp-pause 0.3 --seed 42` both print `PASSED: All ... outputs
  match exactly` (n_samples × 20 per-patch outputs).
- The RTL is the streaming composition (kernel core → 3-window shift buffer → mid core → per-patch
  einsum tail), NOT a monolithic comb core.
