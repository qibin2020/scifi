# SciF System — Usage Guide

## How it works

```
You (natural language)  →  SciFi  →  SciF  →  module .sh  →  .py (in container)
                            │          │
                            │          └─ deterministic bash dispatcher
                            └─ LLM-driven intent → SciF command
```

- **SciFi**: say what you want, it figures out the command
- **SciF**: run a specific command directly
- All heavy work runs inside Apptainer containers (isolated, reproducible)

---

## Quick Start

```bash
# First time — set API keys in .secret.sh then bootstrap
#   1. cp .secret.sh.template .secret.sh && vi .secret.sh
#   2. source ENV.sh
#   3. Run:
SciFi bootstrap             # or: SciF BOOTSTRAP

# Daily use
SciFi start                 # or: SciF START
SciFi run test_hello        # or: SciF RUN test_hello
SciFi stop                  # or: SciF END
```

---

## SciFi — natural language entry point

```bash
SciFi <what you want>          # interactive (waits for feedback after)
SciFi -- <what you want>       # batch (process and exit)
```

**Examples:**
```bash
SciFi run test_hello                    # runs the task, shows conclusion
SciFi I want to train MNIST on GPU      # starts task maker with your description
SciFi what is the rank system?          # answers from documentation
SciFi reset the system                  # suggests command, you run manually
SciFi apptainer not found               # pre-bootstrap help (no LLM needed)
```

**Three routes:**
1. **Early stop** — rule-based (apptainer/secret checks, auto-bootstrap). No LLM.
2. **SciF route** — LLM picks a command, SciFi fences it, executes or suggests.
3. **Text answer** — LLM answers directly from this documentation.

**Command safety** (SciFi enforces this regardless of LLM output):

| Auto-execute | Interactive handoff | Suggest only | Forbidden |
|-------------|--------------------|--------------|-----------| 
| BOOTSTRAP, START, END, STATUS, RUN, EVOLVE suggest | MAKE, ASK | RESET, MAINTAIN, EVOLVE model | EVOLVE code |

The fence sets a **floor** per command type. The LLM can raise restrictiveness
(e.g. flag suspicious input as suggest-only) but never lower it. Shell
metacharacters are rejected before classification. LLM calls retry once on
timeout (30s per attempt).

---

## SciF — deterministic commands

```bash
# Lifecycle
SciF BOOTSTRAP                       # Pam → Kam → F → smoke test
SciF START                           # start LLM gateway
SciF END                             # stop gateway
SciF STATUS                          # show what's running
SciF RESET                           # clean runtime (keep tasks/skills/audit)
SciF MAINTAIN                        # evolution suggest + model + audit roll

# Work
SciF RUN <task>                      # run a task (local or SLURM, auto-routed)
SciF JOBS                            # active driver SLURM jobs + recent logs
SciF MAKE <desc.md>                  # create task interactively
SciF MAKE --desc "text" [out_dir]    # create task from inline description
SciF MAKE <desc.md> --skill <name>   # create a skill
SciF ASK                             # multi-turn agent (tools, debug, explore)
SciF EVOLVE <suggest|model>          # run evolution (code mode disabled)
```

---

## Bootstrap

### Prerequisites

1. **Apptainer** — container runtime. Path set in `ENV.sh` as `APPTAINER=`.
   Check: `apptainer --version`. On NERSC: see APPTAINER path in ENV.sh
2. **API keys** — at least one provider key set in `.secret.sh` (sourced by `ENV.sh`)

### Dependency chain

```
Apptainer binary exists
  ↓
Kam: rl9_micromamba_0.sif (container image)
  ↓
.secret.sh: at least one API key set (sourced by ENV.sh)
  ↓
Pam: gateway.model.yaml (references keys via os.environ/)
  ↓
Pam: gateway.sif (built from precursor + gateway.def)
  ↓
Gateway starts → SciFi LLM mode available
  ↓
F: F.overlay.img (Python + openai + requests)
  ↓
Full system ready
```

