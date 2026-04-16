---
Rank: 1
Timeout: 900
BashTime: -1
GPU: local
NoMemory: on
---

# torch CUDA smoke test

## Context

Verify that PyTorch can see and use the local NVIDIA A100 GPU through the
container. Create a small env with `torch`, run a tiny matmul on GPU, write the
torch version + device name + matmul wall time to `torch_gpu.txt`.

## Todo

1. `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.12 -y`
2. `MAMBA_ROOT_PREFIX=./env micromamba run -n work pip install --no-cache-dir torch`
3. `nvidia-smi -L` (host check, should list at least one A100)
4. Write `gpu_check.py`:
   - `import torch, time, json`
   - `assert torch.cuda.is_available(), "CUDA not available"`
   - `dev = torch.device('cuda:0')`
   - Allocate two `2048x2048` random fp32 tensors on `dev`
   - Warm-up matmul, then time 10 matmuls with `torch.cuda.synchronize()` around them
   - Print `torch.__version__`, `torch.cuda.get_device_name(0)`, the per-matmul ms
   - Write `torch_gpu.txt` with three lines: `torch=<ver>`, `device=<name>`, `matmul_ms=<value>`
5. Run: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python gpu_check.py`

## Expect

- `torch_gpu.txt` exists
- File contains `torch=` and `device=` and `matmul_ms=` lines
- Device line includes `A100` or another NVIDIA GPU name (not CPU fallback)
