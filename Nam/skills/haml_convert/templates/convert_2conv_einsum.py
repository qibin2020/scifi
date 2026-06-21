"""
v3_ref convert — V3 complex model -> da4ml cores + per-patch einsum-tail params.
General helpers (env, calibrate, partial_predict, emit_core, comb_full_golden) from general/hgq_rtl.py;
SciFi I/O from common/sci_io.py. Case-by-case: kernel/mid decomposition + the per-patch einsum tail.

Gates:  A per-patch comb_kernel vs keras (~0)   B 3-window comb_mid vs keras (0.0)
        C full chain (kernel->mid->tail) vs comb_full  (MUST be 100% bit-exact -> else STOP)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'general'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
import hgq_rtl as G
import sci_io as S

import json
import numpy as np
import keras
from da4ml.codegen.rtl.verilog.io_wrapper import hetero_io_map
from da4ml.converter import trace_model
from da4ml.trace import comb_trace, FixedVariableArray, FixedVariableArrayInput

model = keras.saving.load_model('model.keras')   # already calibrated at train time (trace_minmax saved); do NOT re-calibrate
x_val = S.load_val_x(4096)                        # validation samples for the Stage A/B/C gates only

c1 = next(i for i, l in enumerate(model.layers) if type(l).__name__ == 'QConv1D' and i < 5)
c2 = next(i for i, l in enumerate(model.layers) if type(l).__name__ == 'QConv1D' and i > c1)
ei = next(i for i, l in enumerate(model.layers) if type(l).__name__ == 'QEinsumDense')
conv1 = model.layers[c1]
PS, NCH = conv1.kernel.shape[0], conv1.kernel.shape[-1]
NP, W = model.input.shape[-1] // PS, model.layers[c2].kernel.shape[0]
print(f'PS={PS} NCH={NCH} NP={NP} W={W} | c1={c1} c2={c2} ei={ei}')

# kernel core (one patch)
m0 = keras.Model(model.inputs, model.layers[c1].output)
kif = tuple(int(np.asarray(x).ravel()[0]) for x in conv1.iq.quantizer.kif)
inp0 = FixedVariableArrayInput(PS).quantize(*kif); _, o0 = trace_model(m0, inputs=inp0)
ck = comb_trace(inp0, o0, keep_dead_inputs=True)
xt = x_val[:8]; ykc = G.partial_predict(model, xt, c1); xpat = xt.reshape(8, NP, PS)
ymk = np.array([[ck.predict(xpat[n:n+1, p, :], n_threads=1).flatten()[:NCH] for p in range(NP)] for n in range(8)])
stage_a = float(np.max(np.abs(ymk - ykc)))

# mid core (3-window)
m1 = keras.Model(model.layers[c2].input, model.layers[ei-1].output)
inp1 = np.stack([FixedVariableArray.from_kif(*o0.kif) for _ in range(W)], 0); _, o1 = trace_model(m1, inputs=inp1)
cm = comb_trace(inp1, o1[W//2:W//2+1], keep_dead_inputs=True)
ykpad = np.concatenate([np.zeros((8, 1, NCH)), ykc, np.zeros((8, 1, NCH))], 1)
ykm = G.partial_predict(model, xt, ei-1)
ycm = np.array([[cm.predict(ykpad[n, p:p+W, :].reshape(1, -1), n_threads=1).flatten()[:ykm.shape[-1]]
                 for p in range(NP)] for n in range(8)]).reshape(ykm.shape)
stage_b = float(np.max(np.abs(ycm.ravel() - ykm.ravel())))
print(f'Stage A: {stage_a:.6f}   Stage B: {stage_b:.6f}')

# einsum tail params (validated bit-exact arithmetic)
esd = model.layers[ei]
s = np.asarray(keras.ops.convert_to_numpy(esd.qkernel)).ravel()
b = np.asarray(keras.ops.convert_to_numpy(esd.qbias)).ravel()
ekif = lambda q: [int(np.asarray(keras.ops.convert_to_numpy(x)).item()) for x in q.quantizer.kif]
IQ_K, IQ_I, IQ_F = ekif(esd.iq); KQ_K, KQ_I, KF = ekif(esd.kq)
F_MID = int(np.asarray(cm.out_kifs).ravel().astype(int)[2])
kern_pad,  _ = hetero_io_map(ck.out_qint, merge=True)[-1]
midin_pad, _ = hetero_io_map(cm.inp_qint, merge=True)[-1]
mid_pad,   _ = hetero_io_map(cm.out_qint, merge=True)[-1]

G.emit_core(ck, 'kernel', './rtl_kernel')
G.emit_core(cm, 'mid',    './rtl_mid')

# Stage C: chain(kernel->mid->per-patch einsum tail) == comb_full (shared general golden)
# Einsum (general): out = oq( iq(mid)*kq(scale) + bias ).  Exact integer arithmetic:
#   q          = clip( round(mid / 2^REQ_SHIFT), 0, 2^Q_BITS-1 )         iq requant (REQ_SHIFT=F_MID-IQ_F)
#   prod       = round( (q * scale_int) / 2^PROD_SHIFT )                 product -> frac OQ_F  (signed scale)
#   out        = clip( prod + bias_int, OUT_MIN, OUT_MAX )               + bias (frac OQ_F), oq SAT
xs = x_val[:64].astype(np.int32)
(OQ_K, OQ_I, OQ_F), raw_full, _ = G.comb_full_golden(model, xs, path='./rtl_full')
OUT_MIN, OUT_MAX = -(2**(OQ_I+OQ_F)), 2**(OQ_I+OQ_F)-1
REQ_SHIFT  = F_MID - IQ_F                          # mid -> iq frac
Q_BITS     = IQ_I + IQ_F                           # iq value width (unsigned)
PROD_SHIFT = IQ_F + KF - OQ_F                      # product (frac IQ_F+KF) -> oq frac
scale_int  = np.round(s * 2**KF).astype(np.int64)  # signed (kq may be signed)
bias_int   = np.round(b * 2**OQ_F).astype(np.int64)
SCALE_SIGNED = int(KQ_K)
def rsh(x, sh):                                    # round-half-up arithmetic shift (handles sh<=0)
    return (x + (1 << (sh - 1))) >> sh if sh > 0 else x << (-sh)
def chain(xs):
    out = np.zeros((len(xs), NP), np.int64)
    for n in range(len(xs)):
        kout = np.stack([ck.predict(xs[n].reshape(NP, PS)[p:p+1], n_threads=1).flatten()[:NCH] for p in range(NP)], 0)
        kpad = np.concatenate([np.zeros((1, NCH)), kout, np.zeros((1, NCH))], 0)
        for p in range(NP):
            mid = cm.predict(kpad[p:p+W, :].reshape(1, -1), n_threads=1).flatten()[0]
            # iq requant uses round_mode=RND (round-half-UP), matching da4ml + the RTL
            # ((mid_out+half)>>REQ_SHIFT); python round() is half-to-EVEN and differs at .5 ties.
            q = int(np.clip(int(np.floor(mid * 2**IQ_F + 0.5)), 0, 2**Q_BITS - 1))
            prod = rsh(q * int(scale_int[p]), PROD_SHIFT)
            out[n, p] = int(np.clip(prod + int(bias_int[p]), OUT_MIN, OUT_MAX))
    return out
match = int((chain(xs) == raw_full).sum()); tot = raw_full.size
print(f'Stage C: chain vs comb_full = {match}/{tot} ({100*match/tot:.1f}%)')
assert match == tot, 'Stage C NOT bit-exact — tail derivation wrong, STOP.'

# LUT mems (scale twos-complement if signed)
def lut_mem(vals, bits):
    nd = (bits + 3) // 4
    return '\n'.join([format(int(v) % (2**bits), 'X').zfill(nd) for v in vals] +
                     [''.zfill(nd)] * (256 - len(vals))) + '\n', nd
lutdir = Path('rtl_kernel/src/static'); lutdir.mkdir(parents=True, exist_ok=True)
SCALE_BITS, BIAS_BITS = max(1, KQ_K+KQ_I+KF), OQ_K+OQ_I+OQ_F
sm, snd = lut_mem(scale_int, SCALE_BITS); (lutdir/'scale_lut.mem').write_text(sm)
bm, bnd = lut_mem(bias_int,  BIAS_BITS);  (lutdir/'bias_lut.mem').write_text(bm)

meta = {
    'PATCH_SIZE': int(PS), 'N_CH': int(NCH), 'N_PATCHES': int(NP), 'CONV2_WINDOW': int(W),
    'BW_INP': S.BW_INP, 'kernel_input_bits': int(PS*S.BW_INP), 'kernel_pad_bits': int(kern_pad),
    'mid_input_pad_bits': int(midin_pad), 'mid_output_pad_bits': int(mid_pad),
    'F_MID': F_MID, 'REQ_SHIFT': int(REQ_SHIFT), 'Q_BITS': int(Q_BITS),
    'PROD_SHIFT': int(PROD_SHIFT), 'SCALE_SIGNED': SCALE_SIGNED, 'OQ_F': int(OQ_F),
    'SCALE_BITS': int(SCALE_BITS), 'BIAS_BITS': int(BIAS_BITS), 'OUT_BITS': int(OQ_K+OQ_I+OQ_F),
    'OUT_MIN': int(OUT_MIN), 'OUT_MAX': int(OUT_MAX),
    'scale_int': scale_int.tolist(), 'bias_int': bias_int.tolist(),
    'stage_a': stage_a, 'stage_b': stage_b, 'stage_c_match': match,
}
assert midin_pad == W * kern_pad, f'{midin_pad} != {W}*{kern_pad}'
json.dump(meta, open('convert_meta.json', 'w'), indent=2)
open('convert_status.txt', 'w').write(
    f'OK kernel_pad={kern_pad} mid_in={midin_pad} mid_out={mid_pad} F_MID={F_MID} '
    f'REQ_SHIFT={REQ_SHIFT} stageA={stage_a:.6f} stageB={stage_b:.6f} stageC={match}/{tot}\n')
print('convert_meta.json + convert_status.txt written; Stage C bit-exact.')