**What works at each stage:**
- **Always**: SciF (pure bash), SciFi rule-based mode
- **After gateway**: SciFi LLM mode
- **After F overlay**: SciF RUN, MAKE, ASK, EVOLVE

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `apptainer not found` | Check ENV.sh APPTAINER path, or `module load apptainer` |
| `gateway.model.yaml not found` | `cp Pam/gateway.model.yaml.template Pam/gateway.model.yaml` |
| `<SETME> in secret` | Edit `.secret.sh`, set at least one API key, then `source ENV.sh` |
| `gateway.rank.yaml missing` | SciF BOOTSTRAP auto-generates from secret.yaml |
| Gateway won't start | `bash Pam/gateway.debug.sh` (foreground with full logs) |
| SciFi rule-based only | Gateway not running — SciF START |
| Continue a task manually | `cd F/tasks/<task>_<ts> && bash $BASEDIR/F/F.debug.sh` (drops you in the same container, `env.sh` auto-sourced, GPU auto-detected) |

---

## Tasks

### Create a task

```bash
# From a description file
SciF MAKE my_idea.md

# Or via SciFi (passes your text to the maker)
SciFi "create a task that trains MNIST with PyTorch on 1 GPU"
```

The task maker asks clarifying questions, confirms understanding, then generates.

### Task format (top.md)

New tasks use `---` frontmatter + `# Title` + 3 sections. Parsed deterministically
by `F/task_parser.py` — malformed files are rejected with line-number errors.

```markdown
---
Rank: 2
BashTime: -1
Skills: NERSC_slurm
---

# My Task Name

## Context
What the agent needs to know.

## Todo
1. Step one
2. Step two

## Expect
- file.txt exists with content X
- accuracy > 95%
```

Legacy tasks (without `---` fences) still work via fallback in `driver.py`.

Metadata (all optional, inside `---` fences):
- `Rank` (0-4) — task difficulty, controls model selection
- `Timeout` (seconds) — wall limit
- `BashTime` (-1=unlimited) — per-bash-call cap
- `ThinkTime` (-1=unlimited) — LLM time cap per attempt; propagates to subtasks
- `Skills` (comma-separated) — skill names to inject
- `ForceModel` — pin worker to exact model name
- `ControlModel` — pin review/prescan model (name or rank number)
- `Thinking: N` — force thinking mode with budget N tokens from start
- `NoMemory: on|off` — when on, do not read global memory and do not write global history (clean-room run). Does not affect TaskGroup memory
- `TaskGroup: name` — opt-in cross-task memory. Tasks in the same group share domain lessons from failed runs. Stored at `F/run/.taskgroup_memory/<name>.md`. Independent of NoMemory
- `CommonHome: ro|rw|disable` — mount F/home → /home (default: rw). Portal symlinks ~/.local and ~/.cache to /tmp to prevent cross-run pollution
- `CommonStorage: rw|ro|disable` — mount F/mnt → /mnt (default: rw)
- `GPU: no|local|slurm|on` — GPU policy (default: no)
    - `no` — never use GPU
    - `local` — use GPU only when host has nvidia-smi (no SLURM)
    - `slurm` — always submit to a SLURM GPU node (overrides default `Slurm: off`)
    - `on` — auto: local GPU if present, else SLURM (requires `Slurm: on`)
- `Slurm: off|on` — SLURM submission (default: off). `on` lets dense
  workloads (`BashTime: -1`) auto-route to a CPU SLURM node. Combining
  `GPU: slurm` with explicit `Slurm: off` is an **error**.
- `SlurmHours: N` — wall hours for SLURM allocation (default: 4)
- `SlurmCpus: N` — CPUs per task for SLURM allocation (default: 32)

### Writing effective tasks

A trivial task can still time out if the worker spends its LLM wall on
exploratory bash (`ls`, `pwd`, `which`, re-`cat`-ing files it just wrote).
Weaker rank-0 models are especially prone to this "analysis paralysis."
The task text itself is the main lever to steer the worker toward direct
execution.

Guidelines for the `Context` block:

- **State assumed environment explicitly.** Instead of leaving the agent to
  verify, say "the shell is a standard Linux environment — `python3`, `md5sum`,
  `mkdir` are available." This removes the incentive to `which`/`--version`-check.
