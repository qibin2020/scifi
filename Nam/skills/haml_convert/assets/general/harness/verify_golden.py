"""
verify_golden.py — drive the verilator-compiled stream_wrapper via the
5-arg `inference(c_inp, c_out, n_samples, pause_prob, seed)` binder,
compare to ../dataset/golden_Y.csv. Prints `PASSED: All` on bit-exact match.

Usage from wrap_pkg/sim/:
    python3 verify_golden.py --no-pause
    python3 verify_golden.py --inp-pause 0.3 --seed 42
"""

import argparse
import ctypes
import glob
import subprocess
import sys
from pathlib import Path

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-pause',  action='store_true')
    ap.add_argument('--inp-pause', type=float, default=0.0,
                    help='per-clock probability to hold inp_valid low')
    ap.add_argument('--seed',      type=int,   default=0)
    ap.add_argument('--dataset',   type=str,   default='../dataset',
                    help='directory holding golden_X.csv and golden_Y.csv')
    args = ap.parse_args()

    pause_prob = 0.0 if args.no_pause else float(args.inp_pause)
    seed = int(args.seed)
    print(f'mode: inp_pause_prob={pause_prob} seed={seed}')

    # ---- Build the shared library on demand ----------------------------------
    print('building libstream_wrapper_*.so ...')
    rc = subprocess.run(['make', '-f', 'build_binder.mk', 'slow'],
                        check=False).returncode
    if rc != 0:
        print('FAILED: build returned non-zero', rc); sys.exit(1)

    so_paths = sorted(glob.glob('libstream_wrapper_*.so'))
    if not so_paths:
        print('FAILED: no libstream_wrapper_*.so found after build'); sys.exit(1)
    so_path = str(Path(so_paths[-1]).resolve())
    print(f'loading {so_path}')

    lib = ctypes.CDLL(so_path)
    lib.inference.argtypes = [
        ctypes.POINTER(ctypes.c_int32),  # c_inp
        ctypes.POINTER(ctypes.c_int32),  # c_out
        ctypes.c_size_t,                  # n_samples
        ctypes.c_double,                  # inp_pause_prob
        ctypes.c_uint32,                  # seed
    ]
    lib.inference.restype = ctypes.c_size_t

    # ---- Load golden dataset ------------------------------------------------
    X = np.loadtxt(Path(args.dataset) / 'golden_X.csv',
                   delimiter=',', dtype=np.int32)
    Y = np.loadtxt(Path(args.dataset) / 'golden_Y.csv',
                   delimiter=',', dtype=np.int32)
    if Y.ndim == 1:
        Y = Y.reshape(-1, 1)
    n_samples, n_inp = X.shape
    print(f'golden_X: {X.shape}  golden_Y: {Y.shape}')

    c_inp = X.reshape(-1).astype(np.int32, copy=False)
    c_out = np.zeros(n_samples * Y.shape[1], dtype=np.int32)

    n_out = lib.inference(
        c_inp.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        c_out.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        ctypes.c_size_t(n_samples),
        ctypes.c_double(pause_prob),
        ctypes.c_uint32(seed),
    )
    expected = n_samples * Y.shape[1]
    print(f'inference returned n_out={n_out} (expected {expected} = {n_samples}x{Y.shape[1]})')
    if n_out != expected:
        print(f'FAILED: only {n_out}/{expected} outputs collected'); sys.exit(1)

    Y_dut = c_out.reshape(n_samples, -1).astype(np.int32)

    # Bit-exact compare
    eq = np.all(Y_dut == Y)
    if eq:
        print(f'PASSED: All {n_samples} outputs match exactly')
    else:
        n_diff = int(np.sum(np.any(Y_dut != Y, axis=1)))
        worst  = int(np.max(np.abs(Y_dut - Y)))
        print(f'FAILED: {n_diff}/{n_samples} outputs mismatch, worst |diff|={worst}')
        print(f'  first 5 expected: {Y[:5, 0].tolist()}')
        print(f'  first 5 got:      {Y_dut[:5, 0].tolist()}')
        sys.exit(1)


if __name__ == '__main__':
    main()
