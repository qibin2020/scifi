#!/usr/bin/env bash
# Sci bench task maker: all sci_bench_task_maker/ tasks that don't need GPU or SLURM
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ENV.sh"

TASKS=(
    sci_bench_task_maker/sci_file_ops
    sci_bench_task_maker/sci_h5_io
    sci_bench_task_maker/sci_matplotlib_basic
    sci_bench_task_maker/sci_matplotlib_mnist
    sci_bench_task_maker/sci_pandas_csv
    sci_bench_task_maker/sci_mnt_share_read
    sci_bench_task_maker/sci_root_install
    sci_bench_task_maker/sci_root_gauss_fit
    sci_bench_task_maker/sci_skill_gauss
    sci_bench_task_maker/sci_skill_install
    sci_bench_task_maker/sci_skill_invoke
    sci_bench_task_maker/sci_skill_reuse
    sci_bench_task_maker/sci_web_paper
    sci_bench_task_maker/sci_chain_mnt_persist
    sci_bench_task_maker/sci_chain_paper_to_code
    sci_bench_task_maker/sci_chain_root_pipeline
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