- **Encourage single-call execution for trivial tasks.** Add a sentence like
  "solve with one `python3 -c '...'` call" or "chain setup, run, and write
  into one bash script." Rank-0/1 tasks that finish in <1 minute on a human
  shouldn't need five tool calls.
- **Name any preconditions the suite already handles.** If `/mnt/foo` is
  guaranteed by the setup, say so — otherwise the agent will defensively
  `ls` it.
- **Discourage intermediate verification** when the Expect section already
  covers it. Agents that `cat result.txt` after writing it consume wall-time
  without adding value; the reviewer will verify independently.

Guidelines for `Todo`:

- Prefer outcome-oriented steps over procedural ones. "Write `parsed.json`
  mapping keys to values" is better than "1. list dir, 2. read file, 3. parse,
  4. dump JSON" — the procedural form invites one LLM call per step.
- For environment-setup tasks, phrase the sequence as a single imperative:
  "create env, install X, write version to result.txt" rather than three
  numbered steps.

Guidelines for `Expect`:

- Make each bullet something the reviewer can check with one tool call
  (`read_file`, `grep`, `ls`). Expectations that require re-running the
  worker's logic will slow review and are brittle.

These patterns apply especially to tasks intended for rank-0/1 (cheap/weak
workers). Higher-rank tasks (2+) face a different failure mode — toolchain
friction and capability ceilings — and benefit more from `TaskGroup: <name>`
for cross-run lessons, or explicit Context hints about known pitfalls.

### Run a task

```bash
SciF RUN task_name
# or
SciFi run task_name
```

`SciF RUN` is the same entry point regardless of whether the task runs
locally or on a SLURM GPU node — `F/portal.py` reads `GPU` + `Slurm` from
task metadata and routes accordingly. Examples:

```yaml
# Pure CPU task — runs locally (default)
Rank: 1

# Train on a GPU; only when the host already has one
Rank: 2
BashTime: -1
GPU: local

# Train on a GPU; always submit to a NERSC GPU node, 8h
Rank: 2
BashTime: -1
GPU: slurm
SlurmHours: 8

# Auto: use the local GPU if present, otherwise submit to SLURM
Rank: 2
BashTime: -1
GPU: on
Slurm: on
```

When the driver submits to SLURM it prints `[submitted] <task> → log: ...`
and exits; the actual run starts when the allocation lands and re-invokes
`python3 F/portal.py driver <task>` inside the job.

**Output flow:** prescan → iterations → review → result → final review

**Final review** prints: conclusion (DONE/NOT DONE) + task suggestions.
System suggestions saved to `.suggestion.md` (evolution reads these).

### Task output location

```
F/tasks/<task_name>_<timestamp>/
├── top.md               # task definition
├── output files          # whatever the agent created
├── .history.md          # full execution log
├── .history_index.md    # summary
├── .memory.md           # task memory
└── .suggestion.md       # final review (conclusion + suggestions)
```

---

## Skills

```bash
SciF MAKE desc.md --skill skill_name
```

**Tool skill** (adds a callable function): `skill.yaml` + `run.py`
**Context skill** (injects knowledge): `SKILL.md` + optional `templates/`

Use in tasks: add `Skills: skill_name` to `top.md`.

### Log parsing skill (rtfl)

`rtfl` ("Read The F***ing Log") is a tool skill for structured log analysis.
Agents use it instead of `read_file` or `cat` on large logs.

**Modes:**

| Mode | What it does |
|------|-------------|
| `skeleton` (default) | Errors, warnings, exit codes, stack traces, test summaries, head/tail |
| `grep` | Regex search with context lines |
| `slice` | Line range extraction (1-indexed) |
| `head` | First N lines (default 50) |
| `tail` | Last N lines (default 50) |

**Workflow**: Always start with `skeleton` to see the shape, then `grep` or
`slice` to zoom into specific sections. Never dump an entire log into context.

```yaml
Skills: rtfl

## Todo
Run the build and diagnose any failures from build.log

## Expect
- diagnosis.md lists root cause with line numbers
```

**A/B validated** (gemma4×gemma4, 1856-line ML training log, 5 buried signals):

| Metric | Without rtfl | With rtfl |
|--------|-------------|-----------|
| Signals found | 5/5 | 5/5 |
| LLM calls | 27 | 22 (−19%) |
| Line numbers in report | No | Yes |

