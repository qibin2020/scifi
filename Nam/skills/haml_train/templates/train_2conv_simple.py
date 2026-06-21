"""
v3_ref train — V3 *complex* model (2 conv + per-patch DNN + QEinsumDense tail), few epochs.
General helpers from general/hgq_rtl.py (G); SciFi I/O from common/sci_io.py (S).
Target = per-patch primary counts (20,).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'general'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
import hgq_rtl as G
import sci_io as S

import time
import h5py as h5
import numpy as np
import keras
from hgq.config import QuantizerConfig, QuantizerConfigScope, LayerConfigScope
from hgq.layers import QDense, QConv1D, QEinsumDense

# ---- training scale: FULL (debug values in comments) ----
N_TRAIN = None      # all 500k training samples           (debug: 5000)
N_VAL   = 20000     # validation subset for fit monitoring (debug: 1000); calibration uses ALL val
EPOCHS  = 1000      # full training                        (debug: 8)
N_PATCHES, PATCH_SIZE = 20, 25

def patch_targets(is_primary_500):
    return is_primary_500.reshape(-1, N_PATCHES, PATCH_SIZE).sum(axis=2).astype(np.float32)

with h5.File(f'{S.DATA_DIR}/train_v3.h5') as f:
    x_train = S.PRO_X(f['waveform500'][:N_TRAIN]); y_train = patch_targets(f['is_primary3000'][:N_TRAIN, :500])
with h5.File(f'{S.DATA_DIR}/val_v3.h5') as f:
    x_val = S.PRO_X(f['waveform500'][:N_VAL]);     y_val = patch_targets(f['is_primary3000'][:N_VAL, :500])
print(f'x_train {x_train.shape} y_train {y_train.shape} range [{y_train.min()},{y_train.max()}]')

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
t0 = time.time()
model.fit(x_train, y_train, validation_data=(x_val, y_val),
          epochs=EPOCHS, batch_size=1024, verbose=2)
print(f'train wall: {time.time()-t0:.1f}s')

G.calibrate(model, S.load_val_x())                   # trace_minmax ONCE on ALL validation data; saved with the model
mae = model.evaluate(x_val, y_val, verbose=0)[1]
print(f'val MAE after trace_minmax: {mae:.4f}')

model.save('model.keras')
open('train_status.txt', 'w').write(f'OK model.keras mae={mae:.4f} epochs={EPOCHS} architecture=2conv+DNN+einsum\n')
print('saved model.keras')
