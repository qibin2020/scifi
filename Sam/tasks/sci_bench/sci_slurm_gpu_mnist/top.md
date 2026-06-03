---
Rank: 3
ForceModel: gemma4
SlurmTool: on
BashTime: -1
NoMemory: on
Binds: /pscratch/sd/b/binus/scif_gpu_out:/srv/out:rw
---

# SLURM MNIST GPU

## Context

Train a tiny net on MNIST on a Perlmutter GPU node via SLURM, then verify the
outputs. There is no `sbatch` here — use the `slurm_submit` / `slurm_status`
tools. The command runs directly on the GPU node, where `module load pytorch`
provides torch + CUDA.

IMPORTANT — two different paths for the SAME directory:
- Inside THIS shell (your bash), the output dir is `/srv/out`. Write the script
  here and read outputs back here to verify.
- On the GPU compute node (where the submitted command runs), that same
  directory is `/pscratch/sd/b/binus/scif_gpu_out`. The `slurm_submit` command
  MUST use that real path, never `/srv/out`.

## Todo

1. Write the training script to `/srv/out/train.py` with bash (a single
   heredoc). It uses the real node path internally. End with `echo WROTE_TRAIN`:
   ```bash
   cat > /srv/out/train.py <<'PY'
   import os, sys, time, torch, torch.nn as nn, torch.nn.functional as F
   from torch.utils.data import DataLoader
   from torchvision import datasets, transforms
   OUT="/pscratch/sd/b/binus/scif_gpu_out"
   class Net(nn.Module):
       def __init__(s):
           super().__init__()
           s.c1=nn.Conv2d(1,16,3,padding=1); s.c2=nn.Conv2d(16,32,3,padding=1)
           s.f1=nn.Linear(32*7*7,128); s.f2=nn.Linear(128,10)
       def forward(s,x):
           x=F.max_pool2d(F.relu(s.c1(x)),2); x=F.max_pool2d(F.relu(s.c2(x)),2)
           x=x.flatten(1); x=F.relu(s.f1(x)); return s.f2(x)
   log=open(OUT+"/train.log","w")
   def p(m): print(m); log.write(m+"\n"); log.flush()
   dev="cuda" if torch.cuda.is_available() else "cpu"
   p("torch=%s cuda=%s device=%s"%(torch.__version__,torch.cuda.is_available(),dev))
   if dev!="cuda": p("ERROR no cuda"); sys.exit(2)
   p("gpu=%s"%torch.cuda.get_device_name(0))
   tf=transforms.Compose([transforms.ToTensor(),transforms.Normalize((0.1307,),(0.3081,))])
   dl=DataLoader(datasets.MNIST(OUT+"/data",train=True,download=True,transform=tf),batch_size=64,shuffle=True,num_workers=2)
   net=Net().to(dev); opt=torch.optim.Adam(net.parameters(),lr=1e-3); net.train()
   t0=time.time(); step=0
   while step<500:
       for x,y in dl:
           if step>=500: break
           x,y=x.to(dev),y.to(dev); opt.zero_grad()
           loss=F.cross_entropy(net(x),y); loss.backward(); opt.step()
           if step%100==0: p("step %d loss %.4f"%(step,loss.item()))
           step+=1
   p("trained 500 batches in %.1fs"%(time.time()-t0))
   torch.save(net.state_dict(),OUT+"/model.pt")
   p("saved model.pt %d bytes"%os.path.getsize(OUT+"/model.pt"))
   log.close(); print("TRAIN_OK")
   PY
   echo WROTE_TRAIN
   ```

2. Submit the GPU training job (note the REAL node path in the command):
   - `slurm_submit` with command
     `module load pytorch >/pscratch/sd/b/binus/scif_gpu_out/modload.log 2>&1; cd /pscratch/sd/b/binus/scif_gpu_out && python train.py >/pscratch/sd/b/binus/scif_gpu_out/run.log 2>&1 && echo JOB_DONE`,
     `time_minutes` 30, `cpus` 8, `gpus` 1, `name` "gpu_mnist".
   - Remember the returned job id.

3. Poll `slurm_status` with that job id, running `sleep 30` in bash between
   calls, until it returns `DONE <exit>` (or `FAILED`).

4. After `DONE 0`, verify the outputs from THIS shell (read them at `/srv/out`,
   one clean token):
   ```bash
   test -s /srv/out/model.pt && test $(stat -c%s /srv/out/model.pt) -gt 100000 && test -s /srv/out/train.log && grep -q cuda /srv/out/train.log && echo GPU_MNIST_OK || echo GPU_MNIST_MISSING
   ```
   When you see `GPU_MNIST_OK`, call `done` (include the job id). If the job
   `FAILED` or the check prints `GPU_MNIST_MISSING`, report it.

## Expect

- `slurm_status` returned `DONE 0` for the submitted job.
- `/srv/out/model.pt` exists and is larger than 100 KB.
- `/srv/out/train.log` exists and shows CUDA was used.
