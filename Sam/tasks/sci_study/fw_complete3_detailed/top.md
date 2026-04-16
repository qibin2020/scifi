---
Rank: 4
Timeout: 1800
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# Real FW Void — HGQ Stream Wrapper From Nothing

## Context

You are implementing a Verilator-based simulation harness for an FPGA streaming inference pipeline FROM SCRATCH. Both halves of the harness are EMPTY:

- `sim/src/stream_wrapper.v` — contains only `module stream_wrapper; endmodule`. You design the entire port interface and the entire body.
- `sim/stream_wrapper_binder.cc` — contains only comments. You write the entire C++ binder that drives your `.v` module via Verilator.

You design BOTH sides of the C++/Verilog interface yourself. The only fixed boundary is between Python and C++ (the `inference` function signature, defined below). Everything else — `.v` port names, port widths, signal protocol, internal C++ helpers — is your decision.

The available submodules in `sim/src/` are complete and authoritative. Do NOT modify them:
- `sim/src/kernel_wrapper.v` — combinational convolution kernel. Compose this into your `stream_wrapper`.
- `sim/src/dense_wrapper.v` — combinational dense (fully-connected) layer. Compose this into your `stream_wrapper`.
- `sim/src/kernel.v`, `sim/src/dense.v`, `sim/src/static/*` — internal building blocks of the above.

Other support files you can use as-is:
- `sim/build_binder.mk` — Makefile that runs `verilator --cc -build src/stream_wrapper.v --top-module stream_wrapper -Wall ...` and links the C++ binder + verilator-generated objects into `libstream_wrapper_<uuid>.so`. You should not need to change it.
- `sim/ioutil.hh` — header with `write_input<N, BW>(buf, ptr)` and `read_output<N, BW>(buf, ptr)` template helpers for bit packing/unpacking between int32 arrays and Verilator wide buses. You can use these in your binder.
- `sim/verify_golden.py` — Python verification oracle. It loads your `.so` via ctypes, calls `inference(...)`, and compares the result against `dataset/golden_Y.csv`.

The dataset is in `dataset/`:
- `golden_X.csv` — 100 input waveforms, each with 500 int32 features
- `golden_Y.csv` — 100 expected int32 output values, one per waveform

The toolchain (verilator, g++, make, python3 with numpy) is NOT pre-installed. Install into a local micromamba env first:
    MAMBA_ROOT_PREFIX=./mamba_env micromamba create -n hgq -c conda-forge verilator gxx_linux-64 make "python>=3.10" numpy -y
Then write env.sh to put it on PATH.

### Required external contract (do NOT change)

`verify_golden.py` is the oracle. It is fixed. It will:
1. Run `make -f build_binder.mk slow` from `sim/` to build your binder + RTL into a `.so`.
2. Find the resulting `libstream_wrapper_*.so`.
3. Load it via `ctypes.CDLL(...)`.
4. Resolve the symbol `inference` with this argtypes signature:
   ```python
   lib.inference.argtypes = [
       ctypes.POINTER(ctypes.c_int32),   # c_inp
       ctypes.POINTER(ctypes.c_int32),   # c_out
       ctypes.c_size_t,                  # n_samples
       ctypes.c_double,                  # inp_pause_prob
       ctypes.c_uint32,                  # seed
   ]
   lib.inference.restype = ctypes.c_size_t
   ```
5. Call `lib.inference(inp_ptr, out_ptr, 100, inp_pause_prob, seed)`. The first array is 100*500=50000 int32 values flattened row-major (sample 0 features, then sample 1 features, ...). The second array is your output buffer (length 100).
6. Compare the returned outputs to `golden_Y.csv`.
7. Print `PASSED: All 100 outputs match golden reference.` if all match, or `FAILED: ...` otherwise.

So your `stream_wrapper_binder.cc` MUST export:
```cpp
extern "C" size_t inference(
    const int32_t *c_inp,
    int32_t       *c_out,
    size_t         n_samples,
    double         inp_pause_prob,
    uint32_t       seed);
```
The function returns the number of outputs collected (should equal `n_samples` on success).

### Required dataflow (the design problem)

The hardware design is a streaming inference pipeline:

