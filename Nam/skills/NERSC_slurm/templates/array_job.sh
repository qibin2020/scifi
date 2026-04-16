#!/bin/bash
# Auto-generated SLURM wrapper for: {{USER_SCRIPT}}
# Pattern: Array job — each task runs independently with its own allocation
# Use for: hyperparameter sweeps, config sweeps, cross-validation folds
# Generated: {{DATE}}

#SBATCH -A {{ACCOUNT}}
#SBATCH -C {{CONSTRAINT}}
#SBATCH -q shared
#SBATCH -t {{WALLTIME}}            # VERIFY: runtime PER array task
#SBATCH --array={{ARRAY_SPEC}}     # VERIFY: 0-(N-1)%MAX_CONCURRENT
{{GPU_DIRECTIVES}}
#SBATCH --job-name={{JOBNAME}}     # VERIFY: descriptive job name
#SBATCH --output=slurm_%x_%A_%a.out
#SBATCH --error=slurm_%x_%A_%a.err

# --- Job Info ---
echo "=== SLURM Array Task ==="
echo "Array Job:  ${SLURM_ARRAY_JOB_ID:-$SLURM_JOB_ID}"
echo "Task Index: $SLURM_ARRAY_TASK_ID"
echo "Node:       $SLURM_NODELIST"
echo "Start:      $(date)"
echo "Script:     {{USER_SCRIPT}}"
echo ""

# --- Working Directory ---
WORKDIR={{WORKDIR}}
cd "$WORKDIR" || { echo "ERROR: cannot cd to $WORKDIR"; exit 1; }

# --- Environment ---
source /pscratch/sd/b/binus/Playground/slurm_system/env_setup.sh



{{GPU_CHECK}}
{{CPU_BIND}}

# =============================================================================
# CONFIG SELECTION — VERIFY: customize for your sweep
# =============================================================================
{{CONFIG_BLOCK}}

# =============================================================================
# MAIN COMMAND
# =============================================================================
srun {{LAUNCH_CMD}}

echo ""
echo "Done: $(date)"
