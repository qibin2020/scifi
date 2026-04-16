#!/bin/bash
# Auto-generated SLURM wrapper for: {{USER_SCRIPT}}
# Pattern: CPU-only — regular QOS (full node: 128 cores / 256 threads, 512G RAM)
# Use for: heavy preprocessing, large parallel CPU workloads
# Generated: {{DATE}}

#SBATCH -A {{ACCOUNT}}
#SBATCH -C cpu
#SBATCH -q regular
#SBATCH -t {{WALLTIME}}            # VERIFY: adjust to your estimated runtime
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH -c 256
#SBATCH --job-name={{JOBNAME}}     # VERIFY: descriptive job name
#SBATCH --output=slurm_%x-%j.out
#SBATCH --error=slurm_%x-%j.err

# --- Job Info ---
echo "=== SLURM Job ==="
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURM_NODELIST"
echo "CPUs:      256 (full node)"
echo "Start:     $(date)"
echo "Script:    {{USER_SCRIPT}}"
echo ""

# --- Working Directory ---
WORKDIR={{WORKDIR}}
cd "$WORKDIR" || { echo "ERROR: cannot cd to $WORKDIR"; exit 1; }

# --- Environment ---
source /pscratch/sd/b/binus/Playground/slurm_system/env_setup.sh



# =============================================================================
# MAIN COMMAND
# =============================================================================
srun {{LAUNCH_CMD}}

echo ""
echo "Done: $(date)"
