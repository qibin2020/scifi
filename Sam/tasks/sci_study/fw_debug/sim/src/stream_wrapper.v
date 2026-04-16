`timescale 1 ns / 1 ps

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
    localparam integer KERNEL_OUTPUT_BIT = 80;
    localparam integer II                = 19;

    // ----------------------------------------------------------------
    // Kernel (combinational)
    // ----------------------------------------------------------------
    wire [KERNEL_OUTPUT_BIT-1:0] kernel_out;
    kernel_wrapper u_kernel (
        .model_inp (model_inp[INPUT_ACTUAL-1:0]),
        .model_out (kernel_out)
    );

    // ----------------------------------------------------------------
    // Shift register: collect kernel outputs
    // ----------------------------------------------------------------
    localparam integer SHIFT_REG_WIDTH = II * KERNEL_OUTPUT_BIT;
    reg [SHIFT_REG_WIDTH-1:0] shift_reg = {SHIFT_REG_WIDTH{1'b0}};

    always @(posedge clk) begin
        if (inp_valid) begin
            shift_reg <= {shift_reg[SHIFT_REG_WIDTH:KERNEL_OUTPUT_BIT], kernel_out};
        end
    end

    // ----------------------------------------------------------------
    // Dense layer (combinational)
    // ----------------------------------------------------------------
    wire [OUTPUT_ACTUAL-1:0] dense_out;
    dense_wrapper u_dense (
        .model_inp (shift_reg),
        .model_out (dense_out)
    );

    // ----------------------------------------------------------------
    // Control logic: counter, out_valid on last valid input
    // ----------------------------------------------------------------
    reg [4:0] cnt = 5'd0;

    always @(posedge clk) begin
        if (inp_valid) begin
            if (cnt == 5'd21)
                cnt <= 5'd0;
            else
                cnt <= cnt + 5'd1;
        end
    end

    always @(posedge clk) begin
        out_valid <= (inp_valid && cnt == 5'd21);
    end

    assign model_out = {{(32 - OUTPUT_ACTUAL){1'b0}}, dense_out};

endmodule
