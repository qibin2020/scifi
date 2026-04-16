#!/bin/bash
# Auto-generated SLURM wrapper for: {{USER_SCRIPT}}
# Pattern: 1 node, 4 tasks, 4 GPUs — regular QOS (all GPUs visible to all tasks)
# Use for: frameworks that manage their own GPU assignment (Horovod, custom CUDA)
# Generated: {{DATE}}

#SBATCH -A {{ACCOUNT}}
#SBATCH -C gpu
#SBATCH -q regular
#SBATCH -t {{WALLTIME}}            # VERIFY: adjust to your estimated runtime
#SBATCH -N 1
#SBATCH --ntasks-per-node=4
#SBATCH -c 32
#SBATCH --gpus-per-task=1
#SBATCH --gpu-bind=none
#SBATCH --job-name={{JOBNAME}}     # VERIFY: descriptive job name
#SBATCH --output=slurm_%x-%j.out
#SBATCH --error=slurm_%x-%j.err

# --- Job Info ---
echo "=== SLURM Job ==="
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURM_NODELIST"
echo "GPUs:      4 (all visible to each task)"
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
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>/dev/null \
    || echo "(no GPU detected)"

# --- CPU Binding (required for GPU jobs) ---
export SLURM_CPU_BIND="cores"

# =============================================================================
# MAIN COMMAND
# =============================================================================
srun {{LAUNCH_CMD}}

echo ""
echo "Done: $(date)"
