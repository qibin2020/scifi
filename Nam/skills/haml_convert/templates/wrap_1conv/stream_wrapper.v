// stream_wrapper.v — V1-simple HGQ streaming pipeline (1 conv + 1 dense)
// All localparams DERIVED, no fixed numbers in logic:
//   INPUT_ACTUAL      = kernel_size * BW_INP                    ← from kernel_wrapper.v input
//   KERNEL_OUTPUT_BIT = kernel_wrapper output bit width          ← grep '^\s*output' kernel_wrapper.v
//   SHIFT_REG_WIDTH   = II * KERNEL_OUTPUT_BIT                  ← must equal dense_wrapper input
//   OUTPUT_ACTUAL     = dense_wrapper output bit width           ← grep '^\s*output' dense_wrapper.v
//   II                = waveform_length / kernel_stride          ← number of windows per sample
`timescale 1 ns / 1 ps

module stream_wrapper #(
    parameter integer INPUT_ACTUAL      = 250,   // kernel_wrapper input width  (= kernel_size * BW_INP = 25 * 10)
    parameter integer KERNEL_OUTPUT_BIT = 155,   // kernel_wrapper output width (model-specific)
    parameter integer II                = 20,    // windows per sample           (= 500 / 25)
    parameter integer OUTPUT_ACTUAL     = 28     // dense_wrapper output width  (model-specific)
) (
    input  wire                       clk,
    input  wire                       inp_valid,
    // verilator lint_off UNUSEDSIGNAL
    input  wire [INPUT_ACTUAL-1:0]    model_inp,
    // verilator lint_on UNUSEDSIGNAL
    output reg                        out_valid,
    output wire [31:0]                model_out
);

    localparam integer SHIFT_REG_WIDTH = II * KERNEL_OUTPUT_BIT;
    localparam integer CNT_BITS        = $clog2(II);

    // -----------------------------------------------------------------
    // Combinational kernel (per-window)
    // -----------------------------------------------------------------
    wire [KERNEL_OUTPUT_BIT-1:0] kernel_out;
    kernel_wrapper u_kernel (
        .model_inp(model_inp),
        .model_out(kernel_out)
    );

    // -----------------------------------------------------------------
    // Shift register accumulating II valid kernel outputs
    // (new KERNEL_OUTPUT_BIT-wide chunk goes into HIGH bits; existing
    //  contents shift DOWN — this order matches what dense_wrapper expects)
    // -----------------------------------------------------------------
    reg [SHIFT_REG_WIDTH-1:0] shift_reg = {SHIFT_REG_WIDTH{1'b0}};
    reg [CNT_BITS-1:0]        cnt       = {CNT_BITS{1'b0}};

    // -----------------------------------------------------------------
    // Combinational dense over the full shift register
    // -----------------------------------------------------------------
    wire [OUTPUT_ACTUAL-1:0] dense_out;
    dense_wrapper u_dense (
        .model_inp(shift_reg),
        .model_out(dense_out)
    );

    // -----------------------------------------------------------------
    // Control: counter advances ONLY on inp_valid (so paused cycles hold
    // state); out_valid pulses for exactly one clock when window II-1
    // arrives, indicating shift_reg is fully loaded.
    // -----------------------------------------------------------------
    always @(posedge clk) begin
        if (inp_valid) begin
            shift_reg <= {kernel_out, shift_reg[SHIFT_REG_WIDTH-1:KERNEL_OUTPUT_BIT]};
            if (cnt == II[CNT_BITS-1:0] - 1'b1) begin
                cnt       <= {CNT_BITS{1'b0}};
                out_valid <= 1'b1;
            end else begin
                cnt       <= cnt + 1'b1;
                out_valid <= 1'b0;
            end
        end else begin
            out_valid <= 1'b0;
        end
    end

    // Zero-extend the OUTPUT_ACTUAL-wide dense_out to the 32-bit output bus
    assign model_out = {{(32-OUTPUT_ACTUAL){1'b0}}, dense_out};

endmodule
