#!/bin/bash
# Auto-generated SLURM wrapper for: {{USER_SCRIPT}}
# Pattern: N nodes × 4 GPUs — regular QOS (all GPUs visible to all tasks)
# Use for: frameworks self-managing GPU assignment across multiple nodes
# Generated: {{DATE}}

#SBATCH -A {{ACCOUNT}}
#SBATCH -C gpu
#SBATCH -q regular
#SBATCH -t {{WALLTIME}}            # VERIFY: adjust to your estimated runtime
#SBATCH -N {{NUM_NODES}}           # VERIFY: number of nodes
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
echo "Nodes:     $SLURM_NODELIST"
echo "GPUs:      $(({{NUM_NODES}} * 4)) (4 per node, all visible)"
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

# --- Multi-node DDP setup ---
export MASTER_ADDR=$(scontrol show hostnames $SLURM_JOB_NODELIST | head -n 1)
export MASTER_PORT=29500
echo "MASTER_ADDR: $MASTER_ADDR"
echo "MASTER_PORT: $MASTER_PORT"
echo ""

# =============================================================================
# MAIN COMMAND
# =============================================================================
srun {{LAUNCH_CMD}}

echo ""
echo "Done: $(date)"
