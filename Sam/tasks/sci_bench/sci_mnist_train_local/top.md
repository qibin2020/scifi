---
Rank: 3
BashTime: -1
GPU: local
NoMemory: on
---

# MNIST AlexNet 1 GPU

## Todo
Train a small AlexNet-style CNN on MNIST for ~500 batches on cuda:0. Aim for >90% train acc on the last 100 batches. Save model.pt and train.log.

## Expect
- model.pt exists > 100 KB
- train.log shows last-100-batch acc > 0.90
- gpu_log.txt exists
- `metrics.json` exists with key `accuracy` > 0.90
