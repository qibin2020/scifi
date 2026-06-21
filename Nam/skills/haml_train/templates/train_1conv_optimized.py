"""
v1_opt train — V1 *simple* model, EBOP/resource-constrained training (PID + Pareto).

Same model + data as v1_ref, but training drives the FPGA cost (EBOPs ~ LUT/DSP) toward a target:
  * FreeEBOPs   — logs the model's total EBOPs each epoch
  * BetaPID     — a PID controller that anneals the EBOP loss weight `beta` (after `warmup` epochs)
                  to drive ebops -> TARGET_EBOPS (this is what shrinks the quantizer bit-widths)
  * ParetoFront — saves the accuracy(val_mae) vs ebops front; we then pick the most accurate model
                  WITHIN the EBOP budget and calibrate it once on all validation data.

The smaller bit-widths flow straight through the (unchanged) convert/wrap pipeline -> smaller cores.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'general'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
import hgq_rtl as G          # sets jax backend + GPU env on import
import sci_io as S

import time, shutil
import h5py as h5
import numpy as np
import keras
from hgq.config import QuantizerConfig, QuantizerConfigScope, LayerConfigScope
from hgq.layers import QDense, QConv1D
from hgq.utils.sugar import BetaPID, FreeEBOPs, ParetoFront

# ---- training scale + resource target (env SCIFI_DEBUG=1 -> fast workflow test) ----
import os
_DBG = os.environ.get('SCIFI_DEBUG') == '1'
N_TRAIN      = 5000 if _DBG else None    # debug: 5000 / full: all 500k
N_VAL        = 1000 if _DBG else 20000   # fit-monitor subset; calibration uses ALL val regardless
EPOCHS       = 12   if _DBG else 4000    # more epochs so the PID converges to the tighter target
WARMUP       = 2    if _DBG else 500     # PID warmup epochs (beta held at init_beta)
TARGET_EBOPS = 1500                      # FPGA-cost budget the PID drives toward (tight: ~1.5K EBOPs)
PARETO_DIR   = './pareto'

with h5.File(f'{S.DATA_DIR}/train_v3.h5') as f:
    x_train = S.PRO_X(f['waveform500'][:N_TRAIN]); y_train = S.PRO_Y(f['predict500'][:N_TRAIN])
with h5.File(f'{S.DATA_DIR}/val_v3.h5') as f:
    x_val = S.PRO_X(f['waveform500'][:N_VAL]);     y_val = S.PRO_Y(f['predict500'][:N_VAL])
print(f'x_train {x_train.shape}  TARGET_EBOPS={TARGET_EBOPS}')

default_scope1 = QuantizerConfigScope(place=('weight', 'bias'), k0=True, b0=16, i0=8)
default_scope2 = QuantizerConfigScope(place='datalane',         k0=True, i0=8,  f0=8)
default_scope3 = LayerConfigScope(enable_ebops=True, beta0=1e-7)
input_follow_ADC = QuantizerConfig(q_type='kbi', k0=False, i0=S.BW_INP, b0=S.BW_INP,
                                   round_mode='TRN', overflow_mode='WRAP',
                                   trainable=False, is_weight=False, homogeneous_axis=(0, 1))
with default_scope1, default_scope2, default_scope3:
    inp = keras.layers.Input((500,))
    x = keras.layers.Reshape((500, 1))(inp)
    x = QConv1D(filters=5, kernel_size=25, strides=25, padding='valid', activation='relu',
                parallelization_factor=1, data_format='channels_last', iq_conf=input_follow_ADC)(x)
    x = keras.layers.Flatten()(x)
    x = QDense(16, activation='relu')(x)
    x = QDense(8,  activation='relu')(x)
    out = QDense(1, activation='relu')(x)
model = keras.Model(inp, out)
model.summary()

model.compile(optimizer=keras.optimizers.Adam(1e-3), loss='mse', metrics=['mae'])

shutil.rmtree(PARETO_DIR, ignore_errors=True)
pareto = ParetoFront(PARETO_DIR, ['val_mae', 'ebops'], [-1, -1])   # minimize both
callbacks = [FreeEBOPs(), BetaPID(TARGET_EBOPS, init_beta=1e-7, warmup=WARMUP), pareto]

t0 = time.time()
model.fit(x_train, y_train, validation_data=(x_val, y_val),
          epochs=EPOCHS, batch_size=1024, verbose=2, callbacks=callbacks)
print(f'train wall: {time.time()-t0:.1f}s')

# ---- select the most accurate Pareto model WITHIN the EBOP budget ----
recs  = np.array(pareto.record)                 # rows: [val_mae, ebops]
paths = pareto.paths
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

G.calibrate(sel, S.load_val_x())                # calibrate ONCE on ALL validation data; saved with model
mae = sel.evaluate(x_val, y_val, verbose=0)[1]
print(f'val MAE after trace_minmax: {mae:.4f}')
sel.save('model.keras')
open('train_status.txt', 'w').write(f'OK model.keras mae={mae:.4f} epochs={EPOCHS} target_ebops={TARGET_EBOPS}\n')
print('saved model.keras')
