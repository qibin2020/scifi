#!/usr/bin/env bash
# System tests: all system/ tasks (no GPU, no SLURM)
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ENV.sh"

TASKS=(
    system/hello system/basic system/edit_file system/nomem system/private_meta system/anti_inject
    system/medium system/bashtime system/subtask
    system/env_cold_pip system/env_cold_conda system/env_cold_cpp system/env_warm system/env_common
    # system/gpu → run_local_gpu.sh
)

for t in "${TASKS[@]}"; do
    echo "========================================"
    echo "  RUN: $t"
    echo "========================================"
    SciF RUN "$t" || echo "  [FAIL] $t"
    echo ""
done
