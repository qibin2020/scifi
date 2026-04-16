---
Rank: 1
Timeout: 1800
BashTime: -1
Skills: NERSC_slurm
NoMemory: on
---

# SLURM hello-world

## Context

Use the `NERSC_slurm_maker` skill to generate a tiny CPU SLURM script that runs
`hostname; date; echo OK`, submit it to the queue with account `m2616`, wait
for it to finish, and capture the stdout into `slurm_out.txt`.

## Todo

1. Use the `NERSC_slurm_maker` skill to generate a CPU `shared` script:
   - Account: `m2616`
   - Constraint: `cpu`
   - 1 task, 4 CPUs
   - Wall time: 5 minutes
   - Command: `hostname; date; echo OK`
   - Output path: `slurm_out.txt`
2. `sbatch <script>.sh` and capture the job ID
3. Poll `squeue -j <id>` until the job leaves the queue
4. Verify `slurm_out.txt` exists and contains `OK`

## Expect

- A `.sh` SLURM script exists in the task directory
- `slurm_out.txt` exists and contains the literal string `OK`
- A `slurm_jobid.txt` file exists with the numeric job ID
