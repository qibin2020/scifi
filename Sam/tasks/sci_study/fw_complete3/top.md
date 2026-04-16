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

I have an FPGA streaming inference project under `sim/`. Both the Verilog wrapper (`sim/src/stream_wrapper.v`) and the C++ binder (`sim/stream_wrapper_binder.cc`) are empty stubs — you need to design and write both from scratch. The conv kernel and dense layer submodules in `sim/src/` are complete and must not be modified. There's a python verify script (`sim/verify_golden.py`) that builds your code via `make -f build_binder.mk slow`, loads the resulting `.so`, calls an `inference` function through ctypes, and checks outputs against a golden dataset in `dataset/`.

The `inference` C function signature is fixed (see the comment at the top of `sim/stream_wrapper_binder.cc`). The verify script expects it exactly as declared there.

The design is a streaming pipeline: the binder feeds 25 ten-bit values per clock into a conv kernel (`kernel_wrapper`, 250-bit input, 90-bit output), you accumulate 20 kernel outputs in a shift register (1800 bits), then a dense layer (`dense_wrapper`) reads the full register and produces a 14-bit output. The binder must handle random input pauses (`inp_pause_prob`) and capture outputs when `out_valid` pulses. Read `sim/ioutil.hh` for bit-packing helpers you can use in the binder.

The Makefile builds with `verilator -Wall`, so handle lint pragmas (`PROCASSINIT`, etc.) and trailing newlines.

The toolchain (verilator, g++, make, python3 with numpy) is on PATH as bare commands. The task directory is writable.

## Todo

1. Read the existing submodules, binder contract, verify script, and build system to understand the interfaces.
2. Design and write both `sim/src/stream_wrapper.v` and `sim/stream_wrapper_binder.cc`.
3. Build and run both verify modes (`--no-pause` and `--inp-pause 0.3 --seed 42`). Both should pass.

## Expect

- Both verify modes print "PASSED: All" against the golden dataset.
- `sim/src/stream_wrapper.v` and `sim/stream_wrapper_binder.cc` are implemented (no longer empty stubs).
- No other files under `sim/src/` are modified.
