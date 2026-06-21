---
Rank: 4
ThinkTime: -1
BashTime: -1
GPU: local
NoMemory: on
Skills: common_env, haml_analyze, haml_train, haml_convert
ForceModel: gemma4-thinking
ControlModel: gemma4-thinking
CommonStorage: ro
---

# Reproduce v1_ref — 1-conv HGQ model to bit-exact streaming RTL

## Context

Build, from scratch in this (writable) task directory, a hardware-aware quantized model and its
**bit-exact streaming Verilog**, for a 1-D drift-chamber waveform → scalar hit-count regressor.
You have a three-skill pipeline that encodes the whole recipe — **use it; do not re-derive the
methodology**. The success bar is the bit-exact RTL verification, not matching any specific bit widths
(a fresh train anneals to its own widths — that is fine; the pipeline is width-adaptive).

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


### Architecture to build (the only model-specific part)
```
Input(500) -> Reshape(500,1)
 -> QConv1D(filters=5, kernel_size=25, strides=25, padding='valid', relu,
            parallelization_factor=1, input quantizer FROZEN to 10-bit ADC)
 -> Flatten -> QDense(16,relu) -> QDense(8,relu) -> QDense(1,relu)
```
Target = the 10-bit-digitized `predict500` (scalar). Unconstrained training (plain MSE; no EBOP budget).

## Todo
1. `haml_analyze`: determine the input digitization (10-bit ADC), output format (scalar, n_out=1),
   dataset schema, streaming structure (II = 500/25 = 20), and eval (comb_full golden). Emit
   `spec.json` + `common/sci_io.py`; place `general/`.
2. `haml_train`: adapt the 1-conv simple template to the architecture above; calibrate once on all
   validation data; save `model.keras`.
3. `haml_convert`: decompose (per-window split), build the comb_full golden, compose the hand wrapper,
   and Verilator-verify **bit-exact in both modes**. The Stage A/B/C gates localize any bug.

## Expect
- `model.keras` exists (trained + calibrated).
- Convert gates pass: Stage-1 (comb_full vs keras) ~0 and Stage-2 (per-window) bit-exact 0.0.
- `verify_golden.py --no-pause` AND `--inp-pause 0.3 --seed 42` both print `PASSED: All ... outputs
  match exactly` (scalar, 1 output/sample).
- The streaming RTL composes the da4ml kernel + dense cores under a hand-written `stream_wrapper.v`
  (not a single monolithic comb core).
