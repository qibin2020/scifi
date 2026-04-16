`timescale 1 ns / 1 ps

module dense_wrapper (
    // verilator lint_off UNUSEDSIGNAL
    input [1799:0] model_inp,
    // verilator lint_on UNUSEDSIGNAL
    output [13:0] model_out
);
    wire [562:0] packed_inp;
    wire [13:0] packed_out;

    assign packed_inp[14:0] = model_inp[35:21];
    assign packed_inp[29:15] = model_inp[125:111];
    assign packed_inp[44:30] = model_inp[215:201];
    assign packed_inp[59:45] = model_inp[305:291];
    assign packed_inp[73:60] = model_inp[428:415];
    assign packed_inp[88:74] = model_inp[485:471];
    assign packed_inp[102:89] = model_inp[518:505];
    assign packed_inp[116:103] = model_inp[535:522];
    assign packed_inp[131:117] = model_inp[575:561];
    assign packed_inp[145:132] = model_inp[608:595];
    assign packed_inp[159:146] = model_inp[625:612];
    assign packed_inp[174:160] = model_inp[665:651];
    assign packed_inp[188:175] = model_inp[698:685];
    assign packed_inp[202:189] = model_inp[715:702];
    assign packed_inp[217:203] = model_inp[755:741];
    assign packed_inp[231:218] = model_inp[788:775];
    assign packed_inp[245:232] = model_inp[805:792];
    assign packed_inp[260:246] = model_inp[845:831];
    assign packed_inp[274:261] = model_inp[878:865];
    assign packed_inp[288:275] = model_inp[895:882];
    assign packed_inp[303:289] = model_inp[935:921];
    assign packed_inp[317:304] = model_inp[968:955];
    assign packed_inp[331:318] = model_inp[985:972];
    assign packed_inp[346:332] = model_inp[1025:1011];
    assign packed_inp[360:347] = model_inp[1058:1045];
    assign packed_inp[374:361] = model_inp[1075:1062];
    assign packed_inp[389:375] = model_inp[1115:1101];
    assign packed_inp[403:390] = model_inp[1148:1135];
    assign packed_inp[418:404] = model_inp[1205:1191];
    assign packed_inp[432:419] = model_inp[1238:1225];
    assign packed_inp[446:433] = model_inp[1255:1242];
    assign packed_inp[461:447] = model_inp[1385:1371];
    assign packed_inp[476:462] = model_inp[1475:1461];
    assign packed_inp[490:477] = model_inp[1598:1585];
    assign packed_inp[505:491] = model_inp[1655:1641];
    assign packed_inp[519:506] = model_inp[1688:1675];
    assign packed_inp[533:520] = model_inp[1705:1692];
    assign packed_inp[548:534] = model_inp[1745:1731];
    assign packed_inp[562:549] = model_inp[1795:1782];

    dense op (
        .model_inp(packed_inp),
        .model_out(packed_out)
    );

    assign model_out[13:0] = packed_out[13:0];

endmodule
