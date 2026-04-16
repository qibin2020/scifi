#!/usr/bin/env bash
# Sci bench: all sci_bench/ tasks that don't need GPU or SLURM
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ENV.sh"

TASKS=(
    sci_bench/sci_file_ops
    sci_bench/sci_h5_io
    sci_bench/sci_matplotlib_basic
    sci_bench/sci_matplotlib_mnist
    sci_bench/sci_pandas_csv
    sci_bench/sci_mnt_share_read
    sci_bench/sci_root_install
    sci_bench/sci_root_gauss_fit
    sci_bench/sci_skill_install
    sci_bench/sci_skill_invoke
    sci_bench/sci_skill_reuse
    sci_bench/sci_web_paper
    sci_bench/sci_impossible_prime
    sci_bench/sci_chain_mnt_persist
    sci_bench/sci_chain_paper_to_code
    sci_bench/sci_chain_root_pipeline
    sci_bench/bench_algo_design
    sci_bench/bench_data_pipeline
    sci_bench/bench_debug_trace
    sci_bench/bench_env_discover
    sci_bench/bench_env_setup
    sci_bench/bench_error_adapt
    sci_bench/bench_logic_puzzle
    sci_bench/bench_multifile
    sci_bench/bench_shortcut
    sci_bench/bench_token_economy
    # GPU tasks → run_local_gpu.sh: sci_torch_smoke, sci_mnist_train_local, sci_mnist_train_multigpu, sci_chain_mnist_full
    # SLURM tasks → run_slurm.sh: sci_slurm_hello, sci_slurm_gpu_mnist, sci_chain_slurm_train_eval
)

for t in "${TASKS[@]}"; do
    echo "========================================"
    echo "  RUN: $t"
    echo "========================================"
    SciF RUN "$t" || echo "  [FAIL] $t"
    echo ""
done
