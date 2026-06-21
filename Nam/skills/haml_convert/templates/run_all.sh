#!/bin/bash
# v1_ref/run_all.sh — end-to-end ground-truth pipeline for the V1 *simple* model (1 conv).
#   train -> convert -> gen_golden (shared) -> assemble wrap_pkg -> verify (both modes, bit-exact).
# Datasets generated on the fly from the shared HGQ h5 files. All RTL widths derived per-model.
# Multi-GPU: `export CUDA_VISIBLE_DEVICES=N` before running (scripts respect it, no preallocation).
set -e
cd "$(dirname "$0")"
# Toolchain: this script assumes the env is ALREADY active (python3/jax/da4ml/verilator/make/g++ on
# PATH). Under scifi that means you ran `activate_env(.../fpga_toolchain/envs/hgq)` (common_env skill)
# first, so every command here inherits it. Outside scifi, activate the env however you normally do.
command -v verilator >/dev/null 2>&1 || { echo "ERROR: toolchain not on PATH — activate the shared env (common_env / activate_env) before running run_all.sh" >&2; exit 1; }

echo "==================== [1/5] train ===================="
python3 train.py
echo "==================== [2/5] convert =================="
python3 convert.py
echo "==================== [3/5] gen_golden (shared) ======"
python3 ../common/gen_golden.py
echo "==================== [4/5] assemble wrap_pkg ========"
python3 assemble_wrap.py
echo "==================== [5/5] verify (both modes) ======"
cd wrap_pkg/sim
echo "----- no-pause -----";              python3 verify_golden.py --no-pause
echo "----- inp-pause 0.3 seed 42 -----"; python3 verify_golden.py --inp-pause 0.3 --seed 42
echo "==================== DONE ============================"
