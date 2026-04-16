---
Rank: 3
Timeout: 1800
BashTime: -1
GPU: on
NoMemory: on
---

# Train MNIST AlexNet on 2 local GPUs

## Context

Same task as `sci_mnist_train_local`, but use **two** local GPUs via either
`torch.nn.DataParallel` or `torch.nn.parallel.DistributedDataParallel`
(launched with `torchrun --nproc_per_node=2`). The runner pins the task to two
specific GPUs via `CUDA_VISIBLE_DEVICES=<a>,<b>` so inside the container both
appear as `cuda:0` and `cuda:1`.

## Todo

1. Create env (same as the 1-GPU task): `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.12 -y && MAMBA_ROOT_PREFIX=./env micromamba run -n work pip install --no-cache-dir torch torchvision`
2. Verify that BOTH GPUs are visible: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python -c "import torch; print(torch.cuda.device_count())"` should print `2`.
3. Write `train_dp.py`:
   - Build the same small AlexNet-style CNN as `sci_mnist_train_local`
   - Wrap it with `torch.nn.DataParallel(model, device_ids=[0, 1])`
   - Train for ~500 batches on MNIST with batch size 128 (twice the 1-GPU case so each GPU sees 64)
   - Save `model.pt`, write `train.log`, capture `gpu_log.txt` showing **both** GPUs in use
4. Run: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python train_dp.py 2>&1 | tee train.log`
5. While training, capture `nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv > gpu_log.txt` (background loop is fine)

## Expect

- `model.pt` exists, > 100 KB
- `metrics.json` exists with key `accuracy` > 0.90
- `train.log` shows last-100-batch acc > 0.90
- `gpu_log.txt` lists at least 2 distinct GPU UUIDs OR at least 2 nvidia-smi snapshots that each show a python process on a different GPU
