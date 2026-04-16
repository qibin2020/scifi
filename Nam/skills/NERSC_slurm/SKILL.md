---
name: NERSC_slurm
description: Analyze a locally-tested script, generate a correct NERSC Perlmutter SLURM wrapper, submit via sbatch, and confirm the job is queued
---

Analyze a user's locally-tested script, generate the correct SLURM wrapper,
submit it, and confirm the job is PENDING or RUNNING. That's it — no waiting,
no monitoring. Just ensure a clean submission.

## User-provided Configuration (ask if not given)
- **Account**: `-A <account>` — always ask the caller if not provided

## Fixed Configuration
- **Env setup**: `/pscratch/sd/b/binus/Playground/slurm_system/env_setup.sh`
- **Templates**: `templates/` in this skill directory

## Workflow

```
[1] Read & analyze the script
[2] Determine resource requirements (ask only if ambiguous)
[3] Select template & generate wrapper
[4] Show wrapper to caller for confirmation
[5] Submit via sbatch + confirm queued
```

## Step 1: Analyze the Script

Read the script completely. Detect:

**GPU**: `torch.cuda`, `.to("cuda")`, `.cuda()`, `CUDA_VISIBLE_DEVICES`,
`cupy`, `cudf`, `tf.config.list_physical_devices('GPU')`. None → CPU job.

**Parallelism**:
- DDP: `torch.distributed`, `DistributedDataParallel`, `torchrun`, `accelerate`, `deepspeed`
- Multi-node: `MASTER_ADDR`, `WORLD_SIZE`, `--nnodes`
- Array/sweep: `--config`, `--seed`, iterating over params
- MPI: `mpi4py`, `mpirun`
- Parallel tasks: multiple independent runs

**Wall time**: Estimate from epochs, dataset size, batch size, steps.
If insufficient info, use conservative default (4h) and note it.

**Working dir**: Infer from script location. Default: `/pscratch/sd/b/binus/Playground`

## Step 2: Determine Requirements

Present findings:

```
  Account:     (ask if not given)
  GPU:         yes/no (reason)
  GPU count:   N
  Parallelism: single | DDP | array | parallel-tasks | MPI
  Wall time:   HH:MM:SS (reasoning)
  Working dir: /path
  Nodes:       N
```

Only ask if genuinely ambiguous. If caller gave hints, use them directly.

## Step 3: Select Template & Generate Wrapper

### QOS matrix

Default is `regular`. Use `shared` only for ≤2 GPUs or partial CPU node.
`debug` only if caller explicitly requests it.

| Scenario | QOS | Constraint | Template | Key directives |
|----------|-----|-----------|----------|----------------|
| CPU, partial node | shared | cpu | `cpu_shared.sh` | `-n 1 -c <cpus>` |
| CPU, full node | regular | cpu | `cpu_regular.sh` | `-N 1 -c 256` |
| 1 GPU | shared | gpu | `gpu_shared_1gpu.sh` | `-n 1 -c 32 --gpus-per-task=1` |
| 2 GPUs | shared | gpu | `gpu_shared_2gpu.sh` | `--ntasks=2 -c 32 --gpus-per-task=1` |
| 4 GPUs, 1 node | regular | gpu | `gpu_regular_4gpu.sh` | `-N 1 --ntasks-per-node=4 -c 32 --gpus-per-task=1` |
| 4 GPUs, all visible | regular | gpu | `gpu_regular_4gpu_allvis.sh` | `-N 1 --ntasks-per-node=4 -c 32 --gpu-bind=none` |
| N nodes × 4 GPUs | regular | gpu | `gpu_regular_multinode.sh` | `-N <N> --ntasks-per-node=4 -c 32 --gpus-per-task=1` |
| Array (GPU) | shared | gpu | `array_job.sh` | `--array=0-N%M -n 1 -c 32 --gpus-per-task=1` |
| Array (CPU) | shared | cpu | `array_job.sh` | `--array=0-N%M -n 1 -c <cpus>` |
| Parallel GPU tasks | regular | gpu | `parallel_tasks.sh` | `--ntasks-per-node=4`, `srun --exact` |

### Hard rules (NERSC-enforced)
- GPU shared QOS **must** use `-c 32`
- All GPU jobs **must** have `export SLURM_CPU_BIND="cores"`
- Max wall time: `48:00:00`
- Must explicitly request GPUs (`--gpus-per-task` or `--gpus-per-node`)
- All-visible mode needs `--gpu-bind=none`

