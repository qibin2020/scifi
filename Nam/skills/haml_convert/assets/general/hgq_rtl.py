"""
general/hgq_rtl.py — project-agnostic HGQ -> da4ml -> RTL helpers.

No model / dataset / architecture assumptions. Reusable across ANY streaming-quantized
HGQ model: environment setup, generic fixed-point digitization, trace_minmax calibration,
raw da4ml inference, da4ml core emission, and the comb_full end-to-end software golden.

Project-specific I/O (ADC calibration constants, dataset schema) lives outside this file
(see common/sci_io.py). Import this BEFORE `import keras` — it sets KERAS_BACKEND on import.
"""
import os
os.environ.setdefault('KERAS_BACKEND', 'jax')
os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')                # respect external GPU choice
os.environ.setdefault('XLA_PYTHON_CLIENT_PREALLOCATE', 'false')   # don't grab the whole card

import ctypes
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from types import MethodType

import numpy as np
import keras

import hgq  # noqa: F401
from hgq.utils import trace_minmax
from da4ml.codegen import RTLModel
from da4ml.codegen.rtl.rtl_model import get_io_kifs, at_path
from da4ml.converter import trace_model
from da4ml.trace import comb_trace


# ---- generic fixed-point digitization (a project wraps this with its own vmin/vmax/bits) ----
def re_digi(d, vmin, vmax, bits, norm1=False):
    a = np.clip((d - vmin) / (vmax - vmin), 0, 1)
    step = 1 / (2 ** bits)
    code = np.clip(np.floor(a / step + 1e-12), 0, 2 ** bits - 1)
    return code * step if norm1 else code


def calibrate(model, x):
    """trace_minmax on representative inputs — mandatory before any da4ml tracing."""
    trace_minmax(model, x, reset=True, verbose=False)
    return model


def partial_predict(model, x, up_to_layer_idx):
    """Keras forward up to a layer (per-stage convert validation)."""
    return keras.Model(model.inputs, model.layers[up_to_layer_idx].output).predict(x, verbose=0)


def emit_core(comb, name, path):
    """Write a da4ml combinational core to `path` (wipes it first)."""
    if Path(path).exists():
        shutil.rmtree(path)
    RTLModel(comb, name, str(path)).write()
    return path


# ---- raw int32 inference on a compiled da4ml RTLModel (V1 gen_golden recipe) ----
def predict_raw(self, data, n_threads=0):
    if isinstance(data, Sequence):
        data = np.concatenate([a.reshape(a.shape[0], -1) for a in data], axis=-1)
    inp_size, out_size = self._solution.shape
    n_sample = data.size // inp_size
    kifs_in, kifs_out = get_io_kifs(self._solution)
    f_in = np.max(kifs_in[2])
    k_out, i_out, f_out = map(np.max, (kifs_out[0], kifs_out[1], kifs_out[2]))
    inp = np.empty(n_sample * inp_size, np.int32)
    out = np.empty(n_sample * out_size, np.int32)
    inp[:] = np.floor(data.ravel() * 2.0 ** f_in)
    with at_path(self._path / 'src/memfiles'):
        self._lib.inference(inp.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                            out.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), n_sample, n_threads)
    k, i, f = int(k_out), int(i_out), int(f_out)
    raw = out.reshape(n_sample, out_size).astype(np.int32)
    dequa = ((raw + k * 2.0 ** (i + f)) % 2.0 ** (k + i + f) - k * 2.0 ** (i + f)) * np.float32(2.0 ** -f)
    return (k, i, f), raw, dequa


# ---- comb_full: the end-to-end software golden (whole model, bit-exact to keras) ----
def comb_full_golden(model, x, path='./rtl_full'):
    """Trace the WHOLE model -> comb_full -> compile -> predict_raw -> sign-correct.

    Returns (kif, golden_signed[int64 (N,nout)], dequa[float (N,nout)]). Works for any
    output width (scalar or vector); the RTL composed from the kernels must reproduce this.
    """
    ii, oo = trace_model(model)
    cf = comb_trace(ii, oo)
    p = Path(path)
    if p.exists():
        shutil.rmtree(p)
    rt = RTLModel(cf, 'full', str(path)); rt.write(); rt._compile()
    rt.predict_raw = MethodType(predict_raw, rt)
    kif, raw, dequa = rt.predict_raw(np.asarray(x).astype(np.int32))
    k, i, f = kif
    half, full = k * 2 ** (i + f), 2 ** (k + i + f)
    signed = ((raw.astype(np.int64) + half) % full - half).astype(np.int64)   # unsigned bits -> signed int
    return kif, signed, dequa


def write_golden(model, x, outdir='golden', meta_path='convert_meta.json'):
    """Generate + persist the software golden for the streaming RTL to match.

      golden/golden_X.csv  the inputs            golden/golden_Y.csv  signed per-output raw int
    If `meta_path` exists, record the output kif / total output bit width into it.
    """
    kif, signed, dequa = comb_full_golden(model, x)
    yk = model.predict(x, verbose=0).reshape(len(x), -1)
    out = Path(outdir); out.mkdir(exist_ok=True)
    np.savetxt(out / 'golden_X.csv', np.asarray(x).astype(np.int64), fmt='%d', delimiter=',')
    np.savetxt(out / 'golden_Y.csv', signed,                          fmt='%d', delimiter=',')
    if Path(meta_path).exists():
        m = json.load(open(meta_path))
        m['golden_out_kif'] = list(kif)
        m['output_bw_total'] = int(sum(kif))
        json.dump(m, open(meta_path, 'w'), indent=2)
    return kif, signed, dequa, yk
