"""
common/sci_io.py — PROJECT-SPECIFIC I/O for the hardware-aware ML -> RTL pipeline.

This is the ONE place that encodes the project's input digitization (ADC calibration) and dataset
schema. Everything downstream (train, convert, golden) reads through it. Fill every <FILL ...> from
the spec.json the haml_analyze skill produced. Self-contained (numpy + h5py only) so train.py can
import it without the heavier general/ library.
"""
import h5py as h5
import numpy as np

# ----- dataset schema (from spec.data) -----
DATA_DIR  = '<FILL data.dir>'          # e.g. /mnt/sci_shared/data (shared storage the driver auto-maps)
TRAIN_H5  = '<FILL data.train>'        # e.g. train_v3.h5
VAL_H5    = '<FILL data.val>'          # e.g. val_v3.h5
X_KEY     = '<FILL data.x_key>'        # e.g. waveform500   (shape (N, input_len))

# ----- input digitization (from spec.input) -----
BW_INP = <FILL input.bw_inp>           # ADC bit width = ceil(log2(#codes)); e.g. 10
VMIN, VMAX = <FILL input.vmin>, <FILL input.vmax>   # ADC calibration window; e.g. -0.2, 40.0

def re_digi(d, vmin, vmax, bits, norm1=False):
    a = np.clip((d - vmin) / (vmax - vmin), 0, 1)
    step = 1 / (2 ** bits)
    code = np.clip(np.floor(a / step + 1e-12), 0, 2 ** bits - 1)
    return code * step if norm1 else code

def PRO_X(x):                          # input -> BW_INP-bit ADC codes
    return re_digi(x, VMIN, VMAX, BW_INP)

def PRO_Y(x):                          # target codes (adapt to the project's target transform)
    return re_digi(x, 0, 2 ** BW_INP - 1, BW_INP)

def load_val_x(n=None, split='val'):
    """PRO_X-digitized validation inputs. n=None loads the ENTIRE split (for calibration)."""
    with h5.File(f'{DATA_DIR}/{VAL_H5 if split == "val" else TRAIN_H5}') as f:
        wf = f[X_KEY]
        return PRO_X(wf[:] if n is None else wf[:n])
