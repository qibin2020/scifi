---
Rank: 2
BashTime: -1
NoMemory: on
---

# complete — Fill in the stream_wrapper skeleton

## Context

The starting `sim/src/stream_wrapper.v` is a **skeleton with `...` placeholders** (localparam value, registers, always blocks, control logic, output assignment). Your job is to complete the design so it compiles cleanly under Verilator `-Wall` AND both verify modes pass against the golden dataset.

This is design work, not bug hunting. The only file you may modify is `sim/src/stream_wrapper.v`. All other files (kernel*.v, dense*.v, shift_adder.v, the binder, the Makefile, the verify script) are authoritative and must not change.

### Toolchain

`The toolchain is NOT pre-installed — install via micromamba or check if env.sh was written by an earlier subtask.

### The design

A `stream_wrapper` module that composes a combinational conv kernel and a combinational dense layer using a shift register. The conv kernel takes a chunk of input per cycle and produces an intermediate feature; those intermediates are accumulated in a shift register across `II` valid cycles; when the shift register is full, the dense layer (combinational over the full shift register width) produces the sample output. `out_valid` must pulse for exactly one cycle per completed sample.

### Ground truth — read these to get the concrete numbers

Never trust the skeleton's in-line comments (e.g. "collect 10 kernel outputs", "190 * 10 bits") — they may be stale or misleading. Derive dimensions from these authoritative sources:

- `sim/src/kernel_wrapper.v` — declares the kernel's input and output widths. The output width is your `KERNEL_OUTPUT_BIT`.
- `sim/src/dense_wrapper.v` — declares the dense layer's input and output widths. The dense layer's input width is the required `SHIFT_REG_WIDTH`. The output width is the raw dense output before zero-extension to 32 bits.
- `sim/stream_wrapper_binder.cc` — declares `II`, `CHUNK`, `BW_INP`, `BW_OUT`. `II` is the number of valid input cycles per sample (= the number of kernel outputs that must fit in the shift register). `BW_OUT` is the output bit-width that the binder reads back.

From these three sources you can compute: `SHIFT_REG_WIDTH = II * KERNEL_OUTPUT_BIT`. Verify: this must equal the `dense_wrapper` input port width. If it does not, your reading is wrong.

### What the skeleton is missing (checklist)

- The value of `SHIFT_REG_WIDTH` (currently `...`).
- The `always @(posedge clk)` block that advances the shift register when `inp_valid` is high (otherwise holds state, so paused cycles don't corrupt accumulation). The new kernel output becomes the newest slot; older values shift toward the oldest slot.
- The control logic: a counter `cnt` that counts valid inputs modulo `II` (0..II-1, wraps), and registered `out_valid` that asserts for exactly one cycle after the II-th valid input, with no state update on paused cycles.
- The output assign: `model_out` is 32 bits wide but the dense layer produces `BW_OUT` (14) bits. Zero-extend.

### Verilator -Wall strictness

The Makefile uses `-Wall`, which upgrades warnings to errors. You MUST handle:

- **`PROCASSINIT`** — the single trickiest issue. A `reg` with both a declaration-time initializer (`= 1'b0`, `= 5'd0`, `= {...{1'b0}}`) AND a procedural assignment in an `always` block triggers this warning. Verilator reports TWO line numbers per warning: the declaration line and the procedural-assignment line. A `lint_off` pragma must cover BOTH locations.

  **The only reliable fix**: put `/* verilator lint_off PROCASSINIT */` on the line immediately after `` `timescale 1 ns / 1 ps `` (BEFORE the `module` declaration), and put `/* verilator lint_on PROCASSINIT */` on the line immediately after `endmodule`. Wrapping only the `always` block is NOT enough — the warning is tied to the declaration location.

- `UNUSEDSIGNAL` — already handled for `model_inp`/`inp_valid` via existing lint pragmas in the file header; leave those alone.
- `WIDTHEXPAND` — implicit width mismatch in assigns. Be explicit: `5'd0`, `5'd19`, `{(32-OUTPUT_ACTUAL){1'b0}}`. When comparing a narrow register to a localparam, cast explicitly (e.g. `cnt == 5'd19` not `cnt == II-1` where `II` is an untyped integer localparam).
- `LATCH` — an `always` block that doesn't cover all branches may infer a latch. Use `<=` on every path or add a default.

### Anti-loop discipline (mandatory)

The failure mode is "write some code → compile → fix symptoms → compile → fix other symptoms" forever. Prevent it:

1. BEFORE writing code, read the three ground-truth files (`kernel_wrapper.v`, `dense_wrapper.v`, `stream_wrapper_binder.cc`) and write a short **design plan** to `hypothesis_log.md` containing: the concrete numeric values of `KERNEL_OUTPUT_BIT`, dense input width, `II`, `BW_OUT`; the resulting `SHIFT_REG_WIDTH` computation; the counter wrap value; the `out_valid` timing.
2. Then write the full completed `stream_wrapper.v` in one edit. Fill every `...`. Don't incrementally patch.
3. Build: from `sim/`, run `make -f build_binder.mk clean && make -f build_binder.mk slow 2>&1`. If the build fails, read the Verilator errors carefully and write **Hypothesis N** to `hypothesis_log.md` describing what was wrong and what one-line-summary change you'll make. Then apply the change and rebuild.
4. Once the build succeeds, run BOTH verify modes from `sim/`:
   - `python3 verify_golden.py --no-pause 2>&1 | tee /tmp/v1.out`
   - `python3 verify_golden.py --inp-pause 0.3 --seed 42 2>&1 | tee /tmp/v2.out`
   - Copy `/tmp/v1.out` to `../nopause.log` and `/tmp/v2.out` to `../paused.log`.
5. **Verify success by reading the log files yourself**: run `grep "PASSED: All" nopause.log paused.log` (from the task root). You MUST see two lines, one for each file, each containing `PASSED: All`. If the grep returns fewer than two matches, you have NOT succeeded — go back to step 3.
6. If either mode fails the golden match, that's a logic bug — write a new hypothesis, fix, rebuild, re-run BOTH modes.
7. **Hard limit: 5 distinct hypothesis iterations** after the first compile attempt. If still failing, call done with `partial:` and a detailed description.

Do NOT write `design_notes.md` or call `done` until step 5's grep returns two `PASSED: All` lines. Claiming success without verified logs is a failure mode the reviewer WILL catch.

## Todo

1. Read `sim/src/kernel_wrapper.v`, `sim/src/dense_wrapper.v`, and `sim/stream_wrapper_binder.cc`. Write concrete numbers (`KERNEL_OUTPUT_BIT`, dense input width, dense output width, `II`, `BW_OUT`) and the computed `SHIFT_REG_WIDTH = II * KERNEL_OUTPUT_BIT` to `hypothesis_log.md` under `## Design plan`.
2. Read `sim/src/stream_wrapper.v` to see exactly where the `...` placeholders are.
3. Write the completed `sim/src/stream_wrapper.v` in one edit. Put `/* verilator lint_off PROCASSINIT */` after the timescale (before `module`) and `/* verilator lint_on PROCASSINIT */` after `endmodule`.
4. From `sim/`, run `make -f build_binder.mk clean && make -f build_binder.mk slow 2>&1`. If it fails, append Hypothesis 1 to `hypothesis_log.md` with the specific error and your fix, apply the fix, rebuild. Repeat until the build succeeds.
5. Run BOTH verify modes from `sim/` and copy stdout to `nopause.log` and `paused.log` in the parent task directory (see Context step 4 for exact commands).
6. From the task root, run `grep "PASSED: All" nopause.log paused.log`. If fewer than two matches, the task is NOT done — form a new hypothesis and repeat from step 3 or 4 as appropriate.
7. When step 6 returns two `PASSED: All` lines, write `design_notes.md` describing the final `SHIFT_REG_WIDTH`, `II`, shift direction, `out_valid` timing, pause handling, and lint pragma placement.

## Expect

- `hypothesis_log.md` exists in the parent task directory with a Design plan section and at least one hypothesis block.
- One of two terminal states:
  - **Success**: `nopause.log` and `paused.log` both exist in the parent task directory and both contain the literal string `PASSED: All`, AND `design_notes.md` exists with the final design description.
  - **Escape**: up to 5 hypothesis blocks in `hypothesis_log.md`, `design_notes.md` documenting what was tried and the remaining failure mode.
- No file other than `sim/src/stream_wrapper.v` was modified in `sim/`.
