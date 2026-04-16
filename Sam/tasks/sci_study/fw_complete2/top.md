---
Rank: 3
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# FPGA Stream Wrapper — From Scratch

## Context

I have an FPGA project under `sim/`. The outermost module `sim/src/stream_wrapper.v` is empty — just the module declaration and port list (those are locked to the binder, don't touch). The convolution kernel and dense layer submodules in `sim/src/` are done, the C++ binder is done, and there's a python verify script. I need you to write the entire body of `stream_wrapper.v` so the design passes verification.

The toolchain (verilator, g++, make, python3 with numpy) is NOT pre-installed. Install it into a local micromamba env before building:
    MAMBA_ROOT_PREFIX=./mamba_env micromamba create -n hgq -c conda-forge verilator gxx_linux-64 make "python>=3.10" numpy -y
Then write env.sh to put it on PATH. The task directory is writable.

## Todo

1. Look at the empty skeleton, the kernel/dense wrapper modules, and the binder to figure out the parameters.
2. Implement the body of `sim/src/stream_wrapper.v`.
3. Build it and run both verify modes (`--no-pause` and `--inp-pause 0.3 --seed 42`). Both should print "PASSED: All".

## Expect

- Both verify modes print "PASSED: All" against the golden dataset.
- Only `sim/src/stream_wrapper.v` is modified.
