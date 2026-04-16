---
Rank: 4
Timeout: 2400
BashTime: -1
GPU: local
NoMemory: on
---

# Full MNIST pipeline (env -> train -> evaluate -> report)

## Context

End-to-end chained task. Build the env, train a small AlexNet on MNIST
locally on 1 GPU, evaluate on the test set, produce a confusion matrix plot,
and write a one-paragraph report linking everything together.

## Todo

1. Create a torch + torchvision env: `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.12 -y && MAMBA_ROOT_PREFIX=./env micromamba run -n work pip install --no-cache-dir torch torchvision matplotlib`
2. Write `train.py`: small AlexNet, train ~500 batches, save `model.pt` and `train.log`
3. Write `evaluate.py`: load `model.pt`, run on the MNIST test set, compute accuracy and confusion matrix, save `confusion.png` (matplotlib imshow with class labels) and `metrics.json` with `accuracy`
4. Run training, then evaluation
5. Write `report.md` (one paragraph) summarizing: command used, training step count, final test accuracy, link to confusion.png

## Expect

- `model.pt` > 100 KB
- `metrics.json` with `accuracy` > 0.90
- `confusion.png` exists, > 5 KB
- `report.md` exists, mentions `accuracy` and `confusion.png`
