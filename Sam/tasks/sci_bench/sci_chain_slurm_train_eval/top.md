---
Rank: 3
ForceModel: gemma4
SlurmTool: on
BashTime: -1
NoMemory: on
Binds: /pscratch/sd/b/binus/scif_gpu_out:/srv/out:rw
---

# SLURM train + eval chain

## Context

Train a tiny net on MNIST on a Perlmutter GPU node via SLURM, then run a second
GPU job that loads `model.pt` and evaluates it, producing `eval.json` with the
test accuracy. There is no `sbatch` here — use the `slurm_submit` /
`slurm_status` tools. The command runs directly on the GPU node, where
`module load pytorch` provides torch + CUDA.

IMPORTANT — two different paths for the SAME directory:
- Inside THIS shell (your bash), the output dir is `/srv/out`. Write the script
  here and read outputs back here to verify.
- On the GPU compute node (where the submitted commands run), that same
  directory is `/pscratch/sd/b/binus/scif_gpu_out`. The `slurm_submit` commands
  MUST use that real path, never `/srv/out`.

## Todo

1. Write the script (it has a `train` mode and an `eval` mode) to
   `/srv/out/te.py` with bash (a single heredoc). End with `echo WROTE_SCRIPT`:
   ```bash
   cat > /srv/out/te.py <<'PY'
   import os, sys, json, time, torch, torch.nn as nn, torch.nn.functional as F
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
   def data(train,bs):
       tf=transforms.Compose([transforms.ToTensor(),transforms.Normalize((0.1307,),(0.3081,))])
       return DataLoader(datasets.MNIST(OUT+"/data",train=train,download=True,transform=tf),batch_size=bs,shuffle=train,num_workers=2)
   dev="cuda" if torch.cuda.is_available() else "cpu"
   mode=sys.argv[1] if len(sys.argv)>1 else "train"
   if mode=="train":
       log=open(OUT+"/train.log","w")
       def p(m): print(m); log.write(m+"\n"); log.flush()
       p("torch=%s cuda=%s device=%s"%(torch.__version__,torch.cuda.is_available(),dev))
       if dev!="cuda": p("ERROR no cuda"); sys.exit(2)
       p("gpu=%s"%torch.cuda.get_device_name(0))
       net=Net().to(dev); opt=torch.optim.Adam(net.parameters(),lr=1e-3); net.train()
       t0=time.time(); step=0; dl=data(True,64)
       while step<700:
           for x,y in dl:
               if step>=700: break
               x,y=x.to(dev),y.to(dev); opt.zero_grad()
               loss=F.cross_entropy(net(x),y); loss.backward(); opt.step()
               if step%100==0: p("step %d loss %.4f"%(step,loss.item()))
               step+=1
       p("trained 700 batches in %.1fs"%(time.time()-t0))
       torch.save(net.state_dict(),OUT+"/model.pt")
       p("saved model.pt %d bytes"%os.path.getsize(OUT+"/model.pt"))
       log.close(); print("TRAIN_OK")
   else:
       net=Net().to(dev); net.load_state_dict(torch.load(OUT+"/model.pt",map_location=dev)); net.eval()
       c=t=0; dl=data(False,256)
       with torch.no_grad():
           for x,y in dl:
               x,y=x.to(dev),y.to(dev); c+=(net(x).argmax(1)==y).sum().item(); t+=y.numel()
       acc=c/t
       json.dump({"accuracy":acc,"correct":c,"total":t},open(OUT+"/eval.json","w"))
       print("accuracy %.4f"%acc); print("EVAL_OK")
   PY
   echo WROTE_SCRIPT
   ```

2. Submit the GPU TRAINING job (note the REAL node path in the command):
   - `slurm_submit` with command
     `module load pytorch >/pscratch/sd/b/binus/scif_gpu_out/modload.log 2>&1; cd /pscratch/sd/b/binus/scif_gpu_out && python te.py train >/pscratch/sd/b/binus/scif_gpu_out/train_run.log 2>&1 && echo TRAIN_JOB_DONE`,
     `time_minutes` 30, `cpus` 8, `gpus` 1, `name` "te_train".
   - Remember the returned job id. Poll `slurm_status` with it, running
     `sleep 30` in bash between calls, until it returns `DONE <exit>`.
   - After `DONE 0`, confirm the model from THIS shell with one clean token:
     ```bash
     test $(stat -c%s /srv/out/model.pt) -gt 100000 && echo MODEL_OK || echo MODEL_MISSING
     ```

3. Submit the GPU EVAL job (only after `MODEL_OK`):
   - `slurm_submit` with command
     `module load pytorch >/pscratch/sd/b/binus/scif_gpu_out/modload2.log 2>&1; cd /pscratch/sd/b/binus/scif_gpu_out && python te.py eval >/pscratch/sd/b/binus/scif_gpu_out/eval_run.log 2>&1 && echo EVAL_JOB_DONE`,
     `time_minutes` 20, `cpus` 8, `gpus` 1, `name` "te_eval".
   - Remember this second job id. Poll `slurm_status` with it (with `sleep 30`
     between calls) until `DONE <exit>`.

4. After the eval job is `DONE 0`, verify accuracy from THIS shell (one clean
   token):
   ```bash
   python3 -c "import json;a=json.load(open('/srv/out/eval.json'))['accuracy'];print('CHAIN_OK' if a>0.90 else 'CHAIN_LOW %.4f'%a)"
   ```
   When you see `CHAIN_OK`, call `done` (include both job ids and the accuracy).
   If either job `FAILED`, or the check prints `CHAIN_LOW`, report it.

## Expect

- Both SLURM jobs returned `DONE 0`.
- `/srv/out/model.pt` exists and is larger than 100 KB.
- `/srv/out/eval.json` exists with `accuracy` > 0.90.
