---
name: haml_convert
description: Step 3 of hardware-aware ML -> bit-exact streaming RTL. Convert a trained HGQ model to streaming Verilog — decompose into da4ml kernel cores, build the comb_full software golden, compose a hand-written top wrapper, and drive Verilator to verify BIT-EXACT in no-pause AND backpressured modes. Reuses the bundled general/ library; multi-step gates early-stop for debugging. Use after haml_train.
---

You are writing the **convert + verify** stage: da4ml converts the *kernels*; you hack `comb_full`
as the end-to-end software golden; you hand-write the streaming top that *composes* the cores; Verilator
verifies the composed RTL end-to-end. Each step is a **gate that early-stops for debugging**. Read
`spec.json` first. Worked, verified sources: `SciFi_v2_RTL/v1_ref` (1conv) and `v3_ref` (2conv+einsum).

## Reuse vs case-by-case (the core principle)
- **`general/` is the reusable kernel — never rewrite it.** It's bundled at `assets/general/`
  (`hgq_rtl.py`: env, calibrate, `predict_raw`, `emit_core`, **`comb_full_golden`** = the golden;
  `harness/`: `verify_golden.py` AXIS driver, generic config-driven `stream_binder.hh`, `build_binder.mk`,
  `ioutil.hh`, da4ml static lib). haml_analyze already copied it to `<proj>/general/`; if absent,
  `cp -r "${SKILLS_DIR:-/srv/skills}/haml_convert/assets/general" <proj>/general` and
  `cp "${SKILLS_DIR:-/srv/skills}/haml_convert/assets/common/gen_golden.py" <proj>/common/`.
- **Case-by-case = `convert.py` (decomposition + tail derivation), `wrap/stream_wrapper.v` (hand top),
  `assemble_wrap.py` (width-adaptive patcher).** Adapt the matching templates; the wrapper + binder are
  parametric and patched from `convert_meta.json`, so they are width-adaptive across re-trains.

Templates by `spec.topology`:
| | convert | wrapper+binder | assemble |
|---|---|---|---|
| `1conv_simple` | `convert_1conv.py` | `wrap_1conv/` | `assemble_1conv.py` |
| `2conv_einsum` | `convert_2conv_einsum.py` | `wrap_2conv/` | `assemble_2conv.py` |

Lay out `<proj>/<model>/` = `convert.py` + `assemble_wrap.py` + `wrap/{stream_wrapper.v,binder.cc}` +
`run_all.sh` (template). Then run the pipeline.

## The pipeline (train -> convert -> gen_golden -> assemble -> verify)
`run_all.sh` chains: `python3 convert.py` → `python3 ../common/gen_golden.py` → `python3 assemble_wrap.py`
→ `cd wrap_pkg/sim && python3 verify_golden.py --no-pause` and `--inp-pause 0.3 --seed 42`.

### Multi-step validation GATES (each can early-stop -> localize the bug to pure Python, no Verilog)
- **Stage A/B** — each da4ml core (per-window kernel; 3-window mid) vs the keras sub-model: ~0 / bit-exact.
- **Stage C** — the FULL chain (cores → hand tail) reproduces `comb_full` **bit-exact** (e.g. 1280/1280).
  `convert.py` ASSERTS this before any Verilog is emitted. If it fails, the tail derivation is wrong —
  fix it here, not in Verilog.
- **golden** = `general.comb_full_golden(model, x)` — whole-model da4ml comb (bit-exact to keras),
  **sign-corrected** (the raw is an unsigned bit pattern; `oq` is signed). per-sample shape = `n_out`.
- **verify** — the Verilator-compiled wrapper reproduces the golden bit-exactly in both modes.

## Decomposition recipes
**1conv (simple):** per-WINDOW split — trace ONE `patch_size`-sample conv window (`inp0[:patch_size]`,
`out0[:filters]*output_msk`) and reuse it `II` times; NEVER the monolithic full conv. Wrapper = a shift
register accumulating `II` kernel outputs (new output into the HIGH bits) feeding the dense core; output
scalar. Width invariant: `dense_in == II * kernel_out`.

