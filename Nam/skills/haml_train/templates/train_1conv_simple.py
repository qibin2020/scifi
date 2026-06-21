"""
v1_ref train — V1 *simple* model (1 conv + 3 dense), few epochs (workflow check only).
Project-agnostic helpers from general/hgq_rtl.py (G); SciFi I/O from common/sci_io.py (S).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'general'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
import hgq_rtl as G          # sets jax backend + GPU env on import
import sci_io as S

import time
import h5py as h5
import keras
from hgq.config import QuantizerConfig, QuantizerConfigScope, LayerConfigScope
from hgq.layers import QDense, QConv1D

# ---- training scale: FULL (debug values in comments) ----
N_TRAIN = None      # all 500k training samples           (debug: 5000)
N_VAL   = 20000     # validation subset for fit monitoring (debug: 1000); calibration uses ALL val
EPOCHS  = 1000      # full training                        (debug: 5)
with h5.File(f'{S.DATA_DIR}/train_v3.h5') as f:
    x_train = S.PRO_X(f['waveform500'][:N_TRAIN]); y_train = S.PRO_Y(f['predict500'][:N_TRAIN])
with h5.File(f'{S.DATA_DIR}/val_v3.h5') as f:
    x_val = S.PRO_X(f['waveform500'][:N_VAL]);     y_val = S.PRO_Y(f['predict500'][:N_VAL])
print(f'x_train {x_train.shape} range=[{x_train.min()},{x_train.max()}]')

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
t0 = time.time()
model.fit(x_train, y_train, validation_data=(x_val, y_val),
          epochs=EPOCHS, batch_size=1024, verbose=2)
print(f'train wall: {time.time()-t0:.1f}s')

G.calibrate(model, S.load_val_x())                   # trace_minmax ONCE on ALL validation data; saved with the model
mae = model.evaluate(x_val, y_val, verbose=0)[1]
print(f'val MAE after trace_minmax: {mae:.4f}')

model.save('model.keras')
open('train_status.txt', 'w').write(f'OK model.keras mae={mae:.4f} epochs={EPOCHS}\n')
print('saved model.keras')
