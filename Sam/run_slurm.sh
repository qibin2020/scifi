#!/usr/bin/env bash
# SLURM tests: all tasks requiring SLURM cluster access
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ENV.sh"

if ! command -v sbatch >/dev/null 2>&1; then
    echo "SKIP: no SLURM detected (sbatch not found)"
    exit 0
fi

TASKS=(
    sci_bench/sci_slurm_hello
    sci_bench/sci_slurm_gpu_mnist
    sci_bench/sci_chain_slurm_train_eval
    sci_bench_task_maker/sci_slurm_hello
    sci_bench_task_maker/sci_slurm_gpu_mnist
    sci_bench_task_maker/sci_chain_slurm_train_eval
    sci_study/calo-vq_rep_refined
)

for t in "${TASKS[@]}"; do
    echo "========================================"
    echo "  RUN: $t"
    echo "========================================"
    SciF RUN "$t" || echo "  [FAIL] $t"
    echo ""
done
