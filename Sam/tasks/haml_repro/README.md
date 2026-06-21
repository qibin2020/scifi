# haml_repro — can the `haml_*` skills reproduce the 6 RTL packages?

Six self-contained scifi tasks that test whether an agent, given **only the three `haml_*` skills and
NO global memory** (`NoMemory: on`), can take a model from architecture spec → HGQ training → da4ml
conversion → **bit-exact streaming Verilog** (verified in no-pause AND backpressured modes). Each task
targets one of the six verified packages under `SciFi_v2_RTL/`.

| task | topology | EBOP budget | reference package | hardest part |
|---|---|---|---|---|
| `repro_v1_ref`  | 1-conv → DNN (scalar) | none | `v1_ref`  | per-window split + shift-reg wrap |
| `repro_v3_ref`  | 2-conv → DNN → einsum (per-patch) | none | `v3_ref`  | 3-window buffer + per-patch einsum tail |
| `repro_v1_opt`  | 1-conv | 3000 | `v1_opt`  | PID+Pareto resource drive |
| `repro_v3_opt`  | 2-conv | 3000 | `v3_opt`  | PID+Pareto + einsum tail |
| `repro_v1_opt2` | 1-conv | 1500 | `v1_opt2` | tight budget (EPOCHS≫warmup) |
| `repro_v3_opt2` | 2-conv | 1500 | `v3_opt2` | tight budget + einsum tail |

## What "reproduce" means
The success bar is the **bit-exact RTL verification** (the convert Stage A/B/C gates + `verify_golden.py`
both modes), NOT byte-matching the package files — a fresh train anneals to its own bit widths and the
pipeline is width-adaptive. For the `_opt*` tasks, success additionally requires the PID+Pareto callbacks
to have run and the EBOPs to be clearly reduced (near the budget for `opt2`).

## What this exercises in the skills
- **`haml_analyze`** — derive digitization / output kind / streaming structure / targets → `spec.json`.
- **`haml_train`** — adapt the right template; recognize the EBOP target → PID + Pareto; calibrate once.
- **`haml_convert`** — decompose to da4ml cores, comb_full golden, hand wrapper, Verilator verify; the
  gotcha ledger (RND rounding, PAD=zero-kernel-output, sign-corrected golden, `PROD_SHIFT` signed tail)
  and the Stage-C early-stop gate are the difference between pass and fail.

## Env / data (shared `/mnt`, no hardcoded host paths)
Toolchain is a **shared `common_env`** at `/mnt/sci_envs/fpga_toolchain/envs/hgq`
(jax-cuda13/keras/hgq/da4ml/h5py/verilator), built once by the **`haml_bootstrap`** task and then
discovered + activated by each repro task (`list_shared_envs` -> `activate_env`). Data is a reduced
20k-row copy on the shared store: `/mnt/sci_shared/data/{train,val}_v3.h5` (driver auto-maps `/mnt`
via `CommonStorage`). Tasks run on a local GPU; at reduced eval scale a full run is ~3-13 min
(`BashTime: -1`). Model is pinned in each task's frontmatter: repro tasks use `ForceModel:
gemma4-thinking`; `haml_bootstrap` uses `ForceModel: gemma4` (non-thinking — thinking loops on env
discovery).

Worked, verified solutions live at `SciFi_v2_RTL/v{1,3}_{ref,opt,opt2}` (do not expose them to the
agent under test — `NoMemory: on` keeps the clean-room fair).

## Two benchmark tables

**`benchmark_reduced.csv`** — the *agent-reproduction* test (gemma4-thinking, no-hardcoded-path version,
2026-06-19). All 6 reproduce **bit-exact** (`[review] PASS`, both no-pause + backpressured modes) at
reduced/debug training scale (~10-15 epochs — fast, since bit-exactness is scale-independent). Run a task
with `./SciF RUN haml_repro/<task>` (model is baked into the frontmatter). A fresh `./SciF RUN` is the
best reset for a flaky draw; v1_opt2 needed 2 attempts, the rest passed first try.

**`benchmark.csv`** — the *full-scale performance* table (2026-06-19). The six reference configs trained
on the FULL dataset (500k) at production epochs (1000 / 1500 / 4000), measured directly (no agent — clean
timing) on 4× A100. Columns: **training time, MSE, MAE, EBOPs** (+ ebop_target, epochs). Highlights:

| config | epochs | train_min | MSE | MAE | EBOPs |
|---|---|---|---|---|---|
| v1_ref  | 1000 | 13.3 | 4.21 | 1.60 | 257,287 |
| v3_ref  | 1000 | 14.9 | 0.18 | 0.21 | 41,179 |
| v1_opt  | 1500 | 21.9 | 4.83 | 1.71 | 22,594 |
| v3_opt  | 1500 | 25.0 | 0.31 | 0.30 | 39,144 |
| v1_opt2 | 4000 | 53.4 | 6.71 | 2.03 | 1,668 |
| v3_opt2 | 4000 | 61.8 | 0.26 | 0.30 | 7,570 |

Full-scale MAE matches the references (v1 ~1.55→1.76→1.94 as the EBOP budget tightens — a clean
accuracy↔resource Pareto tradeoff; v1_ref→v1_opt2 is a **154× EBOP reduction** for +0.43 MAE). The
v3 einsum model resists compression (floors ~7.6k EBOPs). Bit-exactness is scale-independent and is
verified in the reduced-scale table; these full-scale models use the identical (verified) topologies.
