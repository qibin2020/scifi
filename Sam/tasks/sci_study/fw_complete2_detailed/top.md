---
Rank: 3
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# Real FW Empty — HGQ Stream Wrapper From Scratch

## Context

Implement an FPGA-style Verilog design for a streaming inference pipeline. The starting `sim/src/stream_wrapper.v` is an EMPTY skeleton — only the module declaration and port list are provided (these are locked to the Verilator binder and must not change). You write the entire module body from scratch.

The design composes two pre-built combinational submodules into a streaming datapath:
- `sim/src/kernel_wrapper.v`: combinational convolution kernel
- `sim/src/dense_wrapper.v`: combinational dense (fully-connected) layer

Between them you need a shift register that buffers kernel outputs over II valid input cycles, and control logic that pulses `out_valid` exactly once when the dense layer's output is ready. The verifier (`sim/verify_golden.py`) runs the simulation in two modes — baseline (`--no-pause`) and backpressure (`--inp-pause 0.3 --seed 42`). Both must pass against the golden dataset in `dataset/`.

The toolchain (verilator, g++, make, python3 with numpy) is NOT pre-installed. Install into a local micromamba env first:
    MAMBA_ROOT_PREFIX=./mamba_env micromamba create -n hgq -c conda-forge verilator gxx_linux-64 make "python>=3.10" numpy -y
Then write env.sh to put it on PATH.

## Todo

1. Read the empty skeleton in `sim/src/stream_wrapper.v` to see the locked port interface.
2. Read `sim/src/kernel_wrapper.v` and `sim/src/dense_wrapper.v` to derive the actual port widths.
3. Read `sim/stream_wrapper_binder.cc` to understand the testbench protocol (II value, CHUNK, BW_INP, BW_OUT).
4. Design and implement the body of stream_wrapper.v.
5. Build with `make -f build_binder.mk slow` from `sim/`.
6. Run both verify modes; both must print "PASSED: All".

## Expect

- `nopause.log` exists in the task directory and contains "PASSED: All"
- `paused.log` exists in the task directory and contains "PASSED: All"
- `notes.md` exists with a one-paragraph summary of the design and verification result
- Only `sim/src/stream_wrapper.v` was modified; all other files in `sim/` are unchanged
