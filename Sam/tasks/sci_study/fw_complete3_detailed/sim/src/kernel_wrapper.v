`timescale 1 ns / 1 ps

module kernel_wrapper (
    // verilator lint_off UNUSEDSIGNAL
    input [249:0] model_inp,
    // verilator lint_on UNUSEDSIGNAL
    output [89:0] model_out
);
    wire [169:0] packed_inp;
    wire [42:0] packed_out;

    assign packed_inp[29:0] = model_inp[29:0];
    assign packed_inp[49:30] = model_inp[59:40];
    assign packed_inp[79:50] = model_inp[99:70];
    assign packed_inp[119:80] = model_inp[159:120];
    assign packed_inp[139:120] = model_inp[189:170];
    assign packed_inp[169:140] = model_inp[249:220];

    kernel op (
        .model_inp(packed_inp),
        .model_out(packed_out)
    );

    assign model_out[35:21] = packed_out[14:0];
    assign model_out[20:0] = 21'b0;
    assign model_out[68:55] = packed_out[28:15];
    assign model_out[85:72] = packed_out[42:29];
    assign model_out[54:36] = 19'b0;
    assign model_out[71:69] = 3'b0;
    assign model_out[89:86] = 4'b0;

endmodule
