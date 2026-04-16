---
Rank: 1
BashTime: -1
GPU: local
NoMemory: on
---

# torch GPU smoke

## Todo
Install torch. Confirm CUDA. Run a tiny matmul on the GPU. Write `gpu_check.py` and `torch_gpu.txt` with lines: `torch=<version>`, `device=<name>`, `matmul_ms=<time>`.

## Expect
- torch_gpu.txt exists with torch=, device=, matmul_ms= lines
- device line shows an A100 (or another NVIDIA GPU)
