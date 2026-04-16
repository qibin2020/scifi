#!/usr/bin/env python3
"""
Verify stream_wrapper RTL against golden dataset via Verilator shared library.

Usage:
    python verify_golden.py [--inp-pause 0.0] [--seed 42]
    python verify_golden.py --inp-pause 0.3 --seed 42   # test with pauses
    python verify_golden.py --no-pause                   # deterministic baseline
"""

import argparse
import ctypes
import glob
import os
import subprocess
import sys

import numpy as np


def make_clean():
    subprocess.run(["make", "-f", "build_binder.mk", "clean"], check=True)

def make_build():
    subprocess.run(["make", "-f", "build_binder.mk", "slow"], check=True)


def find_lib():
    candidates = sorted(glob.glob("libstream_wrapper_*.so"))
    if not candidates:
        return None
    return candidates[-1]


def load_lib(path):
    lib = ctypes.CDLL(os.path.abspath(path))
    lib.inference.argtypes = [
        ctypes.POINTER(ctypes.c_int32),   # c_inp
        ctypes.POINTER(ctypes.c_int32),   # c_out
        ctypes.c_size_t,                  # n_samples
        ctypes.c_double,                  # inp_pause_prob
        ctypes.c_uint32,                  # seed
    ]
    lib.inference.restype = ctypes.c_size_t
    return lib


def load_golden(dataset_dir):
    golden_x = np.loadtxt(os.path.join(dataset_dir, "golden_X.csv"), delimiter=",", dtype=np.int32)
    golden_y = np.loadtxt(os.path.join(dataset_dir, "golden_Y.csv"), delimiter=",", dtype=np.int32)
    if golden_x.ndim == 1:
        golden_x = golden_x.reshape(1, -1)
    if golden_y.ndim == 0:
        golden_y = golden_y.reshape(1)
    n = golden_x.shape[0]
    assert golden_x.shape[1] == 500, f"Expected 500 input features, got {golden_x.shape[1]}"
    assert golden_y.shape[0] == n
    print(f"Loaded {n} golden samples (X: {golden_x.shape}, Y: {golden_y.shape})")
    return golden_x, golden_y


def run_inference(lib, golden_x, inp_pause_prob, seed):
    n_samples = golden_x.shape[0]
    x_flat = np.ascontiguousarray(golden_x.ravel(), dtype=np.int32)
    out_buf = np.zeros(n_samples, dtype=np.int32)

    inp_ptr = x_flat.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
    out_ptr = out_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))

    n_out = lib.inference(inp_ptr, out_ptr, n_samples, inp_pause_prob, seed)
    print(f"Inference returned {n_out} outputs (expected {n_samples})")
    return out_buf[:n_out], n_out


def verify(golden_y, rtl_y):
    n = min(len(golden_y), len(rtl_y))
    mismatches = []

    for i in range(n):
        g, r = int(golden_y[i]), int(rtl_y[i])
        if g != r:
            mismatches.append((i, g, r))

    if len(mismatches) == 0:
        print(f"\nPASSED: All {n} outputs match golden reference.")
    else:
        print(f"\nFAILED: {len(mismatches)}/{n} mismatches")
        for i, g, r in mismatches[:10]:
            print(f"  sample {i}: golden={g}, rtl={r}")
        if len(mismatches) > 10:
            print(f"  ... and {len(mismatches) - 10} more")

    return len(mismatches) == 0


def main():
    parser = argparse.ArgumentParser(description="Verify stream_wrapper RTL against golden dataset")
    parser.add_argument("--dataset", type=str, default="../dataset")
    parser.add_argument("--inp-pause", type=float, default=0.0,
                        help="Probability of inp_valid pause (default: 0.0 = no pauses)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-pause", action="store_true")
    parser.add_argument("--no-build", action="store_true", help="Skip rebuild")
    args = parser.parse_args()

    if args.no_pause:
        args.inp_pause = 0.0

    if not args.no_build:
        make_clean()
        make_build()

    print(f"inp_pause_prob: {args.inp_pause}")
    print(f"seed:           {args.seed}")
    print()

    lib_path = find_lib()
    assert lib_path is not None, "No .so found"
    lib = load_lib(lib_path)
    golden_x, golden_y = load_golden(args.dataset)
    rtl_y, n_out = run_inference(lib, golden_x, args.inp_pause, args.seed)

    if n_out < len(golden_y):
        print(f"WARNING: only got {n_out} outputs, expected {len(golden_y)}")

    passed = verify(golden_y, rtl_y)

    if not args.no_build:
        make_clean()

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