### Wrapper structure
- Do NOT modify the user's script — the wrapper calls it
- Name: `slurm_<basename>.sh` in the same directory as the user's script
- **Self-contained**: all outputs (SLURM logs, wrapper script) stay in the same
  directory where the submission is launched (i.e. where the user's script lives)
- Use `--output=slurm_%x-%j.out` and `--error=slurm_%x-%j.err` (no `logs/` subdirectory)
- The wrapper `cd`s to the script's directory, so all relative paths resolve there
- No `mkdir -p logs` needed — logs land in `./` next to the script

### Launch command

| Script type | Command |
|-------------|---------|
| Python, single GPU/CPU | `srun python script.py [args]` |
| Python, DDP (torchrun) | `srun torchrun --nproc_per_node=<N> script.py` |
| Python, DDP (accelerate) | `srun accelerate launch script.py` |
| Shell script | `srun bash script.sh` |
| MPI | `srun ./program` |
| Parallel tasks | `srun --exact -n 1 --gpus-per-task 1 ... &` × N + `wait` |

For multi-node DDP, set in wrapper:
```bash
export MASTER_ADDR=$(scontrol show hostnames $SLURM_JOB_NODELIST | head -n 1)
export MASTER_PORT=29500
```

## Step 4: Confirm with Caller

Show the complete wrapper script. Highlight:
- Template and why it was chosen
- Wall time reasoning
- Resource allocation
- Launch command

**Do NOT submit without confirmation.**

## Step 5: Submit & Verify

```bash
cd <directory_of_user_script>
sbatch <wrapper_script>
```

Capture the job ID. Then verify:
```bash
squeue -j <JOBID> -o "%.12i %.10T %.12M %.10l %.8q %.20S %.15R" --noheader
```

If sbatch fails, diagnose and fix (max 2 retries):
- "does not match any supported policy" → wrong constraint/QOS
- "Invalid account" → wrong `-A`
- Wrong working directory → `cd` to the script's directory before `sbatch`

### Final output (REQUIRED — always print this)

The caller may have zero SLURM knowledge. After successful submission, **always**
output a complete, self-contained guide with real data. Use this exact format:

```
============================================================
  SLURM JOB SUBMITTED SUCCESSFULLY
============================================================

  Job ID:      XXXXXX
  Job Name:    <jobname>
  Status:      PENDING | RUNNING
  QOS:         <actual QOS name>
  Resources:   <e.g. 1 GPU, 32 CPUs | 4 GPUs, 1 node | CPU-only, 64 CPUs>
  Wall time:   HH:MM:SS
  Script:      /path/to/slurm_wrapper.sh
  Log (stdout): /path/to/slurm_<jobname>-XXXXXX.out
  Log (stderr): /path/to/slurm_<jobname>-XXXXXX.err

------------------------------------------------------------
  ESTIMATED QUEUE WAIT  (data-driven, measured just now)
------------------------------------------------------------
  Queue snapshot:
    <QOS> pending: NNN jobs | running: NNN jobs
    Idle nodes: NNN | Pending reason: <reason>

  Recent wait times (jobs started in last 6h):
    Median: XX min | P90: XX min | Min: XX min | Max: XX min
    (based on N samples)

  >>> Your estimated wait: ~XX min <<<
  (reason: ...)

------------------------------------------------------------
  HOW TO MONITOR & CONTROL YOUR JOB
------------------------------------------------------------

  Check status:
    squeue -j XXXXXX

  Detailed status (start time estimate, reason for pending):
    squeue -j XXXXXX -o "%.12i %.10T %.12M %.10l %.20S %.15R"

  Watch status live (updates every 30s):
    watch -n 30 squeue -j XXXXXX

  View output log while running:
    tail -f /path/to/slurm_<jobname>-XXXXXX.out

  Cancel the job:
    scancel XXXXXX

  Check all your jobs:
    squeue -u $USER

  After job finishes — check exit status and runtime:
    sacct -j XXXXXX --format=JobID,State,ExitCode,Elapsed,MaxRSS

============================================================
```

### Queue wait estimation procedure (run these commands BEFORE printing output)

**Important**: The actual SLURM QOS names on Perlmutter are NOT the same as the
`-q` flag values in job scripts. The mapping is:

| Script `-q` value | Actual SLURM QOS name | Partition |
|--------------------|----------------------|-----------|
| `shared` + `-C gpu` | `gpu_shared` | `shared_gpu_ss11` |
| `regular` + `-C gpu` | `gpu_regular` | `gpu_ss11` |
| `shared` + `-C cpu` | `shared` | `shared_milan_ss11` |
| `regular` + `-C cpu` | `regular_1` | `regular_milan_ss11` |
| `debug` + `-C gpu` | `gpu_debug` | — |
| `debug` + `-C cpu` | `debug` | — |

Use the **actual QOS name** (left column) for all squeue/sacct queries below.

#### Step A: Queue snapshot
```bash
# Pending and running counts for the target QOS
ACTUAL_QOS=<actual_qos_name>   # e.g. gpu_shared, gpu_regular, shared, regular_1
PD=$(squeue -q $ACTUAL_QOS -t PD --noheader 2>/dev/null | wc -l)
RN=$(squeue -q $ACTUAL_QOS -t R --noheader 2>/dev/null | wc -l)
echo "$ACTUAL_QOS: $PD pending, $RN running"
```

#### Step B: Node availability
```bash
# GPU nodes
sinfo -p gpu_ss11 -t idle -o "%D" --noheader        # idle GPU nodes
sinfo -p gpu_ss11 -t mixed -o "%D" --noheader       # mixed (partially used)
sinfo -p gpu_ss11 -t allocated -o "%D" --noheader   # fully allocated

# CPU nodes
sinfo -p regular_milan_ss11 -t idle -o "%D" --noheader
sinfo -p regular_milan_ss11 -t allocated -o "%D" --noheader
```

#### Step C: Recent wait time statistics (most reliable signal)
Measure actual wait times for jobs that started in the last 6 hours in the same QOS:
```bash
sacct -a -S $(date -d '6 hours ago' '+%Y-%m-%dT%H:%M:%S') -s R,CD \
  --format=JobID,Submit,Start,QOS -P --noheader 2>&1 | \
  grep "$ACTUAL_QOS" | grep -v "\." | \
  while IFS='|' read jobid submit start qos; do
    if [[ "$start" != "Unknown" ]]; then
      s_epoch=$(date -d "$submit" +%s 2>/dev/null)
      t_epoch=$(date -d "$start" +%s 2>/dev/null)
      if [[ -n "$s_epoch" && -n "$t_epoch" && $t_epoch -gt $s_epoch ]]; then
        wait=$((t_epoch - s_epoch))
        # Only include jobs submitted in last 48h to exclude very old backlog
        if (( wait < 172800 )); then echo $wait; fi
      fi
    fi
  done | sort -n | awk '
  { vals[NR] = $1; sum += $1 }
  END {
    if (NR == 0) { print "NO_DATA"; exit }
    printf "samples=%d min=%.0f median=%.0f p90=%.0f max=%.0f avg=%.0f\n", \
      NR, vals[1]/60, vals[int(NR/2)+1]/60, vals[int(NR*0.9)+1]/60, vals[NR]/60, (sum/NR)/60
  }'
```

#### Step D: Pending reason for the submitted job
```bash
squeue -j <JOBID> -o "%r" --noheader
# Common reasons:
#   Priority    — waiting for higher-priority jobs to clear
#   Resources   — waiting for nodes to free up
#   QOSMaxJobsPerUserLimit — user hit QOS job limit
#   Dependency  — waiting on another job
```

#### Step E: Fairshare check (optional, for context)
```bash
sshare -A <account> -u <user> --noheader -o "Account,User,FairShare"
# FairShare > 0.5 = good priority, < 0.1 = low priority (used a lot recently)
```

#### Estimation heuristic (combine Steps A-E)

1. If **idle nodes > 0** AND **pending < 50**: estimate **5–15 min** (backfill likely)
2. If **pending < 200** AND **median recent wait < 60 min**: estimate **median × 1.2**
3. If **pending > 500**: estimate **P90 recent wait** as likely wait
4. If **no recent data**: fall back to these rough baselines:
   - `gpu_shared`: 10–60 min (light), 1–4 hours (busy)
   - `gpu_regular` (1 node): 30 min–6 hours
   - `gpu_regular` (multi-node): 2–12+ hours
   - `shared` CPU: 5–30 min
   - `regular_1` CPU: 10–60 min
5. If **fairshare < 0.1**: add 50% to estimate (low priority)
6. Short wall time jobs (<1h) get backfilled faster — reduce estimate by 30%

Always state the estimate is approximate and depends on cluster load.

Return the **job ID** as the final value so the caller can use it downstream.
