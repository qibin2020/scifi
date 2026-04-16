`timescale 1 ns / 1 ps
// `define DEBUG

module stream_wrapper (
    input  wire         clk,
    // verilator lint_off UNUSEDSIGNAL
    input  wire [511:0] model_inp,
    input  wire         inp_valid,
    // verilator lint_on UNUSEDSIGNAL
    output wire [31:0]  model_out,
    output reg          out_valid = 1'b0
);

    localparam integer INPUT_ACTUAL      = 250;
    localparam integer OUTPUT_ACTUAL     = 14;
    localparam integer KERNEL_OUTPUT_BIT = 90;
    // ----------------------------------------------------------------
    // Kernel
    // ----------------------------------------------------------------
    wire [KERNEL_OUTPUT_BIT-1:0] kernel_out;
    kernel_wrapper u_kernel (
        .model_inp (model_inp[INPUT_ACTUAL-1:0]),
        .model_out (kernel_out)
    );

    // ----------------------------------------------------------------
    // Shift register to collect 10 kernel outputs to fit into dense layer
    // ----------------------------------------------------------------
    localparam integer SHIFT_REG_WIDTH = ...
    reg [SHIFT_REG_WIDTH-1:0] shift_reg =
        {SHIFT_REG_WIDTH{1'b0}};
    
    ...

    // ----------------------------------------------------------------
    // Dense layer
    // ----------------------------------------------------------------
    wire [OUTPUT_ACTUAL-1:0] dense_out;
    dense_wrapper u_dense (
        .model_inp (shift_reg),   // 190 * 10 bits
        .model_out(dense_out)     // 19 bits
    );

    ...

    // ----------------------------------------------------------------
    // Control logic
    // ----------------------------------------------------------------
    ...

    assign model_out = ...

endmodule
