---
name: haml_analyze
description: Step 1 of hardware-aware ML -> bit-exact streaming RTL (HGQ -> da4ml -> Verilog). Analyze a quantized-NN-on-FPGA task — input digitization, output format, dataset schema, streaming structure, evaluation — and emit spec.json + common/sci_io.py that the haml_train and haml_convert skills consume. Use at the START of any such project.
---

You are bootstrapping a **hardware-aware ML → bit-exact RTL** project. The full pipeline is three
skills: **`haml_analyze` (this) → `haml_train` → `haml_convert`**. Your job here is to pin down the
*input / output / data / evaluation* so the later steps have everything they need, and to lay out
the shared project skeleton.

Worked end-to-end reference (six verified packages): `/pscratch/sd/b/binus/Playground/AI_SciFi/SciFi_v2_RTL`.

## What you produce (the hand-off contract)
1. **`spec.json`** — the single source of truth for IO/data/eval/targets. Schema + a filled example:
   `assets/spec.example.json`. Every later skill reads this.
2. **`common/sci_io.py`** — the project's I/O module (ADC digitization + dataset schema), filled from
   `assets/sci_io_template.py`. Imported by both train and convert. Self-contained (numpy + h5py).
3. **`<proj>/general/`** — copy the reusable library bundled in the `haml_convert` skill. In this
   harness the skills are injected read-only at **`$SKILLS_DIR` (= `/srv/skills`)**, so:
   `cp -r "${SKILLS_DIR:-/srv/skills}/haml_convert/assets/general" <proj>/general` and
   `cp "${SKILLS_DIR:-/srv/skills}/haml_convert/assets/common/gen_golden.py" <proj>/common/`.
   (Do NOT search the filesystem for `general/` — it is right here in the skill assets.)

Project layout the templates assume (keep it exactly — the scripts resolve `general`/`common` by
`parent.parent`):
```
<proj>/general/      (copied)     <proj>/common/sci_io.py, gen_golden.py
<proj>/<model>/      train.py, convert.py, assemble_wrap.py, wrap/, run_all.sh   (later skills)
<proj>/spec.json
```

## Steps
1. **Inspect the dataset.** Open the h5 files; record keys + shapes. Identify the input signal array
   (`x_key`, shape `(N, input_len)`) and the target (`y_key`, and whether the model output is a
   **scalar per sample** or a **per-element/per-patch vector**).
2. **Input digitization.** The model's front-end is a fixed integer ADC. Determine `bw_inp =
   ceil(log2(#codes))` and the calibration window `(vmin, vmax)` so `re_digi(x,vmin,vmax,bw_inp)`
   maps raw inputs to codes `[0, 2^bw_inp)`. (SciFi: vmin=-0.2, vmax=40, bits=10.)
3. **Output format.** Set `output.kind` = `scalar` or `per_patch`, and `n_out`. **Do NOT try to fix
   the output bit width / signedness here** — those are read off the *trained* model's output
   quantizer (`comb_full`) at convert time. Just record the shape/kind.
4. **Streaming structure.** `ii = input_len / patch_size`; `patch_size` = the first conv's kernel/stride.
   Set `conv2_window > 1` **only if** a second conv with `padding='same'` mixes neighbor patches
   (that triggers the 3-window shift buffer + per-patch einsum tail in convert). Pick `topology`:
   `1conv_simple` or `2conv_einsum`.
5. **Evaluation.** Metric (mae/mse) + note the golden is da4ml `comb_full` (bit-exact to keras), and
   the RTL must match it bit-exactly in **both** no-pause and backpressured modes.
6. **Targets (optional).** If the user gave an EBOP/LUT budget or an accuracy floor, fill
   `targets.ebops` / `targets.perf_mae` (these switch on PID+Pareto in haml_train). Else leave null.
7. **Write `spec.json`** (from the example schema) and **fill `common/sci_io.py`** from the template
   (every `<FILL ...>` from the spec). Copy `general/` + `gen_golden.py` into place.
   **CONTRACT — do NOT change the function signatures in `sci_io.py`.** `haml_train` and `haml_convert`
   call them positionally and verbatim: `PRO_X(x)`, `PRO_Y(x)`, and **`load_val_x(n=None, split='val')`**
   (e.g. `S.load_val_x()` for calibration, `S.load_val_x(4096)` for the gates). Only fill the `<FILL ...>`
   constants / body — keep the names and argument lists EXACTLY. Adding a parameter (e.g. `load_val_x(spec, n)`)
   silently breaks every downstream `convert.py`/`train.py` call and sends you into a debugging cascade.

## Notes
- `re_digi`/`PRO_X` must be **identical** everywhere (train calibration, convert tracing, golden) — that
  is why it lives once in `common/sci_io.py`.
- If the task is not waveform→count (different modality), keep the same spec structure; only the
  digitization and schema change.
- Hand off to **`haml_train`** next.
