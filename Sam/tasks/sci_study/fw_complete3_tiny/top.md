---
Rank: 4
BashTime: -1
NoMemory: on
TaskGroup: real_FW_void
Skills: common_env
CommonStorage: rw
---

# FPGA Stream Wrapper — Both Halves From Scratch

## Context

Streaming inference project under `sim/`. Both `sim/src/stream_wrapper.v` and `sim/stream_wrapper_binder.cc` are empty stubs — write both from scratch. The submodules in `sim/src/` (kernel, dense, etc.) are complete and must not be touched. `sim/verify_golden.py` is the oracle that builds and tests your code against `dataset/`.

The toolchain (verilator, g++, make, python3 with numpy) is on PATH. The task directory is writable.

## Todo

1. Read everything under `sim/` to understand the interfaces and build system.
2. Implement both files.
3. Run `sim/verify_golden.py` in both modes (`--no-pause` and `--inp-pause 0.3 --seed 42`). Both must pass.

## Expect

- Both verify modes print "PASSED: All".
- Only `stream_wrapper.v` and `stream_wrapper_binder.cc` are changed.
