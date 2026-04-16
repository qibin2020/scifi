---
Rank: 1
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# FW Bootstrap — Install Verilator Toolchain

## Context
Set up the shared FPGA toolchain at /mnt/sci_envs/ so all subsequent FW tasks
can use it immediately. This task does NOT do any Verilog work — it only
installs and verifies the toolchain.

## Todo
1. Use the common_env skill to create a shared env with: verilator, gxx_linux-64, make, python>=3.10, numpy
2. Verify all four tools work: `verilator --version`, `g++ --version`, `make --version`, `python3 -c "import numpy"`
3. Write the verified versions to `toolchain_versions.txt`

## Expect
- `toolchain_versions.txt` exists with version strings for verilator, g++, make, numpy
- The environment is at /mnt/sci_envs/ (not local ./)
