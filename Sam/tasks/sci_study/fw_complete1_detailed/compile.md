---
Rank: 2
BashTime: -1
NoMemory: on
---

# compile — Verify stream_wrapper compiles

## Context

Run a clean Verilator + g++ build of the current `sim/src/stream_wrapper.v` and report whether the build succeeds. This is a build-only check — do not run any verification, do not modify any source.

Toolchain: NOT pre-installed. The parent task or env.md subtask installs it into a local micromamba env. If env.sh exists, it is auto-sourced.

Build driver: `make -f build_binder.mk` from inside `sim/`. Target `clean` wipes prior state, target `slow` performs a clean Verilator + g++ build. On success the build leaves a `libstream_wrapper_*.so` file in `sim/`.

The starting `stream_wrapper.v` contains `...` placeholders (it's a skeleton for the parent task's design work). As a result, the build is expected to fail on this first pass with Verilog syntax errors. Capture the errors faithfully — the complete.md subtask needs them as the diagnosis input.

`BashTime: -1` is set because the build can take 30-90 seconds (when it does succeed).

## Todo

1. From `sim/`, run `make -f build_binder.mk clean` followed by `make -f build_binder.mk slow 2>&1 | tee /tmp/build.out`.
2. If the build succeeded (a `libstream_wrapper_*.so` exists in `sim/`): write `OK` to `compile_status.txt` in the parent task directory and copy `/tmp/build.out` to `compile_ok.log`.
3. If the build failed: write `FAIL: <one-line reason>` to `compile_status.txt` and copy `/tmp/build.out` to `compile_error.log` (full output with all warnings, errors, file/line references).

## Expect

- `compile_status.txt` exists in the parent task directory and starts with either `OK` or `FAIL:`.
- If `OK`: a `libstream_wrapper_*.so` file exists under `sim/` and `compile_ok.log` exists.
- If `FAIL`: `compile_error.log` exists with the full build error output.
- No file under `sim/src/`, `sim/stream_wrapper_binder.cc`, `sim/build_binder.mk`, or `sim/verify_golden.py` was modified.
