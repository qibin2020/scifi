---
Rank: 1
BashTime: -1
NoMemory: on
---

# env — Verify HGQ toolchain is available

## Context

The HGQ toolchain (verilator, g++, make, python3 with numpy) is pre-installed at `/mnt/sci_envs/fpga_toolchain`. Use `activate_env` to add it to PATH. Your job is to confirm all four tools are reachable directly via bare command names, and write a status file so downstream subtasks know the environment is ready.

## Todo

1. Use `activate_env(env_path="/mnt/sci_envs/fpga_toolchain/envs/hgq")` to activate the toolchain.
2. Run `which verilator g++ make python3` — all four should resolve.
3. Run `verilator --version`, `g++ --version`, `make --version`, and `python3 -c "import numpy; print(numpy.__version__)"` — all four should print successfully.
4. Write `env_status.txt` in the parent task directory with the single word `READY` if all four tools work, or `FAIL: <reason>` otherwise.

## Expect

- `env_status.txt` exists in the parent task directory and starts with `READY` or `FAIL:`.
- If `READY`: running `verilator --version` and `python3 -c "import numpy"` directly (no wrapper script) both succeed.
