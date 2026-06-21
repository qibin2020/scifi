// stream_wrapper.v — V3 complex streaming pipeline (2 conv + per-patch DNN + per-patch einsum tail)
// Composes da4ml cores (kernel, mid) under a hand-written streaming top, and reproduces da4ml's
// comb_full per-patch output BIT-EXACTLY (validated: chain == comb_full 320/320).
//
// All localparams DERIVED from convert_meta.json by assemble_wrap.py (never hardcode):
//   KERNEL_INPUT_BIT  = PATCH_SIZE*BW_INP        KERNEL_OUTPUT_BIT = kernel core out width
//   MID_INPUT_BIT     = CONV2_WINDOW*KOB         MID_OUTPUT_BIT    = mid core out width (frac F_MID)
//   N_PATCHES, CONV2_WINDOW, N_FLUSH, ACCUM_START (= CONV2_WINDOW-1, patch-0 mid-valid cycle)
//   einsum tail (per patch p, ROUND requant — validated bit-exact):
//     q    = clip( round(mid_out / 2^REQ_SHIFT), 0, 2^Q_BITS-1 )    // iq requant, unsigned SAT
//     prod = round( q * scale_lut[p] / 2^KF )                        // per-patch scale LUT
//     out  = clip( prod + bias_lut[p], OUT_MIN, OUT_MAX )            // bias LUT + oq SAT
//   Output is PER-PATCH: out_valid pulses N_PATCHES times / sample, OUT_BITS-wide signed.
//
// ⚠ One streaming knob (same as dtpid): shift_buffer window order vs da4ml's mid-trace flatten
//   order (newest-into-HIGH here). If streamed mid disagrees with comb_full, reverse the concat.
//   ACCUM_START may need ±1 for comb latency. SCALE_SIGNED is assumed 0 (einsum scale >= 0).
`timescale 1 ns / 1 ps

module stream_wrapper #(
    parameter integer KERNEL_INPUT_BIT  = 250,
    parameter integer KERNEL_OUTPUT_BIT = 288,
    parameter integer MID_INPUT_BIT     = 864,
    parameter integer MID_OUTPUT_BIT    = 29,
    parameter integer N_PATCHES         = 20,
    parameter integer CONV2_WINDOW      = 3,
    parameter integer N_FLUSH           = 2,
    parameter integer ACCUM_START       = 2,
    parameter integer REQ_SHIFT         = 12,    // mid -> iq frac (= F_MID - IQ_F)
    parameter integer Q_BITS            = 13,    // iq value width (unsigned)
    parameter integer PROD_SHIFT        = 2,     // product -> oq frac (= IQ_F + KF - OQ_F; may be <=0)
    parameter integer SCALE_BITS        = 4,     // scale LUT width (signed if SCALE_SIGNED)
    parameter integer SCALE_SIGNED      = 0,     // kq sign bit
    parameter integer BIAS_BITS         = 15,    // signed
    parameter integer OUT_BITS          = 15,    // signed (= OQ_K+OQ_I+OQ_F)
    parameter integer OUT_MIN           = -16384,
    parameter integer OUT_MAX           = 16383
) (
    input  wire                        clk,
    input  wire                        inp_valid,
    // verilator lint_off UNUSEDSIGNAL
    input  wire [KERNEL_INPUT_BIT-1:0] model_inp,
    // verilator lint_on UNUSEDSIGNAL
    output reg                         out_valid,
    output wire [31:0]                 model_out
);
    localparam integer PERIOD   = N_PATCHES + N_FLUSH;
    localparam integer CNT_BITS = $clog2(N_PATCHES + N_FLUSH + 1);

    // ----- per-patch combinational kernel (conv1) -----
    wire [KERNEL_OUTPUT_BIT-1:0] kernel_out;
    kernel_wrapper u_kernel (.model_inp(model_inp), .model_out(kernel_out));

    // ----- 3-window shift buffer (newest into HIGH) -> mid core (conv2+DNN) -----
    reg  [MID_INPUT_BIT-1:0]  shift_buffer = {MID_INPUT_BIT{1'b0}};
    wire [MID_OUTPUT_BIT-1:0] mid_out;
    mid_wrapper u_mid (.model_inp(shift_buffer), .model_out(mid_out));

    // ----- per-sample counter + current patch index -----
    reg  [CNT_BITS-1:0] cnt = {CNT_BITS{1'b0}};
    // conv2 padding='same' boundary = ZERO kernel outputs, NOT kernel(0). During the flush
    // cycles (cnt >= N_PATCHES) push literal 0 into the buffer so patch 0's left and patch
    // (N_PATCHES-1)'s right contexts are PAD (matches the Stage-C python chain's zero padding).
    wire is_flush = (cnt >= N_PATCHES[CNT_BITS-1:0]);
    wire [KERNEL_OUTPUT_BIT-1:0] kin = is_flush ? {KERNEL_OUTPUT_BIT{1'b0}} : kernel_out;
    wire accept = (cnt >= ACCUM_START[CNT_BITS-1:0]) &&
                  (cnt <  ACCUM_START[CNT_BITS-1:0] + N_PATCHES[CNT_BITS-1:0]);
    wire [CNT_BITS-1:0] psel = cnt - ACCUM_START[CNT_BITS-1:0];
    wire [7:0] patch_idx = {{(8-CNT_BITS){1'b0}}, psel};

    // ----- per-patch scale + bias LUTs -----
    wire [SCALE_BITS-1:0] scale;
    wire [BIAS_BITS-1:0]  bias;
    lookup_table #(.BW_IN(8), .BW_OUT(SCALE_BITS), .MEM_FILE("scale_lut.mem")) u_scl (.in(patch_idx), .out(scale));
    lookup_table #(.BW_IN(8), .BW_OUT(BIAS_BITS),  .MEM_FILE("bias_lut.mem"))  u_bia (.in(patch_idx), .out(bias));

    // ----- einsum tail (combinational); intended fixed-point truncations -> waive width lints -----
    // verilator lint_off WIDTHEXPAND
    // verilator lint_off WIDTHTRUNC
    // q = clip( round(mid_out / 2^REQ_SHIFT), 0, 2^Q_BITS-1 )    (mid_out unsigned, relu)
    localparam [MID_OUTPUT_BIT:0] HALF_REQ = (REQ_SHIFT > 0) ? ({{MID_OUTPUT_BIT{1'b0}},1'b1} << (REQ_SHIFT-1)) : 0;
    wire [MID_OUTPUT_BIT:0] q_round = ({1'b0, mid_out} + HALF_REQ) >> REQ_SHIFT;
    wire q_ovf = |q_round[MID_OUTPUT_BIT:Q_BITS];                          // any bit above Q_BITS set
    wire [Q_BITS-1:0] q = q_ovf ? {Q_BITS{1'b1}} : q_round[Q_BITS-1:0];     // unsigned SAT

    // prod = round( q * scale / 2^PROD_SHIFT )   (scale SIGNED; PROD_SHIFT may be <=0)
    localparam integer PFW = Q_BITS + 1 + SCALE_BITS;                 // signed product width
    localparam integer LSH = (PROD_SHIFT < 0) ? -PROD_SHIFT : 0;      // left-shift amount if PROD_SHIFT<0
    localparam integer PW  = PFW + LSH + 1;
    wire signed [SCALE_BITS-1:0] scale_s = SCALE_SIGNED ? $signed(scale) : $signed({1'b0, scale[SCALE_BITS-2:0]});
    wire signed [PFW-1:0] prod_full = $signed({1'b0, q}) * scale_s;
    localparam signed [PW-1:0] HALF_PROD = (PROD_SHIFT > 0) ? (1 <<< (PROD_SHIFT-1)) : 0;
    wire signed [PW-1:0] prod =
        (PROD_SHIFT > 0) ? (($signed(prod_full) + HALF_PROD) >>> PROD_SHIFT) :
        (PROD_SHIFT < 0) ? ($signed(prod_full) <<< LSH) :
                            $signed(prod_full);

    // val = prod + bias  (signed);  then oq SAT clip
    localparam integer ACCW = (PW > BIAS_BITS ? PW : BIAS_BITS) + 2;
    wire signed [ACCW-1:0] val  = $signed(prod) + $signed(bias);
    wire signed [ACCW-1:0] omin = OUT_MIN[ACCW-1:0];
    wire signed [ACCW-1:0] omax = OUT_MAX[ACCW-1:0];
    wire signed [OUT_BITS-1:0] clipped =
        (val < omin) ? omin[OUT_BITS-1:0] : (val > omax) ? omax[OUT_BITS-1:0] : val[OUT_BITS-1:0];
    // verilator lint_on WIDTHTRUNC
    // verilator lint_on WIDTHEXPAND

    reg signed [OUT_BITS-1:0] out_r = {OUT_BITS{1'b0}};

    always @(posedge clk) begin
        if (inp_valid) begin
            shift_buffer <= {kin, shift_buffer[MID_INPUT_BIT-1:KERNEL_OUTPUT_BIT]};
            out_r        <= clipped;
            out_valid    <= accept;
            cnt          <= (cnt == PERIOD[CNT_BITS-1:0] - 1'b1) ? {CNT_BITS{1'b0}} : cnt + 1'b1;
        end else begin
            out_valid <= 1'b0;
        end
    end

    assign model_out = {{(32-OUT_BITS){out_r[OUT_BITS-1]}}, out_r};
endmodule