**2conv + einsum (complex):** kernel core (one patch, conv1) + 3-window MID core (conv2 `padding='same'`
+ DNN, traced with a 3-window stacked input, middle patch kept). Per-patch output. Wrapper = a
`3*kernel_out` shift buffer (newest-into-HIGH) → mid core → per-patch **einsum tail** → `N_PATCHES`
outputs/sample. Width invariant: `mid_in == 3 * kernel_out`.

### Einsum tail — the EXACT general arithmetic (do not re-derive from scratch)
`out = oq( iq(mid) * kq(scale) + bias )`, per patch, all integer:
```
q    = clip( round(mid / 2^REQ_SHIFT), 0, 2^Q_BITS-1 )     # REQ_SHIFT = F_MID - IQ_F ; ROUND = half-UP (RND)
prod = round( (q * scale_int) / 2^PROD_SHIFT )             # PROD_SHIFT = IQ_F + KF - OQ_F (may be <=0); SIGNED scale
out  = clip( prod + bias_int, OUT_MIN, OUT_MAX )           # bias_int = round(b * 2^OQ_F) ; oq SAT (signed)
```
`scale_int = round(s * 2^KF)` (signed if kq is signed); LUTs (`scale_lut.mem`, `bias_lut.mem`) indexed by
`patch_idx`. Read `IQ_F,Q_BITS` from `esd.iq`, `KF/sign` from `esd.kq`, `OQ_*` from `comb_full`'s output kif.

## GOTCHA LEDGER (every one of these was a real bug — honor them)
1. **Rounding is RND (round-half-UP), not Python `round()` (half-to-even).** They differ only at exact
   `.5` ties (≈1-in-1000) — but that one tie fails Stage C. Use `floor(x + 0.5)` in Python and
   `(x + half) >> shift` in RTL, everywhere (iq requant AND the product shift).
2. **PAD = ZERO kernel outputs, not `kernel(0)`.** conv2 `padding='same'` boundaries need zeros in the
   *kernel-output* space. The wrapper pushes literal 0 into the shift buffer on the flush cycles
   (`cnt >= N_PATCHES`); feeding a zero *input* window through the kernel core gives `kernel(0) != 0` and
   corrupts the boundary patches. (This was a 90/100 fail localized to patches 0 and N-1.)
3. **Sign-correct the golden.** `comb_full.predict_raw` returns the unsigned bit pattern; `oq` is signed —
   `general.comb_full_golden` already applies `((raw + half) % full - half)`. The RTL/binder sign-extend.
4. **Calibrate once (train), never re-calibrate in convert/gen_golden** — they load the saved model as-is.
5. **Widths are per-model.** `assemble_wrap.py` derives every wrapper param + binder constant + LUT from
   `convert_meta.json`. Never hardcode reference numbers — a fresh train anneals to different widths.
6. **`general/harness/stream_binder.hh` is generic** — the binder.cc is a thin CFG (CHUNK/BW_INP/WINDOWS/
   N_FLUSH/OUT_PER_SAMPLE/BW_OUT/SIGNED_OUT); assemble patches it. One template serves scalar + per-patch.

## Generalizing to NEW architectures (more convs, other tails)
Follow the same shape: trace each reusable sub-block as one da4ml core, validate it (Stage A/B) against
its keras sub-model, compose them in the hand wrapper with the right shift-buffer depth, pull any
per-index tail (scale/bias LUTs) out of the trace, and gate on **Stage C (chain == comb_full) before
emitting Verilog**. The convert_meta + width-adaptive assemble pattern carries any widths.

## Output
`wrap_pkg/sim/` with the verified `.so`; both `verify_golden.py` modes print `PASSED: All N outputs
match exactly`. That is the bit-exact streaming RTL for the trained (optionally resource-constrained) model.