See `RD/rtfl_ab_test.md` for full analysis.

### Environment skills

Every task gets one of three env skills injected. If the task declares none,
the driver auto-injects `DEFAULT_ENV_SKILL` from `ENV.sh` (default `temp_env`).
If that skill is missing from `Nam/skills/`, a minimal hardcoded prompt
pointing at `/tmp/mamba_env` is appended instead — always isolated and
ephemeral, since the container's `/tmp` is a fresh per-run bind that's
discarded on exit.

| Skill | Install location | Persists | Typical use |
|-------|------------------|----------|-------------|
| `temp_env` (default) | `/tmp/mamba_env` | No — dies with container | Throwaway runs, keeps task dir clean |
| `local_env` | `./mamba_env` (task dir) | Yes, within the task dir | Per-task isolated env |
| `common_env` | `/mnt/sci_envs/<prefix>` | Yes, across tasks | Heavy stacks (ROOT, PyTorch) reused across tasks |

Heavy software (ROOT ~1 GB, PyTorch ~2 GB) is slow to install. `common_env`
automates **discovery → verify → reuse or create** of shared envs at
`/mnt/sci_envs/<name>/`.

**Rule: reuse or create new — never modify an existing env.**

If the env exists and works → reuse. If not → create a new one (if `/mnt` is
writable) or fall back to a local env in the task directory.

**How it works end-to-end:**

```yaml
# This is the entire task spec. The skill handles everything else.
Skills: common_env

## Todo
Fit a Gaussian with ROOT and save fit.png

## Expect
- fit.png exists
```

1. `portal.py` sees `Skills: common_env` + no explicit `CommonStorage`
   → defaults `CommonStorage` to `rw` (so the skill can create envs)
2. Container starts with `/mnt` writable
3. Skill context injected into agent prompt (from `Nam/skills/common_env/SKILL.md`)
4. Agent checks `/mnt/sci_envs/` for a matching env → found? verify → reuse (50-60s)
   → not found? create + verify → reuse on next run (150-500s first time only)
5. Agent writes `env.sh` with PATH/LD_LIBRARY_PATH exports
6. Driver auto-sources `env.sh` before every bash call — tools available as bare commands

**CommonStorage interaction:**

| `CommonStorage` value | Env skill behavior |
|-----------------------|-------------------|
| (empty) + env skill loaded | → `rw` (skill escalates default) |
| `ro` | Reuse only — if no env found, install locally in task dir |
| `rw` | Reuse or create new in `/mnt/sci_envs/` |
| `off` | No `/mnt` — install locally |

**Validated performance (gemma4×gemma4, ROOT):**

| Scenario | Wall | Iters |
|----------|------|-------|
| Cold start (no env, skill creates it) | 167s | 11 |
| Warm reuse (env exists) | 53s | 6 |
| Without skill (manual install task) | 522s | 76 |

---

## Evolution

```bash
SciF EVOLVE suggest        # analyze tasks, write suggestions
SciF EVOLVE model          # adjust model ranks from evidence
SciF MAINTAIN              # suggest + model + audit roll (all-in-one)
```

Evolution reads `.suggestion.md` from each task (final review feedback) plus
`.history.md` and `.memory.md`. It writes `.global_memory.md` (workers read this)
and `.global_suggestion.md` (human action items).

---

## Monitoring

```bash
SciF STATUS                              # gateway + task/skill counts
cat F/tasks/<task>/.history_index.md     # task summary
cat F/tasks/<task>/.suggestion.md        # final review
cat F/run/.global_history.md             # all task runs
cat F/run/.global_memory.md              # cross-task knowledge
cat F/run/.global_suggestion.md          # evolution suggestions
cat F/run/.taskgroup_memory/<name>.md    # TaskGroup cross-task memory
ls  F/run/slurm/                        # SLURM job stdout/stderr
ls  F/run/logs/                         # pre-container local logs (bench, sci_bench, etc.)
```

---

## Benchmarking

Independent harness in `Sam/`:

