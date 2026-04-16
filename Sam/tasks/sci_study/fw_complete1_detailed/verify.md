---
Rank: 2
BashTime: -1
NoMemory: on
---

# verify — Drive simulation against golden dataset

## Context

Run the Verilator-built simulation against the golden dataset in two modes and report which one(s) pass. Verification only — do not modify any source.

Toolchain: NOT pre-installed. The parent task or env.md subtask installs it into a local micromamba env. If env.sh exists, it is auto-sourced.

The verify script is `sim/verify_golden.py`. It loads `dataset/golden_X.csv` as inputs, drives them through the Verilator-built shared library, compares outputs to `dataset/golden_Y.csv`, and prints `PASSED: All N outputs match golden reference.` (exit 0) or `FAILED: M/N mismatches` (exit 1).

The two modes that must be tested are:
- `python3 verify_golden.py --no-pause` — `inp_valid` is high every cycle. Easy baseline.
- `python3 verify_golden.py --inp-pause 0.3 --seed 42` — `inp_valid` is randomly low ~30% of cycles. Tests backpressure.

`BashTime: -1` is set because the verify script invokes a Verilator rebuild internally if the .so is missing.

## Todo

1. From `sim/`, run `python3 verify_golden.py --no-pause 2>&1 | tee /tmp/v1.out`. Copy `/tmp/v1.out` to `verify_nopause.log` in the parent task directory. Pass = log contains `PASSED: All` AND exit code 0.
2. From `sim/`, run `python3 verify_golden.py --inp-pause 0.3 --seed 42 2>&1 | tee /tmp/v2.out`. Copy `/tmp/v2.out` to `verify_paused.log`. Same pass criterion.
3. Write `verify_status.txt` in the parent task directory with two lines: `nopause: PASS` (or `FAIL`) and `paused: PASS` (or `FAIL`).

## Expect

- `verify_nopause.log` exists in the parent task directory.
- `verify_paused.log` exists in the parent task directory.
- `verify_status.txt` exists with exactly two lines, each `<mode>: PASS` or `<mode>: FAIL`.
- No file under `sim/src/`, `sim/stream_wrapper_binder.cc`, `sim/build_binder.mk`, or `sim/verify_golden.py` was modified.
