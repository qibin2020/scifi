---
Rank: 2
NoMemory: on
Skills: common_env
CommonStorage: rw
BashTime: -1
---

# FPGA Stream Wrapper

## Context

I'm working on an FPGA Verilog project. Under `sim/` there's a Verilator testbench with a skeleton `stream_wrapper.v` that I haven't finished writing — it has some `...` placeholders where the logic should go. The `sim/src/` folder has the conv kernel and dense layer already done (`kernel_wrapper.v`, `dense_wrapper.v`), and `sim/stream_wrapper_binder.cc` is the C++ binder that drives the simulation. There's a python verify script `sim/verify_golden.py` that runs the sim against a golden dataset in `dataset/`.

Please complete `sim/src/stream_wrapper.v` so the design passes the verify script. The verify script has two modes — a normal one (`--no-pause`) and a harder one that randomly drops the input valid signal (`--inp-pause 0.3 --seed 42`). Both should pass. Don't touch any other files.

The required toolchain is at **prefix** `/mnt/sci_envs/fpga_toolchain` with **env name** `hgq` (full path: `/mnt/sci_envs/fpga_toolchain/envs/hgq`). It contains verilator, g++, make, python3, numpy. Use the common_env skill to discover and activate it; if missing, create it there with the same prefix + env name. The task directory is writable.

## Todo

1. Figure out what the wrapper needs to do and fill in the skeleton.
2. Build it and run the verify script in both modes.
3. Get both modes to pass.

## Expect

- Both verify modes print "PASSED: All" against the golden dataset.
- Only `sim/src/stream_wrapper.v` is modified.
