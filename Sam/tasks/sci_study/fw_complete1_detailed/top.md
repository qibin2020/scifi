---
Rank: 2
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# Real FW Complete — HGQ Stream Wrapper

## Context

Complete an FPGA-style Verilog design. The starting `sim/src/stream_wrapper.v` is a skeleton with `...` placeholders — you must write the missing logic so the resulting RTL verifies against a golden dataset under two modes (no-pause baseline and 30%-pause backpressure) using Verilator + a Python ctypes binder. The container does not ship with Verilator/g++/make, so the toolchain must be located (or installed) first.

This task is decomposed into four subtasks. The orchestrator (this file) sequences them via `subagent`, reads their status files for routing, and writes a final summary. It does not do any of the actual work — each subtask owns its own domain knowledge.

The four subtasks must run in **strict sequential order** — each one depends on the artifacts produced by the previous one. They cannot be parallelized:

1. `env.md` (Rank 1) — verifies the pre-built toolchain at `/mnt/envs/hgq` (auto-added to PATH by the driver) or falls back to a local install. Produces `env_status.txt` (`READY` or `FAIL: ...`). No prerequisites.
2. `compile.md` (Rank 2) — runs a clean Verilator build of the current `sim/src/stream_wrapper.v`. Produces `compile_status.txt` (`OK` or `FAIL: ...`), plus `compile_ok.log` or `compile_error.log`. Depends on env.md.
3. `verify.md` (Rank 2) — runs the verify script in both modes against the golden dataset. Produces `verify_status.txt` (two lines, `nopause: PASS|FAIL` and `paused: PASS|FAIL`) plus `verify_nopause.log` and `verify_paused.log`. Depends on compile.md being `OK`.
4. `complete.md` (Rank 3) — fills in the skeleton's `...` placeholders so compile and verify both succeed. This is the creative work of the task. Produces the final `nopause.log`, `paused.log`, `design_notes.md`, and `hypothesis_log.md`. Invoked whenever compile failed (including because of the skeleton's placeholders) or any verify mode failed.

Because the starting skeleton has unresolved `...` placeholders, compile.md WILL report `FAIL` on the first pass — that's expected. The orchestrator routes straight to complete.md, which does the actual design work and re-runs both verify modes internally. A "no work needed" short path (where the skeleton happens to compile and verify cleanly without any edits) is NOT expected for this task, but the orchestrator still handles it for symmetry with the debug flow.

The two verify modes referenced throughout are: `python3 verify_golden.py --no-pause` (or `--inp-pause 0.0`, `inp_valid` is high every cycle, easy baseline) and `python3 verify_golden.py --inp-pause 0.3 --seed 42` (`inp_valid` is randomly low ~30% of cycles, tests backpressure).

Files in this task directory:
- `sim/src/stream_wrapper.v` — the skeleton with `...` placeholders that complete.md must fill in.
- `sim/src/{kernel,kernel_wrapper,dense,dense_wrapper}.v` and `sim/src/static/shift_adder.v` — verified RTL, do not modify. These expose the concrete port widths that constrain the shift register size and the output width (read them if you need the ground truth).
- `sim/stream_wrapper_binder.cc`, `sim/ioutil.hh` — Verilator C++ binder (declares `II`, `CHUNK`, `BW_INP`, `BW_OUT` constants that define the streaming protocol). Do not modify.
- `sim/build_binder.mk` — Verilator + g++ build script with `-Wall` enabled. Do not modify.
- `sim/verify_golden.py` — verification driver. Do not modify.
- `dataset/golden_X.csv`, `dataset/golden_Y.csv` — golden test vectors.

**Watch out**: the skeleton contains in-file comments (e.g. "collect 10 kernel outputs", "190 * 10 bits") that may not match the actual module ports. Always cross-check against the concrete port widths in `kernel_wrapper.v` and `dense_wrapper.v` and against the constants in `stream_wrapper_binder.cc` — those are the ground truth. If the comments contradict the wrapper ports, trust the ports.

The base micromamba env (`/F/mamba`) is the driver's and is read-only — never install into it. Always prefer `./` for things the task needs to write. The driver automatically adds `/mnt/envs/hgq/envs/hgq/bin` to PATH so `verilator`, `g++`, `make`, and `python3` (with numpy) are directly callable as bare commands — no wrapper scripts needed. `BashTime: -1` is set because verilator build and verify can each take ~60 seconds.

The orchestrator's deliverables are the canonical end-state files: `nopause.log` (containing `PASSED: All`), `paused.log` (containing `PASSED: All`), and `notes.md` (a one-paragraph summary of the run). When complete.md runs, it produces `nopause.log` and `paused.log` directly. If verify already passes (unexpected for this task but handled for symmetry), the orchestrator copies `verify_nopause.log` → `nopause.log` and `verify_paused.log` → `paused.log`.

## Todo

1. `subagent("env.md")`.
2. `subagent("compile.md")`. Read `compile_status.txt`.
3. If `compile_status.txt` starts with `FAIL` (the expected path for this task given the skeleton holes): skip verify and `subagent("complete.md")` directly. complete.md reads the compile error and fills in the skeleton.
4. Otherwise `subagent("verify.md")`. Read `verify_status.txt`.
5. If both modes are `PASS` (unexpected but possible): copy `verify_nopause.log` → `nopause.log` and `verify_paused.log` → `paused.log`.
6. Otherwise `subagent("complete.md")`.
7. Write `notes.md` with one paragraph: which path was taken, what complete.md did (if invoked), and the final outcome (success / partial / unresolved).

## Expect

- `nopause.log` exists in the task directory and contains `PASSED: All`.
- `paused.log` exists in the task directory and contains `PASSED: All`.
- `notes.md` exists with a one-paragraph run summary.
