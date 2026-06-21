---
name: haml_train
description: Step 2 of hardware-aware ML -> bit-exact streaming RTL. Write + run HGQ quantization-aware training for FPGA deployment, optionally resource-constrained to an EBOP/LUT budget via BetaPID + ParetoFront. Consumes spec.json + common/sci_io.py (from haml_analyze); produces a calibrated model.keras. Use after haml_analyze, before haml_convert.
---

You are writing the **training** stage. The model architecture is case-by-case, so you ADAPT a
template (`templates/`) rather than write from scratch. Read `spec.json` first.

Templates (pick by `spec.topology` × whether `spec.targets.ebops` is set):
| topology | unconstrained | EBOP-constrained (PID+Pareto) |
|---|---|---|
| `1conv_simple` | `train_1conv_simple.py` | `train_1conv_optimized.py` |
| `2conv_einsum` | `train_2conv_simple.py` | `train_2conv_optimized.py` |

Copy the chosen template to `<proj>/<model>/train.py`, then edit the model block to your architecture.

## NON-NEGOTIABLE invariants (these make the RTL convert bit-exact later)
1. **`parallelization_factor=1` on every QConv1D** — MUST be set at train time. Lets convert slice one
   conv *window* and reuse it; without it the convert unrolls the whole conv and the streaming wrap breaks.
2. **Freeze the input quantizer to the ADC**: `QuantizerConfig(k0=False, i0=BW_INP, b0=BW_INP,
   round_mode='TRN', overflow_mode='WRAP', trainable=False)` passed as `iq_conf` to the first conv.
3. **Calibrate ONCE on ALL validation data** after fit: `trace_minmax(model, sci_io.load_val_x(),
   reset=True)`, then `model.save('model.keras')`. **Never re-calibrate downstream** — the saved
   calibration round-trips through `.keras`, and re-tracing on a different subset silently changes the
   output bit width.
4. `enable_ebops=True` (via `LayerConfigScope`) so EBOPs (≈ LUT/DSP cost) are tracked.
5. Targets for `QEinsumDense` tails use `kernel_initializer='ones'` + homogeneous kq/bq configs.

## Resource-constrained training (when `spec.targets.ebops` is set) — PID + Pareto
The `*_optimized.py` templates add three `hgq.utils.sugar` callbacks:
- **`FreeEBOPs()`** — logs total EBOPs each epoch (so BetaPID + ParetoFront can read it).
- **`BetaPID(TARGET_EBOPS, init_beta=1e-7, warmup=W)`** — PID controller; holds `beta` at `init_beta`
  until epoch `W`, then anneals it (log-space) to drive `ebops → TARGET_EBOPS`. **`warmup` is in EPOCHS.**
- **`ParetoFront(dir, ['val_mae','ebops'], [-1,-1])`** — saves the accuracy↔EBOPs front (minimize both).

After `fit`, **select the most-accurate model WITHIN the budget** from the front (`pareto.record`/`.paths`):
`within = ebops <= 1.1*TARGET; pick lowest val_mae in within, else fallback to lowest ebops`. Load it,
calibrate on all val, save.

Set the knobs from the spec/user:
- `TARGET_EBOPS` = the LUT/DSP budget. Lower ⇒ smaller cores, lower accuracy.
- **`EPOCHS ≫ WARMUP`** — to actually REACH a tight target the PID needs many post-warmup epochs.
  (Empirically: target ~3k needed ~1500 epochs; target ~1.5k needed ~4000 epochs. 1500 only got partway.)
- If `spec.targets.perf_mae` is set, treat it as the accuracy floor when picking from the front (don't
  select a model worse than it; if none qualify, raise `TARGET_EBOPS`).

## Run
```
export SCIFI_DEBUG=1   # optional: tiny data + few epochs to smoke-test the script first
export CUDA_VISIBLE_DEVICES=N
python3 train.py
```
First epoch pays a one-time XLA GPU compile (~minutes); later epochs are ~ms. The templates respect
`CUDA_VISIBLE_DEVICES` and do not preallocate the card (so several models can train on different GPUs).

## Output / hand-off
`model.keras` (calibrated) + `train_status.txt`. The output bit width is whatever the model annealed
to — convert reads it. Hand off to **`haml_convert`**.

## Worked examples
`SciFi_v2_RTL/v1_ref` (plain) and `v1_opt2`/`v3_opt2` (PID+Pareto, 1.5k-EBOP) are the exact, verified
sources of these templates.
