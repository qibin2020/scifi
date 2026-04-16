---
Rank: 3
BashTime: -1
GPU: on
NoMemory: on
---

# MNIST 2-GPU

## Todo
Train the same MNIST AlexNet but with DataParallel across 2 GPUs (CUDA_VISIBLE_DEVICES has 2 entries). Save model.pt, train.log, and gpu_log.txt that proves both GPUs were used.

## Expect
- model.pt > 100 KB
- train.log last-100 acc > 0.90
- gpu_log.txt shows 2 distinct GPUs
- `metrics.json` exists with key `accuracy` > 0.90
