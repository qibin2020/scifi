`timescale 1ns/1ps

module kernel (
    input [169:0] model_inp,
    output [42:0] model_out
);

    // verilator lint_off UNUSEDSIGNAL
    // Explicit quantization operation will drop bits if exists

    wire [9:0] v0; assign v0[9:0] = model_inp[9:0]; // 0.0
    wire [9:0] v1; assign v1[9:0] = model_inp[19:10]; // 0.0
    wire [9:0] v2; assign v2[9:0] = model_inp[29:20]; // 0.0
    wire [9:0] v3; assign v3[9:0] = model_inp[39:30]; // 0.0
    wire [9:0] v4; assign v4[9:0] = model_inp[49:40]; // 0.0
    wire [9:0] v5; assign v5[9:0] = model_inp[59:50]; // 0.0
    wire [9:0] v6; assign v6[9:0] = model_inp[69:60]; // 0.0
    wire [9:0] v7; assign v7[9:0] = model_inp[79:70]; // 0.0
    wire [9:0] v8; assign v8[9:0] = model_inp[89:80]; // 0.0
    wire [9:0] v9; assign v9[9:0] = model_inp[99:90]; // 0.0
    wire [9:0] v10; assign v10[9:0] = model_inp[109:100]; // 0.0
    wire [9:0] v11; assign v11[9:0] = model_inp[119:110]; // 0.0
    wire [9:0] v12; assign v12[9:0] = model_inp[129:120]; // 0.0
    wire [9:0] v13; assign v13[9:0] = model_inp[139:130]; // 0.0
    wire [9:0] v14; assign v14[9:0] = model_inp[149:140]; // 0.0
    wire [9:0] v15; assign v15[9:0] = model_inp[159:150]; // 0.0
    wire [9:0] v16; assign v16[9:0] = model_inp[169:160]; // 0.0
    wire [9:0] v18; assign v18[9:0] = v9[9:0]; // 0.0
    wire [9:0] v19; assign v19[9:0] = v0[9:0]; // 0.0
    wire [9:0] v20; assign v20[9:0] = v2[9:0]; // 0.0
    wire [9:0] v21; assign v21[9:0] = v3[9:0]; // 0.0
    wire [9:0] v22; assign v22[9:0] = v4[9:0]; // 0.0
    wire [9:0] v23; assign v23[9:0] = v6[9:0]; // 0.0
    wire [9:0] v24; assign v24[9:0] = v7[9:0]; // 0.0
    wire [9:0] v25; assign v25[9:0] = v8[9:0]; // 0.0
    wire [9:0] v26; assign v26[9:0] = v10[9:0]; // 0.0
    wire [9:0] v27; assign v27[9:0] = v11[9:0]; // 0.0
    wire [9:0] v28; assign v28[9:0] = v12[9:0]; // 0.0
    wire [9:0] v29; assign v29[9:0] = v13[9:0]; // 0.0
    wire [9:0] v30; assign v30[9:0] = v14[9:0]; // 0.0
    wire [9:0] v31; assign v31[9:0] = v15[9:0]; // 0.0
    wire [9:0] v32; assign v32[9:0] = v16[9:0]; // 0.0
    wire [9:0] v34; assign v34[9:0] = v1[9:0]; // 0.0
    wire [9:0] v35; assign v35[9:0] = v5[9:0]; // 0.0
    wire [10:0] v36; shift_adder #(10, 10, 0, 0, 11, 0, 0) op_36 (v19[9:0], v20[9:0], v36[10:0]); // 1.0
    wire [10:0] v37; shift_adder #(10, 10, 0, 0, 11, 0, 0) op_37 (v21[9:0], v22[9:0], v37[10:0]); // 1.0
    wire [11:0] v38; shift_adder #(10, 10, 0, 0, 12, 1, 0) op_38 (v23[9:0], v24[9:0], v38[11:0]); // 1.0
    wire [11:0] v39; shift_adder #(10, 10, 0, 0, 12, -1, 0) op_39 (v25[9:0], v26[9:0], v39[11:0]); // 1.0
    wire [11:0] v40; shift_adder #(10, 10, 0, 0, 12, 1, 0) op_40 (v27[9:0], v28[9:0], v40[11:0]); // 1.0
    wire [11:0] v41; shift_adder #(10, 10, 0, 0, 12, 1, 0) op_41 (v29[9:0], v30[9:0], v41[11:0]); // 1.0
    wire [11:0] v42; shift_adder #(10, 10, 0, 0, 12, -1, 0) op_42 (v31[9:0], v32[9:0], v42[11:0]); // 1.0
    wire [11:0] v43; shift_adder #(10, 10, 0, 0, 12, 1, 1) op_43 (v34[9:0], v32[9:0], v43[11:0]); // 1.0
    wire [10:0] v44; shift_adder #(10, 10, 0, 0, 11, 0, 0) op_44 (v22[9:0], v35[9:0], v44[10:0]); // 1.0
    wire [10:0] v45; shift_adder #(10, 10, 0, 0, 11, 0, 0) op_45 (v28[9:0], v23[9:0], v45[10:0]); // 1.0
    wire [11:0] v46; shift_adder #(10, 10, 0, 0, 12, -1, 0) op_46 (v25[9:0], v18[9:0], v46[11:0]); // 1.0
    wire [11:0] v47; shift_adder #(10, 11, 0, 0, 12, 0, 0) op_47 (v18[9:0], v36[10:0], v47[11:0]); // 2.0
    wire [12:0] v48; shift_adder #(11, 12, 0, 0, 13, 0, 0) op_48 (v37[10:0], v38[11:0], v48[12:0]); // 2.0
    wire [12:0] v49; shift_adder #(12, 12, 0, 0, 13, 0, 0) op_49 (v39[11:0], v40[11:0], v49[12:0]); // 2.0
    wire [13:0] v50; shift_adder #(12, 12, 0, 0, 14, 1, 0) op_50 (v41[11:0], v42[11:0], v50[13:0]); // 2.0
    wire [13:0] v51; shift_adder #(12, 10, 1, 0, 14, 2, 1) op_51 (v43[11:0], v23[9:0], v51[13:0]); // 2.0
    wire [12:0] v52; shift_adder #(12, 11, 1, 0, 13, -1, 0) op_52 (v43[11:0], v44[10:0], v52[12:0]); // 2.0
    wire [14:0] v53; shift_adder #(12, 10, 0, 0, 15, 4, 1) op_53 (v46[11:0], v19[9:0], v53[14:0]); // 2.0
    wire [13:0] v54; shift_adder #(12, 13, 0, 0, 14, -1, 0) op_54 (v47[11:0], v48[12:0], v54[13:0]); // 3.0
    wire [13:0] v55; shift_adder #(13, 14, 0, 0, 14, 0, 0) op_55 (v49[12:0], v50[13:0], v55[13:0]); // 3.0
    wire [14:0] v56; shift_adder #(14, 13, 1, 1, 15, 1, 1) op_56 (v51[13:0], v52[12:0], v56[14:0]); // 3.0
    wire [13:0] v57; assign v57[13:0] = v56[13:0] & {14{~v56[14]}}; // 3.0
    wire [14:0] v58; shift_adder #(11, 15, 0, 1, 15, -2, 0) op_58 (v45[10:0], v53[14:0], v58[14:0]); // 3.0
    wire [13:0] v59; assign v59[13:0] = v58[13:0] & {14{~v58[14]}}; // 3.0
    wire [14:0] v60; shift_adder #(14, 14, 0, 0, 15, 0, 0) op_60 (v54[13:0], v55[13:0], v60[14:0]); // 4.0

    // verilator lint_on UNUSEDSIGNAL

    assign model_out[14:0] = v60[14:0];
    assign model_out[28:15] = v57[13:0];
    assign model_out[42:29] = v59[13:0];

    endmodule
