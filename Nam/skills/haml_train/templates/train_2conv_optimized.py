"""
v3_opt train — V3 *complex* model (2 conv + per-patch DNN + einsum), EBOP-constrained (PID + Pareto).

Same model + data as v3_ref, but training drives the FPGA cost (EBOPs ~ LUT/DSP) toward a target:
  * FreeEBOPs   — logs total EBOPs each epoch
  * BetaPID     — PID controller anneals the EBOP loss weight `beta` (after `warmup`) -> ebops -> TARGET_EBOPS
  * ParetoFront — saves the accuracy(val_mae) vs ebops front; pick the most accurate model WITHIN budget.
Smaller bit-widths flow through the unchanged convert/wrap pipeline -> smaller cores.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'general'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
import hgq_rtl as G
import sci_io as S

import time, shutil
import h5py as h5
import numpy as np
import keras
from hgq.config import QuantizerConfig, QuantizerConfigScope, LayerConfigScope
from hgq.layers import QDense, QConv1D, QEinsumDense
from hgq.utils.sugar import BetaPID, FreeEBOPs, ParetoFront

# ---- training scale + resource target (env SCIFI_DEBUG=1 -> fast workflow test) ----
import os
_DBG = os.environ.get('SCIFI_DEBUG') == '1'
N_TRAIN      = 5000 if _DBG else None    # debug: 5000 / full: all 500k
N_VAL        = 1000 if _DBG else 20000   # fit-monitor subset; calibration uses ALL val regardless
EPOCHS       = 12   if _DBG else 4000     # more epochs so the PID converges to the tighter target
WARMUP       = 2    if _DBG else 500      # PID warmup epochs (beta held at init_beta)
TARGET_EBOPS = 1500                       # FPGA-cost budget the PID drives toward (tight: ~1.5K EBOPs)
PARETO_DIR   = './pareto'
N_PATCHES, PATCH_SIZE = 20, 25

def patch_targets(is_primary_500):
    return is_primary_500.reshape(-1, N_PATCHES, PATCH_SIZE).sum(axis=2).astype(np.float32)

with h5.File(f'{S.DATA_DIR}/train_v3.h5') as f:
    x_train = S.PRO_X(f['waveform500'][:N_TRAIN]); y_train = patch_targets(f['is_primary3000'][:N_TRAIN, :500])
with h5.File(f'{S.DATA_DIR}/val_v3.h5') as f:
    x_val = S.PRO_X(f['waveform500'][:N_VAL]);     y_val = patch_targets(f['is_primary3000'][:N_VAL, :500])
print(f'x_train {x_train.shape} y_train {y_train.shape}  TARGET_EBOPS={TARGET_EBOPS}')

weight_scope   = QuantizerConfigScope(place=('weight', 'bias'), k0=True, b0=16, i0=8)
datalane_scope = QuantizerConfigScope(place='datalane',         k0=True, i0=8, f0=8, homogeneous_axis=(0, 1))
ebops_scope    = LayerConfigScope(enable_ebops=True, beta0=1e-7)
iq = QuantizerConfig(q_type='kbi', k0=False, b0=S.BW_INP, i0=S.BW_INP, round_mode='TRN',
                     overflow_mode='WRAP', trainable=False, is_weight=False, homogeneous_axis=(0, 1))
calib_w = QuantizerConfig(place='weight', heterogeneous_axis=())
calib_b = QuantizerConfig(place='bias',   heterogeneous_axis=())
with weight_scope, datalane_scope, ebops_scope:
    inp = keras.layers.Input((500,))
    x = inp[..., None]
    x = QConv1D(8,  25, strides=25, padding='valid', activation='relu', parallelization_factor=1,
                data_format='channels_last', iq_conf=iq)(x)
    x = QConv1D(16, 3,  strides=1,  padding='same',  activation='relu', parallelization_factor=1,
                data_format='channels_last')(x)
    x = QDense(16, parallelization_factor=1, activation='relu')(x)
    x = QDense(1,  parallelization_factor=1, activation='relu')(x)
    out = QEinsumDense('bc,c->bc', N_PATCHES, bias_axes='c', kernel_initializer='ones',
                       kq_conf=calib_w, bq_conf=calib_b)(x[..., 0])
model = keras.Model(inp, out)
model.summary()

model.compile(optimizer=keras.optimizers.Adam(1e-3), loss='mse', metrics=['mae'])

shutil.rmtree(PARETO_DIR, ignore_errors=True)
pareto = ParetoFront(PARETO_DIR, ['val_mae', 'ebops'], [-1, -1])
callbacks = [FreeEBOPs(), BetaPID(TARGET_EBOPS, init_beta=1e-7, warmup=WARMUP), pareto]

t0 = time.time()
model.fit(x_train, y_train, validation_data=(x_val, y_val),
          epochs=EPOCHS, batch_size=1024, verbose=2, callbacks=callbacks)
print(f'train wall: {time.time()-t0:.1f}s')

recs  = np.array(pareto.record); paths = pareto.paths
print(f'Pareto front: {len(paths)} points  (val_mae, ebops):')
for r, p in sorted(zip(recs.tolist(), paths)): print(f'  {r[0]:.4f}  {r[1]:.0f}   {Path(p).name}')
if len(paths) == 0:
    sel = model
else:
    within = recs[:, 1] <= TARGET_EBOPS * 1.10
    cand = np.where(within)[0] if within.any() else np.array([int(np.argmin(recs[:, 1]))])
    bi = int(cand[int(np.argmin(recs[cand, 0]))])
    print(f'selected: val_mae={recs[bi,0]:.4f} @ ebops={recs[bi,1]:.0f}  ->  {Path(paths[bi]).name}')
    sel = keras.saving.load_model(paths[bi])

G.calibrate(sel, S.load_val_x())
mae = sel.evaluate(x_val, y_val, verbose=0)[1]
print(f'val MAE after trace_minmax: {mae:.4f}')
sel.save('model.keras')
open('train_status.txt', 'w').write(
    f'OK model.keras mae={mae:.4f} epochs={EPOCHS} target_ebops={TARGET_EBOPS} architecture=2conv+DNN+einsum\n')
print('saved model.keras')