```bash
bash Sam/bench.sh phase1                                            # round-robin model comparison
bash Sam/bench.sh phase2                                            # validate best models
bash Sam/bench.sh custom <task_list> <work_model> <control_model> <reps>
python3 Sam/bench_analyze.py                                        # results summary
python3 Sam/bench_optimize.py --output report.md                    # deep analysis
```

Phase 1 cycles all eligible models per rank (10 reps). Phase 2 validates the picks (3 reps). Custom mode runs a fixed (work, control) pair on any task list.

Three task suites:

| Suite | Tasks | Coverage |
|-------|-------|----------|
| `bench_tasks.txt` | 30 (10 types × 3 styles) | Capability matrix: logic, debug, data, env, shortcut |
| `bench_tasks_agentic.txt` | 7 | SWE-bench/MLE-style agentic tasks |
| `sci_bench_tasks.txt` | 60 (20 types × 3 styles) | Scientific computing: plotting, stats, ROOT, GPU training, SLURM, web, skills, chained workflows |

### Scientific benchmark (`Sam/sci_bench_run.sh`)

```bash
# Run all 60 sci tasks with gemma4×gemma4
bash Sam/sci_bench_run.sh

# Run a subset
bash Sam/sci_bench_run.sh sci_file_ops_simple sci_torch_smoke_normal

# Override parallelism
PARALLEL=2 bash Sam/sci_bench_run.sh

# Independent verification after run
python3 Sam/sci_verify.py
```

Results in `Sam/sci_results.csv`, verification in `Sam/sci_verify.csv`.

Validated 2026-04 with gemma4×gemma4: 42/42 non-ROOT/non-SLURM tasks passed.
Refined style fastest (123s avg), simple slowest (174s avg).

---

## Per-rank limits

Iteration count and wall time scale with task rank. Higher-ranked tasks get more room.

**Read-only iterations are free:** only iterations with mutating tool calls (`bash`, `write_file`, `edit_file`, `done`, `subagent`) count against the budget. `read_file`, `memory_read`, and `compact` calls don't consume iterations, so agents can freely explore source files without penalty.

| Rank | Max effective iters | LLM wall | Total wall (incl. bash) |
|------|---------------------|----------|-------------------------|
| 0 (trivial) | 10 | 60s | 30min |
| 1 (typical) | 20 | 120s | 30min |
| 2 (reasoning) | 30 | 240s | 30min |
| 3 (hard) | 30 | 300s | 30min |
| 4+ (very hard) | 50 | 360-600s | 30min |

Configurable via `ITER_LIMIT_PER_RANK`, `WALL_LIMIT_PER_RANK`, `TOTAL_WALL_PER_RANK` in `ENV.sh`. When review escalates rank on retry, the new (higher) limits apply automatically.

---

## Model configuration

Models ranked in `Pam/gateway.rank.yaml`. Selection: highest rank ≤ task rank, config order priority within same rank, budget-aware.

Current ranks (see `Pam/gateway.rank.yaml` for authoritative list):

| Rank | Models |
|------|--------|
| 3 | claude-opus (disabled by default) |
| 2 | **gemma4**, qwen3-coder, claude-haiku (disabled by default) |
| 0 | deepseek-v3, kimi-k2, qwen3-next-80b |
| -1 | gpt-oss (no tools) |

### Two canonical configurations

| Config | Work | Control | Backend | Use when |
|--------|------|---------|---------|----------|
| **Claude baseline** | claude-haiku | claude-haiku | Bedrock us-east-2 | Normal production, fast iteration |
| **Claude-free baseline** | gemma4 | gemma4 | Ollama Cloud | Anthropic unavailable, diversity required |

Both validated on Verilog RTL (3 tiers), ML reproduction (nu2flows), and 42-task
scientific benchmark suite (matplotlib, pandas, h5py, torch GPU, MNIST 1+2 GPU,
web fetch, skill invocation, ROOT, chained workflows).

**gemma4** handles both creative work AND independent tool-using verification
(re-runs build/test commands, catches fabrication). The fully Claude-free chain
is production-ready.

Add a model: add to `gateway.model.yaml` (use `os.environ/` for key) + `gateway.rank.yaml` (rank, budget) + restart gateway.

Auto-generated rank.yaml: all rank 0, budget -1. Run `SciF MAINTAIN` to tune.
