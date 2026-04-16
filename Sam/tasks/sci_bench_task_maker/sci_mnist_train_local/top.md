---
Rank: 3
Timeout: 1800
BashTime: -1
GPU: local
NoMemory: on
---

# Train a small AlexNet on MNIST (1 GPU)

## Context

Train a small AlexNet-style CNN on MNIST for one short epoch on a single local
A100 GPU. The training is intentionally short — the goal is to validate the
GPU + torch + MNIST + training-loop pipeline, not to converge to SOTA. Aim for
> 90 % training accuracy on the last 100 batches; this is achievable in ~500
batches at batch size 64.

## Todo

1. Create env: `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.12 -y`
2. Install: `MAMBA_ROOT_PREFIX=./env micromamba run -n work pip install --no-cache-dir torch torchvision`
3. Write `train.py`:
   - Use `torchvision.datasets.MNIST(root='./mnist_data', train=True, download=True, transform=ToTensor + Normalize((0.1307,), (0.3081,)))`
   - Build a small AlexNet-style CNN sized for 28x28 grayscale (3 conv blocks + 2 FC). Output 10 classes.
   - Train on `cuda:0` with Adam, batch size 64, for at most 500 batches (you can use `max_steps`-style break or `itertools.islice`)
   - Print training loss + running accuracy every 50 batches
   - After training, compute the running accuracy of the last 100 batches and print it
   - Save the model to `model.pt` via `torch.save(model.state_dict(), 'model.pt')`
   - Append all the printed lines to `train.log`
4. Run: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python train.py 2>&1 | tee train.log`
5. Capture nvidia-smi state during training to `gpu_log.txt` (a snapshot of compute-apps is enough)

## Expect

- `model.pt` exists, > 100 KB
- `metrics.json` exists with key `accuracy` > 0.90
- `train.log` exists, contains "Epoch" / "loss" / "accuracy" markers
- `train.log` shows last-100-batch accuracy > 0.90
- `gpu_log.txt` exists with at least one nvidia-smi snapshot
