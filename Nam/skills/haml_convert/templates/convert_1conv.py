"""
v1_ref convert — V1 simple model -> da4ml cores (per-window split). Case-by-case decomposition;
general helpers (env, calibrate, partial_predict, emit_core) from general/hgq_rtl.py; SciFi I/O from
common/sci_io.py. Gates: Stage 1 comb_full vs keras (~0); Stage 2 per-window vs keras conv (0.0).
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
from da4ml.trace import comb_trace, FixedVariableArray

model = keras.saving.load_model('model.keras')   # already calibrated at train time (trace_minmax saved); do NOT re-calibrate
x_val = S.load_val_x(4096)                        # validation samples for the Stage-1/2 gates only

SPLIT = 2
conv = model.layers[SPLIT]
break_input  = conv.kernel.shape[0]
break_output = conv.kernel.shape[-1]
break_n      = model.input.shape[-1] // break_input
assert break_n * break_input == model.input.shape[-1]
print(f'split: in={break_input} out={break_output} II={break_n}')

model0 = keras.Model(model.inputs, model.layers[SPLIT].output)
model1 = keras.Model(model.layers[SPLIT].output, model.outputs)
inp0, out0 = trace_model(model0)
inp1 = FixedVariableArray.from_kif(*out0.kif)
_, out1 = trace_model(model1, inputs=inp1)
comb_dense = comb_trace(inp1, out1)

omap = np.array(comb_dense.inp_qint).T.reshape(3, break_n, break_output)
output_msk = (~(omap[0] == omap[1]).all(axis=0)).astype(int)
print(f'output_msk = {output_msk.tolist()}')

comb_kernel = comb_trace(inp0[:break_input], out0[:break_output] * output_msk)
assert (out0[:break_output] * output_msk).kif[0].sum() == 0, 'kernel has signed bits after relu'
kernel_pad, _ = hetero_io_map(comb_kernel.out_qint, merge=True)[-1]
dense_pad,  _ = hetero_io_map(comb_dense.inp_qint,  merge=True)[-1]
assert kernel_pad * break_n == dense_pad, f'{kernel_pad}*{break_n} != {dense_pad}'

ii, oo = trace_model(model); comb_full = comb_trace(ii, oo)
G.emit_core(comb_kernel, 'kernel', './rtl_kernel')
G.emit_core(comb_dense,  'dense',  './rtl_dense')
G.emit_core(comb_full,   'full',   './rtl_full')

xt = x_val[:32]
stage1 = float(np.max(np.abs(model.predict(xt, verbose=0).flatten() - comb_full.predict(xt, n_threads=2).flatten())))
yconv = G.partial_predict(model, xt[:8], SPLIT)
xk = xt[:8].reshape(8, break_n, break_input)
yck = np.array([[comb_kernel.predict(xk[i:i+1, w, :], n_threads=1).flatten() for w in range(4)] for i in range(8)])
stage2 = float(np.max(np.abs(yck - yconv[:, :4, :] * output_msk)))
print(f'Stage 1 (comb_full vs keras): {stage1:.6f}   Stage 2 (per-window): {stage2:.6f}')

meta = {
    'break_input': int(break_input), 'break_output': int(break_output), 'break_n': int(break_n),
    'output_msk': output_msk.tolist(),
    'kernel_pad_bits': int(kernel_pad), 'dense_pad_bits': int(dense_pad),
    'stage1_max_abs': stage1, 'stage2_max_abs': stage2,
}
json.dump(meta, open('convert_meta.json', 'w'), indent=2)
open('convert_status.txt', 'w').write(
    f'OK kernel_pad_bits={kernel_pad} dense_pad_bits={dense_pad} '
    f'stage1_diff={stage1:.6f} stage2_diff={stage2:.6f}\n')
print('convert_meta.json + convert_status.txt written')
