---
Rank: 3
BashTime: -1
ThinkTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# FW Debug — Verify HGQ Stream Wrapper

## Context

FPGA Verilog project under `sim/`. A streaming wrapper (`stream_wrapper.v`) chains a conv kernel and dense layer through a shift register. There's a Verilator C++ binder, a Python verify script, and golden data in `dataset/`.

The design in `sim/src/stream_wrapper.v` is pre-written. Set up a verilator toolchain, build it, and run the verify script. If anything fails, fix only `stream_wrapper.v`. Don't touch other files.

Use the `common_env` skill to set up a shared env with the needed toolchain. Write `env_activate.sh` so future tasks can reuse it.

## Todo

1. Set up toolchain via `common_env` skill, write `env_activate.sh`.
2. Build and verify. Fix `stream_wrapper.v` if needed.
3. Both verify modes must pass.

## Expect

- `nopause.log` and `paused.log` both contain `PASSED: All`
- `notes.md` exists with a summary
- Only `sim/src/stream_wrapper.v` modified under `sim/` (if needed)
