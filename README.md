# SciF — Autonomous Agent System

Define tasks in markdown. Agents execute them in isolated containers. Independent reviewers verify the results.

## Talk to It

```bash
SciFi "run the hello test"
SciFi "create a task that trains MNIST on GPU"
SciFi "what tasks have I run?"
SciFi -- "run task_xxx"         # skip confirmation
SciFi help
```

`SciFi` is the natural language interface — just say what you want. For direct commands: `SciF RUN`, `SciF MAKE`, `SciF ASK`, `SciF STATUS`.

## Setup

```bash
vi .secret.sh                   # set ANTHROPIC_API_KEY and BEDROCK_API_KEY
source ENV.sh
SciF BOOTSTRAP                  # first time only
SciFi "start and run test_hello"
```

Optional: share SSH keys with agents for private repo access:
```bash
cp -r ~/.ssh F/home/
```

## Task Format

Create `Sam/tasks/<name>/top.md`:

```markdown
# My Task
Rank: 1

## Context
What the agent needs to know.

## Todo
1. Step one
2. Step two

## Expect
- output.txt exists with "hello"
- tests pass
```

All behavior is controlled through metadata in `top.md` — you never edit driver scripts.

| Field | Default | What it does |
|-------|---------|--------------|
| `Rank: N` | auto | Difficulty. 0 = trivial, 1 = typical, 2 = reasoning, 3+ = hard |
| `ForceModel: name` | rank-based | Pin worker model (e.g. `llama4-scout`) |
| `ControlModel: name` | highest | Pin review model (e.g. `qwen3-coder`) |
| `Thinking: N` | off | Force thinking mode with N token budget |
| `BashTime: N` | 300 | Max seconds per bash call. `-1` = unlimited |
| `Skills: a, b` | auto | Skills to inject |
| `NoMemory: on\|off` | `off` | Clean-room run: don't read global memory, don't write global history |
| `CommonHome: ro\|rw\|disable` | `ro` | Shared home mount (`F/home/` → `/home`) |
| `CommonStorage: rw\|ro\|disable` | `rw` | Shared storage mount (`F/mnt/` → `/mnt`) |

## Agent Environment

Agents run in isolated containers. What they see:

| Path | Persistent | Purpose |
|------|-----------|---------|
| `./` (task dir) | Yes | All outputs and per-task environments go here |
| `/mnt/` | Yes | Shared assets and reusable environments across tasks |
| `/home/` | Read-only* | SSH keys, git config |
| Everything else | No | RAM overlay, discarded on exit |

\* With `CommonHome: rw`, writes to `/home` persist. Default `ro` discards writes.

**Python environments**: the container ships with `micromamba` + `pip`. Agents create environments under `./` (per-task, throwaway) or `/mnt/` (shared, reusable across tasks). The base environment is read-only and reserved for the driver — installs into it are silently discarded on exit.

```bash
# Per-task env (under ./)
MAMBA_ROOT_PREFIX=./mamba_env micromamba create -n work python=3.12 -y
micromamba run -r ./mamba_env -n work pip install <package>

# Shared env (under /mnt, reusable across tasks)
MAMBA_ROOT_PREFIX=/mnt/envs micromamba create -n shared python=3.12 -y
```

## Learn More

Chat with `SciFi` to explore the system, or read:
- `F/F.design.md` — Architecture, concurrency, recovery paths
- `F/F.usage.md` — Commands, skills, evolution
- `Pam/gateway.rank.yaml` — Model rankings
