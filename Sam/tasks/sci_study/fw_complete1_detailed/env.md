---
Rank: 1
BashTime: -1
NoMemory: on
---

# env — Verify HGQ toolchain is available

## Context

The HGQ toolchain (verilator, g++, make, python3 with numpy) is pre-installed at `/mnt/envs/hgq` and automatically added to PATH by the driver. Your job is to confirm all four tools are reachable directly via bare command names, and write a status file so downstream subtasks know the environment is ready.

If the tools are NOT in PATH (e.g. because the pre-built env is missing), install into `./mamba_env` as a fallback.

## Todo

1. Run `which verilator g++ make python3` — all four should resolve.
2. Run `verilator --version`, `g++ --version`, `make --version`, and `python3 -c "import numpy; print(numpy.__version__)"` — all four should print successfully.
3. If any of the four tools are missing, install fallback env into `./mamba_env` from conda-forge with `verilator`, `gxx_linux-64`, `make`, `python>=3.10`, `numpy`; symlink `g++`, `gcc`, `c++` to the conda-forge prefixed names; and prepend `./mamba_env/envs/hgq/bin` to PATH via a `source`-able script for subsequent subtasks.
4. Write `env_status.txt` in the parent task directory with the single word `READY` if all four tools work, or `FAIL: <reason>` otherwise.

## Expect

- `env_status.txt` exists in the parent task directory and starts with `READY` or `FAIL:`.
- If `READY`: running `verilator --version` and `python3 -c "import numpy"` directly (no wrapper script) both succeed.
