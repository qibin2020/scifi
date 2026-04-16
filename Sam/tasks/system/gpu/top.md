---
Rank: 0
BashTime: -1
GPU: local
NoMemory: on
---

# GPU Smoke Test

## Context
Verify that GPU passthrough works. The container should see an NVIDIA GPU
via CUDA_VISIBLE_DEVICES.

## Todo
1. Run `nvidia-smi -L` and write the output to `gpu_info.txt`
2. Write a one-line Python script that prints whether CUDA is available:
   `python3 -c "import subprocess; print(subprocess.check_output(['nvidia-smi','-L']).decode()[:80])"`
   Write the output to `gpu_check.txt`

## Expect
- `gpu_info.txt` exists and contains "GPU" or "NVIDIA"
- `gpu_check.txt` exists and is non-empty