1. Each input waveform has **500 int32 values**, each value is **10 bits** wide (`BW_INP = 10`).
2. The kernel and dense layers operate on **chunks**. Each clock cycle the binder feeds one chunk into the model. With 500 values per waveform and a chunk size of **25** values per clock (`CHUNK = 25`), processing one waveform takes **20 clocks** (`II = 20`, the initiation interval).
3. The convolution kernel (`kernel_wrapper`) takes a **250-bit** combinational input bus (25 values × 10 bits, packed) and produces a **90-bit** output (`KERNEL_OUTPUT_BIT = 90`).
4. To feed the dense layer, you must accumulate **II=20** kernel outputs into a shift register of **20 × 90 = 1800 bits** (`SHIFT_REG_WIDTH = 1800`). The shift register advances by one kernel output per valid input clock.
5. The dense layer (`dense_wrapper`) takes the full **1800-bit** shift register as combinational input and produces a **14-bit** output (`BW_OUT = 14`).
6. The binder must drive `inp_valid` high while feeding chunks. Per the `inp_pause_prob` argument, it must randomly drop `inp_valid` (set it low) with that probability per clock — when `inp_valid` is low, the design must hold its state and not advance the shift register or counter.
7. The design must pulse `out_valid` high for exactly **one cycle** when a fresh dense output is ready (after 20 valid input clocks per waveform). The binder reads `out_valid` and, when high, captures the output value into `c_out[n_out++]`.
8. The binder must process **all 100 waveforms** and write 100 int32 outputs to `c_out`, then return the count.
9. The 14-bit dense output must be sign-/zero-extended to int32 when the binder reads it back (use the `read_output<N, BW>` helper from `ioutil.hh`).

You can choose:
- The exact `.v` port names (e.g. `clk`, `inp_valid`, `model_inp`, `out_valid`, `model_out`, or anything else — your design, your names).
- The bus widths beyond what the building blocks force (e.g. `model_inp` could be 250 bits exactly, or 256, or 512 — pick what's convenient).
- Whether `out_valid` is `wire` or `reg`.
- The exact way you instantiate `kernel_wrapper` and `dense_wrapper` and route signals.
- The C++ binder structure: how you initialize `Vstream_wrapper`, how you advance the clock (`dut->clk = 0; dut->eval(); dut->clk = 1; dut->eval();`), how you implement the random pause loop, how you bound the simulation cycle count, etc.

The Verilator build will generate `obj_dir/Vstream_wrapper.h` from your `.v` file. Whatever ports you declare become public members of `Vstream_wrapper` (e.g. `dut->clk`, `dut->inp_valid`, etc.). Read your own port list to know what to drive.

### Verilator strictness

`build_binder.mk` invokes verilator with `-Wall`. Warnings are treated as errors. Common pitfalls you must handle:
- `PROCASSINIT`: any `reg` declared with an initializer (`reg foo = 0;`) AND assigned in an `always` block needs `/* verilator lint_off PROCASSINIT */` ... `/* verilator lint_on PROCASSINIT */` around the affected scope.
- `EOFNEWLINE`: the `.v` file must end with a trailing newline.
- `WIDTHEXPAND` / `WIDTHTRUNC`: explicit bit-widths in concatenations and comparisons.
- `UNUSEDSIGNAL`: if you declare an input bus wider than what you actually use, wrap it in `/* verilator lint_off UNUSEDSIGNAL */` ... `/* verilator lint_on UNUSEDSIGNAL */`.

## Todo

1. Read every authoritative file BEFORE writing any code:
   - `sim/src/kernel_wrapper.v` and `sim/src/dense_wrapper.v` (port widths, names)
   - `sim/verify_golden.py` (the python oracle, to confirm the C contract you read above)
   - `sim/ioutil.hh` (the bit-packing helpers and how to call them)
   - `sim/build_binder.mk` (so you understand the build flow but don't need to change it)
   - `sim/src/stream_wrapper.v` and `sim/stream_wrapper_binder.cc` (the empty stubs)
2. Design the `.v` module: port list, internal shift register, counter, control logic, instantiations of `kernel_wrapper` and `dense_wrapper`, output assignment.
3. Write `sim/src/stream_wrapper.v`.
4. Design the C++ binder: include verilator headers, declare `extern "C" size_t inference(...)`, instantiate `Vstream_wrapper`, write the cycle loop with random pauses and capture logic.
5. Write `sim/stream_wrapper_binder.cc`.
6. Build: from `sim/`, run `make -f build_binder.mk clean && make -f build_binder.mk slow`.
7. Verify in both modes:
   - From `sim/`, run `python3 verify_golden.py --no-pause 2>&1 | tee ../nopause.log`
   - From `sim/`, run `python3 verify_golden.py --inp-pause 0.3 --seed 42 2>&1 | tee ../paused.log`
   - Both must print "PASSED: All 100 outputs match golden reference."
8. Write `notes.md` in the task root with a one-paragraph summary.

## Expect

- `nopause.log` exists in the task root and contains "PASSED: All"
- `paused.log` exists in the task root and contains "PASSED: All"
- `notes.md` exists in the task root with a one-paragraph summary
- `sim/src/stream_wrapper.v` has been implemented (no longer empty)
- `sim/stream_wrapper_binder.cc` has been implemented (no longer empty)
- No file under `sim/src/` other than `stream_wrapper.v` was modified
- `sim/build_binder.mk`, `sim/verify_golden.py`, `sim/ioutil.hh`, and the dataset are unchanged
