#!/bin/bash
# Auto-generated SLURM wrapper for: {{USER_SCRIPT}}
# Pattern: Multiple independent single-GPU tasks in parallel (srun --exact)
# Use for: running N independent experiments simultaneously, each on its own GPU
# Generated: {{DATE}}

#SBATCH -A {{ACCOUNT}}
#SBATCH -C gpu
#SBATCH -q regular
#SBATCH -t {{WALLTIME}}            # VERIFY: max runtime for any single task
#SBATCH -N 1
#SBATCH --ntasks-per-node={{NUM_TASKS}}
#SBATCH --job-name={{JOBNAME}}     # VERIFY: descriptive job name
#SBATCH --output=slurm_%x-%j.out
#SBATCH --error=slurm_%x-%j.err

# --- Job Info ---
echo "=== SLURM Job ==="
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURM_NODELIST"
echo "Tasks:     {{NUM_TASKS}} parallel"
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
# PARALLEL TASKS — each gets 1 GPU via srun --exact
# The & sends each to background; wait blocks until all complete.
# =============================================================================
{{PARALLEL_SRUN_BLOCK}}

wait
echo ""
echo "All {{NUM_TASKS}} tasks completed."
echo "Done: $(date)"
