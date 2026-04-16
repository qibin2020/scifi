#!/usr/bin/env bash
# Sci study: all sci_study/ tasks that don't need GPU or SLURM
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ENV.sh"

TASKS=(
    sci_study/fw_bootstrap
    sci_study/fw_debug
    sci_study/fw_complete1
    sci_study/fw_complete1_detailed
    sci_study/fw_complete2
    sci_study/fw_complete2_detailed
    sci_study/fw_complete3
    sci_study/fw_complete3_detailed
    sci_study/fw_complete3_tiny
    sci_study/lhco_CWoLa_VAE_detailed
    # GPU tasks → run_local_gpu.sh: calo-vq_rep
    # SLURM tasks → run_slurm.sh: calo-vq_rep_refined
)

for t in "${TASKS[@]}"; do
    echo "========================================"
    echo "  RUN: $t"
    echo "========================================"
    SciF RUN "$t" || echo "  [FAIL] $t"
    echo ""
done
