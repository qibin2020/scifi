"""
common/gen_golden.py — SciFi golden driver: wire the project's val inputs into general.write_golden.

Identical for every topology. Run from a package dir:  python3 ../common/gen_golden.py
The actual golden generation (comb_full end-to-end sim + sign-correction) lives in general/hgq_rtl.py.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'general'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hgq_rtl as G   # env first
import sci_io as S
import numpy as np
import keras

model = keras.saving.load_model('model.keras')   # already calibrated at train time (trace_minmax saved); do NOT re-calibrate

xg = S.load_val_x(100).astype(np.int32)[:100]
kif, signed, dequa, yk = G.write_golden(model, xg)
print(f'comb_full out kif={kif}  golden.shape={signed.shape}')
print(f'dequa vs keras max|d| = {float(np.max(np.abs(dequa - yk))):.6f}  (0 => golden bit-exact to keras)')
print(f'wrote golden/golden_X.csv {xg.shape}  golden/golden_Y.csv {signed.shape}  '
      f'range [{int(signed.min())},{int(signed.max())}]')
