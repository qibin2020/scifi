#!/bin/bash
# Auto-generated SLURM wrapper for: {{USER_SCRIPT}}
# Pattern: 1 node, 1 task, 1 GPU — shared QOS
# Use for: single-GPU training, inference, experiments
# Generated: {{DATE}}

#SBATCH -A {{ACCOUNT}}
#SBATCH -C gpu
#SBATCH -q shared
#SBATCH -t {{WALLTIME}}            # VERIFY: adjust to your estimated runtime
#SBATCH -n 1
#SBATCH -c 32                      # mandatory: 32 CPUs per GPU on gpu_shared
#SBATCH --gpus-per-task=1
#SBATCH --job-name={{JOBNAME}}     # VERIFY: descriptive job name
#SBATCH --output=slurm_%x-%j.out
#SBATCH --error=slurm_%x-%j.err

# --- Job Info ---
echo "=== SLURM Job ==="
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURM_NODELIST"
echo "Start:     $(date)"
echo "Script:    {{USER_SCRIPT}}"
echo ""

# --- Working Directory ---
WORKDIR={{WORKDIR}}
cd "$WORKDIR" || { echo "ERROR: cannot cd to $WORKDIR"; exit 1; }

# --- Environment ---
source /pscratch/sd/b/binus/Playground/slurm_system/env_setup.sh



# --- GPU Check ---
echo "--- GPU Info ---"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null \
    || echo "(no GPU detected)"

# --- CPU Binding (required for GPU jobs) ---
export SLURM_CPU_BIND="cores"

# =============================================================================
# MAIN COMMAND
# =============================================================================
srun {{LAUNCH_CMD}}

echo ""
echo "Done: $(date)"
