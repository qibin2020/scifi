`timescale 1 ns / 1 ps

// stream_wrapper: EMPTY skeleton — implement the streaming inference
// pipeline body. The interface below is fixed (matches sim/stream_wrapper_binder.cc)
// and MUST NOT be changed: port names, widths, and order are required by
// the Verilator-driven testbench.
//
// Available submodules in sim/src/: kernel_wrapper.v, dense_wrapper.v
// Build: from sim/, run `make -f build_binder.mk slow`
// Verify: from sim/, run `python3 verify_golden.py --no-pause`
//                     and `python3 verify_golden.py --inp-pause 0.3 --seed 42`
// Both verify modes must print "PASSED: All".

module stream_wrapper (
    input  wire         clk,
    // verilator lint_off UNUSEDSIGNAL
    input  wire [511:0] model_inp,
    input  wire         inp_valid,
    // verilator lint_on UNUSEDSIGNAL
    output wire [31:0]  model_out,
    output reg          out_valid = 1'b0
);

    // TODO: implement the body here.

endmodule
