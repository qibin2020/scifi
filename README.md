# SciFi — Autonomous Agent System for SCIentific Workloads with an LLM-Native Interface

[![arXiv](https://img.shields.io/badge/arXiv-2604.13180-b31b1b.svg)](https://arxiv.org/abs/2604.13180)

`SciFi: Process the dataset, run this paper method, generate the plots, and make sure you reproduce all the paper results exactly. Suggest what we can optimize and submit SLURM jobs to test—I’ll decide what to try next.`

`SciFi: Read the board manual, understand the interface, find the data on disk, write the RTL to implement the algorithm, and make sure all tests 100% pass. I’ll need it ready for the experiment tomorrow.`

## Talk to It

```bash
SciFi "run the hello test"
SciFi "create a task that trains MNIST on GPU"
SciFi "what tasks have I run?"
SciFi -- "run task_xxx"         # skip confirmation
SciFi help                      # actually you don't need "" if shell is happy
```

`SciFi` is the natural language interface — just say what you want. For direct commands: `SciF RUN`, `SciF MAKE`, `SciF ASK`, `SciF STATUS`.

## Requirements

- **Linux** (tested on RHEL 9 / Debian 13; no macOS or Windows support)
- **[Apptainer](https://apptainer.org/)** (container runtime; `ENV.sh` auto-detects via `which apptainer`)
- **At least one LLM API key** (e.g. Ollama Cloud; local models are also supported, see Models and Credentials sections)

## How It Works

Each task runs as a closed loop: **Prescan → Agent Loop → Independent Review**.

1. **Prescan** — a control model reads the task, assigns a difficulty rank, selects skills, and plans subtasks
2. **Agent Loop** — a worker model executes the Todo with tools (bash, file I/O, web fetch, memory, sub-agents), iterating until it claims `done` or exhausts its budget
3. **Independent Review** — a different model verifies every Expect item using its own tool calls. If verification fails, the task retries with feedback. If the reviewer itself fails, a cascade of fallback reviewers takes over

Every `done` claim is independently verified — the worker's word is never trusted. This makes the system robust against hallucination and fabrication.

## Setup

Configure
```bash
cp .secret.sh.template .secret.sh # all user credentials. Edit your API keys here!
cat .secret.sh                    # add at least one API key in the file or use local model (see later)
chmod 600 .secret.sh              # required — ENV.sh enforces this
cat ENV.sh                        # set the apptainer path in the file if default doesn't work
echo $APPTAINER                   # check apptainer works
```
Bootstrap
```bash
source ENV.sh                     # central config
SciF BOOTSTRAP                    # first time only
SciFi "start and run test_hello"
```

Optional: share SSH keys with agents for private repo access (or create new one for agents):
```bash
# cp -r ~/.ssh F/home/
```

## Task Format

Create `Sam/tasks/<name>/top.md`:

```markdown
---
Rank: 1
Skills: temp_env
---

# My Task

## Context
What the agent needs to know.

## Todo
1. Step one
2. Step two

## Expect
- output.txt exists with "hello"
- tests pass
```

`top.md` is the entry point. Tasks can include multiple `.md` files (subtasks), all following the same format. Behavior is controlled through metadata in each `.md` file — you never edit driver scripts.

The task description must follow exactly this format (for safety reasons). The task starts with metadata and then follows with a title, Context, Todo, and Expect — three fixed-name sections, written in natural language. The format inside each section is free-form and you can use sub-headings or listing if it helps readability (make no difference to agents).

YAML frontmatter block (`---` delimited) at the top of each task `.md` file is the metadata, which is used to control and configure the workflow in a deterministic way (key-value pairs). These fields trigger pre-defined functions and are visible to the agent. To set metadata invisible to the agent (e.g. trigger a special function without the agent knowing), prefix the field name with an underscore, such as `_DontLetAgentKnow: quiz!`.
Common fields and usually we leave them default:

| Field | Default | What it does |
|-------|---------|--------------|
| `Rank: N` | auto | Difficulty. 0 = trivial, 1 = typical, 2 = reasoning, 3+ = hard |
| `ForceModel: name` | rank-based | Pin worker model (e.g. `llama4-scout`) |
| `ControlModel: name` | highest | Pin review model (e.g. `qwen3-coder`) |
| `Thinking: N` | off | Force thinking mode with N token budget |
| `BashTime: N` | 600 | Max seconds per bash call. `-1` = unlimited |
| `Skills: a, b` | auto | Skills to inject |
| `NoMemory: on\|off` | `off` | Clean-room run: don't read global memory, don't write global history |
| `CommonHome: rw\|ro\|disable` | `rw` | Shared home mount (`F/home/` → `/home`) |
| `CommonStorage: rw\|ro\|disable` | `rw` | Shared storage mount (`F/mnt/` → `/mnt`) |
| `GPU: no\|local\|slurm\|on` | `no` | GPU policy |
| `Slurm: off\|on` | `off` | SLURM submission access |

## Agent Environment

Agents run in isolated Apptainer containers. Three Python environment variants are available, controlled by the `Skills` field in task metadata:

| Variant | Skill | Location | Persistent | Use case |
|---------|-------|----------|-----------|----------|
| **common** | `common_env` | `/mnt/` (host under `F/mnt/`) | Yes | Default. Shared across tasks, reused if exists |
| **local** | `local_env` | `./` (task dir under `F/tasks/`) | Yes | Per-task, isolated from other tasks |
| **temp** | `temp_env` | RAM overlay | No | Throwaway, discarded on exit |

If no env skill is declared, `local_env` is auto-inferred. The `common_env` skill handles shared environment discovery and reuse — agents reuse an existing environment at `/mnt/` or create a new one, but never modify an existing one.

## Output and State

Each task run creates `F/tasks/<name>_<timestamp>/`. Check after a run:

| File | What it is |
|------|-----------|
| `F/tasks/<run>/top.md` | Task definition (copied from source) |
| `F/tasks/<run>/*.md` | Subtask files (if any) |
| `F/tasks/<run>/` (other files) | Agent outputs — code, data, logs |
| `F/tasks/<run>/.suggestion.md` | Final review: conclusion (DONE/NOT DONE) + suggestions |
| `F/tasks/<run>/.history_index.md` | Execution summary |
| `F/tasks/<run>/.memory.md` | Per-task memory (agent notes) |

Global memory and history live in `F/run/` (persistent across runs):

| File | What it is |
|------|-----------|
| `F/run/.global_memory.md` | Cross-task knowledge (evolution writes) |
| `F/run/.global_history.md` | All task run records (append-only) |
| `F/run/.global_suggestion.md` | System improvement suggestions |

Shared persistent directories (accessible to all tasks via container mounts):

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `F/mnt/` | `/mnt/` | Shared storage — reusable environments, datasets, assets |
| `F/home/` | `/home/` | Shared home — SSH keys, git config |

Audit logs in `Cam/*.jsonl` — per-session, recommended to keep as they are useful for post-training. `SciF MAINTAIN` compresses old logs.

## Learn More

Chat with `SciFi` to explore the system (e.g. `task maker` and `skill maker`), or read:
- `F/F.design.md` — Architecture, concurrency, recovery paths
- `F/F.usage.md` — Commands, skills, evolution
- `Pam/gateway.rank.yaml` — Model rankings and budgets
- `ENV.sh` — Central configuration and hard-coded things


### Configuration

`ENV.sh` is the central configuration file — every script and entry point sources it first. It sets all paths, driver limits, and model group names. Key sections:

| Variable | Purpose |
|----------|---------|
| `APPTAINER`, `SIF`, `OVERLAY` | Container runtime and image paths |
| `GATEWAY_PORT` | Auto-derived from UID, no manual setup needed |
| `FALLBACK_HIGHEST`, `FALLBACK_WORKING` | Fallback model groups when rank config is unavailable |
| `SCIFI_MODEL` | Model group for the SciFi natural language interface |
| `MAX_ITERATIONS`, `MAX_DEPTH`, `MAX_RETRIES` | Agent loop limits |
| `WALL_LIMIT_PER_RANK`, `ITER_LIMIT_PER_RANK` | Per-rank time and iteration budgets (comma-separated, rank 0 to 5) |
| `TOTAL_WALL_PER_RANK` | Hard wall-clock cap per rank |
| `MAX_EVOLVE_ITER` | Evolution loop limit |


## Important Notice

### Models, Budgets and Reproduction

By default, multiple models are configured at different ranks and load-balanced across providers. The system supports: Anthropic, AWS Bedrock, Ollama Cloud, OpenAI, Google Gemini, Mistral, DeepSeek, OpenRouter, Groq, Together AI, Fireworks AI, and Azure OpenAI. Set at least one API key in `.secret.sh`. 
Locally deployed models and other API services are also supported through [LiteLLM](https://docs.litellm.ai/). 
Refer to `Pam/gateway.model.yaml` for configuration.

**Budget is per run, not cumulative** — it caps the number of API calls per task run, not across runs. Iterative agent loops are token-heavy, so monitor your usage. Consider starting with subscription-based APIs (not pay-per-use) and cost-effective models. Refer to [LiteLLM documentation](https://docs.litellm.ai/docs/simple_proxy) for detailed budget control.

To reproduce the paper configuration, set up an Ollama Cloud API key and keep only `Gemma4` active (comment out other models) in `Pam/gateway.rank.yaml`.

### Credentials

All secrets live in `.secret.sh` (sourced by `ENV.sh`, never committed). Copy the template and fill in what you need. The template includes keys for common providers: Anthropic, AWS Bedrock, Ollama Cloud, OpenAI, Google Gemini, Mistral, DeepSeek, OpenRouter, Groq, Together AI, Fireworks AI, and Azure OpenAI. Uncomment and set the ones you use — unused keys can stay commented out.

**SSH keys for agents**: agents run in isolated containers and cannot access your host `~/.ssh` by default. To give them access (e.g. for cloning private repos), copy your keys into the shared home directory or prepare your own agent-only keys. It is mounted at `/home/` inside the container when `CommonHome` is enabled (default `rw`). Keep `F/home/.ssh` out of version control — it is already in `.gitignore`.

Treat these Credentials carefully! They can in principle read by the agents/LLM/cloud provider

