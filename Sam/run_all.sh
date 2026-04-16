#!/usr/bin/env bash
# Run all test suites in order
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============ SYSTEM ============"
bash "$DIR/run_system.sh"

echo "============ SCI BENCH ============"
bash "$DIR/run_sci_bench.sh"

echo "============ SCI BENCH TASK MAKER ============"
bash "$DIR/run_sci_bench_task_maker.sh"

echo "============ SCI STUDY ============"
bash "$DIR/run_sci_study.sh"

echo "============ LOCAL GPU ============"
bash "$DIR/run_local_gpu.sh"

echo "============ SLURM ============"
bash "$DIR/run_slurm.sh"
