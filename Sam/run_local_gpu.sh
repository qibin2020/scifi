#!/usr/bin/env bash
# GPU tests: all tasks with GPU: local|on (no SLURM)
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ENV.sh"

if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "SKIP: no GPU detected (nvidia-smi not found)"
    exit 0
fi

TASKS=(
    system/gpu
    sci_bench/sci_torch_smoke
    sci_bench/sci_mnist_train_local
    sci_bench/sci_mnist_train_multigpu
    sci_bench/sci_chain_mnist_full
    sci_bench_task_maker/sci_torch_smoke
    sci_bench_task_maker/sci_mnist_train_local
    sci_bench_task_maker/sci_mnist_train_multigpu
    sci_bench_task_maker/sci_chain_mnist_full
    sci_study/calo-vq_rep
)

for t in "${TASKS[@]}"; do
    echo "========================================"
    echo "  RUN: $t"
    echo "========================================"
    SciF RUN "$t" || echo "  [FAIL] $t"
    echo ""
done
