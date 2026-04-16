# F — SAM Driver & Evolution System Design Document

## 1. Overview

F is a self-improving agentic system built on the **SAM (Self-Assessed Module)** pattern. Every task is a closed loop: **Context → Todo → Expect**, sandwiched between a **Prescan** (planning) and a **Review** (verification). The system runs inside Apptainer containers, routes LLM calls through a LiteLLM gateway, and supports concurrent subtask execution with pause/resume.

### Core Principle: RALPH Loop

> With sufficient **variation** (trying different approaches) and **iteration** (repeating with feedback), any achievable expectation MUST eventually be met.

The driver never gives up because convergence is structural: each iteration gets new information (tool results, verifier feedback, memory, checkpoint re-grounding), making progress inevitable.

### Hard Beliefs (embedded in code, not configurable)

1. Every SAM WILL converge — never quit without a verdict
2. Every `done` MUST be reviewed — independent agent checks expectations
3. Review is orthogonal — different model, fresh context
4. Progress must be re-grounded — re-inject task + memory periodically
5. Errors are information — catch, report, continue
6. Prescan plans, review gates — both use highest model (overridable via ControlModel)
7. Model assignment is parent-controlled — parent decides rank, Pam selects (shuffled across subtasks, sticky within)
8. Fast iteration wins — prefer the fastest model that can solve the task
9. Malformed tool calls are dropped — never poison conversation history

### Hard Outer, Soft Inner

Two layers of control with different philosophies:

- **Outer (system code)**: Hard, definite, deterministic. Iter limits, rank caps, model
  routing, tool dispatch, review cascade — enforced by code, clear and unambiguous.
  The system guarantees these; agents cannot override them.

- **Inner (LLM prompts, agent guidance)**: Soft, suggestive, flexible. Strategy notes,
  checkpoint reminders, timeout suggestions, review feedback — the agent has its own
  reasoning and we guide it, never force it. Stronger or lighter suggestions are both
  valid; the agent decides how to apply them.

Never hardcode what the agent should decide. If a behavior is a system guarantee (must
always happen), enforce it in code. If it's agent strategy (should usually happen),
suggest it in the prompt. Example: bash timeout defaults to 30s (system), but for
`BashTime: -1` tasks the prompt suggests setting `timeout: 600` on long operations
(guidance). The agent can ignore it if the operation is short.

---

## 2. Architecture

### 2.1 Sandwich Structure

```
PRESCAN (ControlModel or highest, 1 LLM call)
  → rank, subtask dependencies, skills, context assembly
  ↓
SELECT MODEL (ForceModel or pam.select: highest rank ≤ R, health + budget + blacklist)
  ↓
┌──────────────────────────────────────────────────────┐
│ AGENT LOOP (fixed model, MAX_ITER, wall limit)       │
│  ├─ pause check (threading.Event)                    │
│  ├─ wall limit (excludes tool + subagent time)       │
│  ├─ effective iter count (read-only iters are free)  │
│  ├─ checkpoint (every N iters, re-inject task+memory)│
│  ├─ API call (thinking if enabled by review)         │
│  │   ├─ malformed tool call → drop, nudge, continue  │
│  │   ├─ nudge limit (5 consecutive) → blacklist+break│
│  │   ├─ error limit (5 consecutive) → blacklist+break│
│  │   └─ tool calls:                                  │
│  │       ├─ bash (agent-suggested timeout, capped)   │
│  │       ├─ read_file (offset/limit for large files) │
│  │       ├─ write_file, edit_file, web_fetch, memory  │
│  │       ├─ skill tools (from prescan selection)      │
│  │       ├─ subagent → scheduler.launch_blocking()   │
│  │       └─ done → REVIEW                            │
│  └─ avg_iter_s tracked in history                    │
└──────────────────────────────────────────────────────┘
  ↓ done                ↓ exhausted
REVIEW (done)          REVIEW (failed) → fallback rank -2
  ↓                      ├─ delay → pause + timer + resume
  PASS → return          ├─ retry → same/exclude/escalate + thinking
  FAIL → retry           └─ reflect → REFLECTION → return

POST: index_history (rank -1 model, cheap summary)
      total wall time printed (solve + post breakdown)
```

### 2.2 File Structure

```
$BASEDIR/
├── SciF                    # Scripted entry point (bash dispatcher, sources ENV.sh)
├── SciFi                   # Intelligent entry point (stdlib Python, no container)
├── ENV.sh                  # All paths + parameters (the ONLY source of truth)
│
├── F/                      # Effector — driver, evolution, ask, lifecycle scripts
│   ├── driver.py           # SAM driver (~2500 lines)
│   ├── task_parser.py      # Deterministic task .md parser (frontmatter + sections)
│   ├── portal.py           # Unified container launcher (replaces driver.sh etc.)
│   ├── evolution.py        # Global evolution, 3 modes
│   ├── ask.py              # Multi-turn interactive agent
│   ├── BOOTSTRAP.sh        # Full system setup (Pam → Kam → F → smoke test)
│   ├── START.sh / END.sh   # Start/stop gateway + usage info
│   ├── MAINTAIN.sh         # Evolution suggest + model + audit roll
│   ├── RESET.sh            # Clean runtime, keep data
│   ├── F.bootstrap.sh      # Create overlay + install Python env
│   ├── F.overlay.img       # 2GB ext2 overlay (Python + openai + requests)
│   ├── F.debug.sh          # Interactive container shell (continue a task manually)
│   ├── F.design.md         # This file (technical reference)
│   ├── F.usage.md          # Usage guide (SciFi reads this)
│   ├── .misc/              # Archived/superseded scripts
│   │   ├── driver.sh.archived    # (replaced by portal.py)
│   │   ├── evolution.sh.archived # (replaced by portal.py)
│   │   ├── ask.sh.archived       # (replaced by portal.py)
│   │   └── ...
│   ├── run/                # Global state (persistent across runs)
│   │   ├── .global_memory.md      # Cross-task knowledge (evolution writes)
│   │   ├── .global_history.md     # System-level tape (append-only)
│   │   ├── .global_suggestion.md  # Human help requests (evolution writes)
│   │   ├── .taskgroup_memory/     # Per-group cross-task ledger (auto)
│   │   ├── slurm/                 # SLURM job stdout/stderr logs
│   │   └── logs/                  # Pre-container local logs (bench, sci_bench, etc.)
│   └── tasks/              # Timestamped task run copies (persistent)
│       └── taskN_YYYYMMDDHHMMSS/
│           ├── top.md             # SAM definition
│           ├── subtask.md         # Subtask SAMs
│           ├── .memory.md         # Task memory (worker + review write)
│           ├── .history.md        # Task history (append-only tape)
│           ├── .history_index.md  # Auto-generated outline (rank -1 model)
│           ├── .suggestion.md     # Final review (task + system suggestions)
│           └── .review_feedback.*.md  # Review hints per subtask (cleared on pass)
│
├── Kam/                    # Kontainer images
│   ├── rl9_micromamba_0.sif       # L0: system essentials + micromamba (118 MB)
│   ├── rl9_micromamba_{1,2,3}.sif # L1-L3: progressive layers
│   ├── rl9_micromamba_{0..3}.def  # Build definitions
│   ├── rl9_micromamba.bootstrap.sh
│   └── rl9_micromamba.debug.sh    # Interactive container shell
│
├── Sam/                    # Task library + maker + benchmark suite
│   ├── task_maker.py       # Interactive task builder (supports --desc)
│   ├── task_maker.sh       # Apptainer wrapper
│   ├── tasks/              # Source task definitions (copied to F/tasks on run)
│   ├── task_template/      # Reference task with all metadata
│   ├── bench.sh            # Benchmark orchestrator (phase1/phase2/custom modes)
│   ├── bench_config.sh     # PHASE1_REPS, PHASE2_REPS, BENCH_PARALLEL, BENCH_TIMEOUT
│   ├── bench_tasks.txt     # Phase 1/2 task list (10 task types × 3 versions)
│   ├── bench_tasks_agentic.txt # Agentic benchmark suite (SWE-style, MLE, etc.)
│   ├── bench_analyze.py    # Per-model statistics + best-model picks
│   ├── bench_optimize.py   # Deep analysis from Cam/history for system tuning
│   ├── bench_fixtures/     # Shared seed data for benchmark tasks
│   └── bench_results/      # CSV + per-task logs (gitignored)
│
├── Nam/                    # Skill library + maker
│   ├── skill_maker.py      # Interactive skill builder (supports --desc)
│   ├── skill_maker.sh      # Apptainer wrapper
│   ├── skills/             # Skill library
│   │   ├── text_stats/     # Tool skill: word/line/char counts
│   │   ├── json_tool/      # Tool skill: JSON parse/query
│   │   ├── rtfl/           # Tool skill: structured log parser
│   │   ├── common_env/     # Context skill: shared env at /mnt/sci_envs/
│   │   ├── local_env/      # Context skill: local micromamba env
│   │   ├── temp_env/       # Context skill: ephemeral env in task dir
│   │   └── NERSC_slurm/    # Context skill: SLURM templates
│   └── skill_template/     # Skill template reference
│
├── Pam/                    # Proxy/gateway + model selection
│   ├── pam.py              # Model selection class (shared by all container scripts)
│   ├── gateway.sh          # Instance-mode start/stop/status
│   ├── gateway.debug.sh    # Foreground mode (for debugging)
│   ├── gateway.bootstrap.sh # Pull + build gateway SIF
│   ├── gateway.def         # Build definition (adds %startscript)
│   ├── gateway.sif         # LiteLLM container (built from precursor + def)
│   ├── gateway.rank.yaml   # Model ranking + budget (auto-generated if missing)
│   └── gateway.model.yaml # LiteLLM config (keys via os.environ/ from ENV.sh)
│
└── Cam/                    # Audit (write-only, never deleted)
    ├── cam.py              # Audit recording module (imported by all agents)
    ├── roll.sh             # Compress + archive old logs
    └── *.jsonl             # Audit logs (per-session, per-agent)
```

---

## 3. Model Selection (`Pam/pam.py`)

All model selection logic lives in the `Pam` class (`Pam/pam.py`), shared by all
container-based scripts. SciFi uses a fixed model group (no Pam).

### 3.1 Pam API

```python
pam = Pam(rank_yaml_path, gateway_url, fallback_highest, fallback_working)

pam.select(rank, exclude, usage, require_thinkable, shuffle, force_model) → dict
pam.highest(usage) → str           # shortcut: highest-rank model name
pam.config(name) → dict            # full config for a model
pam.is_thinkable(name) → bool
pam.max_rank() → int
pam.all_ranks() → list[int]
pam.report_connection_ok()         # call after successful API call
pam.report_connection_error()      # call after connection/timeout error
pam.blacklist_model(name)          # session blacklist (nudge/error limit)
pam.is_blacklisted(name) → bool
pam.reload()                       # re-read rank yaml (for evolution)
```

### 3.2 Rank Tiers

Models are ranked in `gateway.rank.yaml` (benchmark-validated 2026-04):

```
Rank < 0: no tool support (text-only usage)
  Rank -2: reasoning-only — review fallback, deep thinking
  Rank -1: cheap text — history indexing, text compaction (gpt-oss)
Rank >= 0: tool-capable (worker, tool-based review)
  Rank  0: backup — reliable but slow (deepseek-v3, kimi-k2, qwen3-next-80b)
  Rank  2: best — work + control capable (gemma4, qwen3-coder, claude-haiku)
  Rank  3: top-tier premium thinkable (claude-opus)

Ranks are dynamic — evolution adjusts based on observed performance.
```

### 3.3 Selection Algorithm

If `force_model` is set, bypass all logic and return that model directly.
Otherwise, for non-negative ranks: waterfall from highest-rank ≤ target, checking
health, budget, blacklist, and requirements. If nothing below, try above. Last resort: rank -1.
For negative ranks (e.g. -1, -2): direct pick from that exact rank (no waterfall).

Session blacklist: models that hit error_limit or nudge_limit are blacklisted via
`pam.blacklist_model()` for the rest of the driver session. Blacklisted models are
excluded from `_can_use()` checks. Resets on next `SciF RUN`.

Fallbacks when no rank config loaded: `FALLBACK_HIGHEST` for "highest" requests,
`FALLBACK_WORKING` for ranked requests. Both set in ENV.sh.

### 3.4 Health & Error Tracking

Health check via `/health` is intentionally NOT used: LiteLLM's health endpoint
returns many false positives (endpoints that work fine in practice but get marked
sick by background probes). The `_refresh_health()` method exists but `_can_use()`
does not call it.

Instead, Pam relies on **session blacklist**: `report_connection_error()` /
`nudge_limit` / `error_limit` catch actually-broken models at runtime.
Connection errors tracked via `report_connection_ok/error()`; when errors exceed
`connection_max`, Pam falls back to rank -1 models.

### 3.5 Stickiness vs Shuffle

**Sticky within a subtask**: once a model is assigned to an `AgentNode`, it stays
fixed for all iterations. The caller holds `node.model` — no re-selection per iteration.
Only review can change it (exclude, escalate rank, enable thinking).

**Shuffle across subtasks**: when launching subtasks, `pam.select(rank, shuffle=True)`
randomizes models within the same rank. This gives different subtasks different models,
producing performance data for evolution to compare and rank-adjust.

### 3.6 Duplicate Ranks

Multiple models can share a rank. Without shuffle: config order = priority. With shuffle:
random order. On retry with `exclude_model`, the excluded model is skipped and the next
available sibling at the same rank is picked.

### 3.7 Model Selection on Retry

Review agent decides (mutually exclusive):
- **Same model**: omit model fields (model was fine, just retry)
- **Exclude current**: `exclude_model: true` (model did poorly, try sibling)
- **Escalate rank**: `suggested_rank: N` (task needs stronger model)

### 3.8 Thinking Mode

Some models support extended thinking (`thinkable: true` in rank config).
- Disabled by default (fast iteration wins)
- Enabled only when review suggests it for complex reasoning failures
- `thinking_budget` capped by model's `max_thinking_budget` and `max_tokens`
- Review sets: `enable_thinking: true, thinking_budget: 5000`

### 3.9 Budget

- `budget: N` = max API calls per run for that model. `budget: -1` = unlimited
- `budget: 0` = blacklist (model never selected)
- Tracked in `_usage` dict in driver.py (per-session, thread-safe)
- Pam checks budget via `usage` dict passed by caller — Pam does NOT track usage itself
- Evolution can adjust budgets in `model` mode

---

## 4. Agent Types

### 4.1 Worker Agent

- Executes the SAM task
- Model: ranked (≤R from prescan)
- Tools: base 9 (bash, read_file, write_file, edit_file, web_fetch, memory_read, memory_write, subagent, done) + prescan-selected skills
- Closed environment: only sees assigned tools/skills

### 4.2 Review Agent

- Two modes: verify (done case), triage (failed case)
- Model: ControlModel or highest rank
- If model rank < 0: text-only path (single LLM call, JSON verdict from prompt)
- If model rank >= 0: tool-based path (bash, read_file, memory_read, compact) + verdict/decision
- Pauses all siblings before reviewing (consistency)
- `finally` block resumes siblings

**Anti-fabrication review cascade (4 defensive stages):**

```
Primary reviewer (tool-capable, adaptive iter cap: 30 for verify-heavy Expects)
 ├─ commits verdict → done
 └─ iter cap reached → Fix C: force-commit (terminal tool only, 1 extra call)
    ├─ commits → done
    └─ Fix D: lateral reviewer (another tool-capable model, same rank, exclude primary)
       with prior investigation log (raw tool outputs, no interpretation)
       ├─ commits → done
       └─ Fix A': conservative text-only fallback (rank -2)
          strict anti-fabrication rules; rejects hedging/admission language
          ├─ approves unambiguous success → done
          └─ rejects → retry
```

- **Fix C** (force-commit): extracts partial verdict from observations already gathered instead of discarding them
- **Fix D** (lateral rotation): preserves tool access by trying another model before dropping to no-tool fallback; prior observations shared as raw (tool_call, tool_result) pairs with interpretation stripped
- **Fix A'** (conservative fallback): text-only reviewer applies strict rules — rejects if worker admits failure, hedges, or lacks quoted evidence for each Expect item

**Review feedback persistence**: on rejection, `.review_feedback.<stem>.md` is written with concrete observations. Survives retries. Injected into the next worker's context (independent of NoMemory). Cleared on SAM_VERIFIED. Retry hints use structured KEEP/FIX/RUN format to preserve correct progress across attempts.

### 4.3 Reflection Agent

- Triggered when review chooses "reflect"
- Model: ControlModel or highest rank
- If review timed out: escalates to highest (control model was too weak)
- Tools: read-only + memory_write
- Diagnoses: task_definition, task_too_large, stuck_loop, review_too_strict, tool_limitation, driver_bug
- Updates memory with findings

### 4.4 Compact/Index Agent

- Rank -1 model (cheapest)
- No tools — pure text in/out
- Used for: history indexing (post-task), text compaction (review's `compact` tool)

### 4.5 Final Review Agent

- Runs after every task (pass or fail), NEVER retries
- Model: highest rank (same as review — quality judgment)
- No tools — pure text in/out
- Reads: task definition, history index, memory, result
- Writes: `.suggestion.md` in task folder
- Output structure:
  - `## Conclusion` — DONE or NOT DONE + one-line reason (printed to user)
  - `## Task suggestions` — how to improve the task definition (printed to user)
  - `## System suggestions` — observations for evolution (NOT printed, saved only)
- Evolution reads `.suggestion.md` as pre-analyzed feedback per task

### 4.6 Evolution Agent

- Separate script (`evolution.py`), 3 modes
- Model: highest (from `FALLBACK_HIGHEST` env)
- `suggest`: read-only analysis → `.global_suggestion.md`
- `code`: can modify `driver.py`
- `model`: can modify `gateway.rank.yaml`
- All modes: read+write `.global_memory.md`, append `.global_history.md`

---

## 5. Concurrency & Scheduling

### 5.1 AgentNode

Each agent is an `AgentNode` with:
- Fixed model (deterministic, set by parent)
- Rank (may escalate on retry)
- Thinking state (enabled/budget)
- Pause event (`threading.Event` — cleared=paused, set=running)
- Children list (for signal propagation)

### 5.2 Scheduler

Wave-based: pick tasks whose deps are done → launch in parallel → wait → repeat.
- `threading.Semaphore(MAX_PARALLEL)` limits concurrency
- `launch_blocking()` for sequential subagents
- `run_plan()` for dependency-ordered parallel execution
- `pause_siblings()` / `resume_siblings()` for review consistency

### 5.3 Pause/Resume

Three triggers:
- **Review pause**: pauses siblings before reviewing (automatically resumed in `finally`)
- **Delay pause**: review says wait → `Timer(N, resume)` → auto-resume
- **Concurrency limit**: `Semaphore.acquire()` blocks before start

Pause mechanics:
- `check_pause()` called before each API call + between tool calls
- `threading.Event.wait()` — zero cost if not paused, blocks if paused
- Propagates recursively to all descendants

### 5.4 Thread Safety

- `_usage`: `_usage_lock` (threading.Lock) — in driver.py
- Health/connection state: locks inside Pam instance (`_health_lock`, `_conn_lock`)
- `.history.md` writes: `_history_lock` (threading.Lock)
- `.memory.md`: `_get_mem_lock(task_dir)` per-task Lock
- GIL: not a problem — all work is I/O-bound (API calls, subprocess)

---

## 6. Timing System

### 6.1 Wall Limit (LLM-only)

Per-rank wall limit counting only LLM API call time (excludes bash/tool time):
```
WALL_LIMIT_PER_RANK = "60,120,240,300,360,600"
# rank 0: 60s, rank 1: 120s, ..., rank 4+: 300-600s
```

Task .md can override: `Timeout: 120`

### 6.2 Total Wall Limit (including bash/tool time)

Hard clock limit to prevent runaway tasks:
```
TOTAL_WALL_PER_RANK = "1800,1800,1800,1800,1800,1800"
# all ranks: 30min (uniform hard cap)
```

This catches tasks where bash calls consume hours while LLM time stays low.

### 6.3 Per-Rank Iteration Limits

Lower ranks get fewer iterations — a rank-0 task needing 50 iterations is misranked:
```
ITER_LIMIT_PER_RANK = "10,20,30,30,50,50"
# rank 0: 10 iters, rank 1: 20, rank 2-3: 30, rank 4+: 50
```

When review escalates rank on retry, the new (higher) limits apply automatically.
MAX_ITERATIONS (50) is the absolute cap regardless of rank.

### 6.4 Bash Timeout

Agent suggests timeout per bash call: `bash(command="...", timeout=60)`
- Capped by task's `BashTime` from metadata (or `MAX_BASH_TIME` default 300s)
- `BashTime: -1` = no cap, disables total wall limit
- `Slurm: on` implies `BashTime: -1` (SLURM jobs are inherently long-running)
- Default if agent omits: 30s (hard, from tool schema)
- For `BashTime: -1` tasks: environment hints strongly suggest `timeout: 86400` for
  any workload command. The 30s default WILL kill long operations. Only trivial
  commands (ls, cat, grep) should use the default.

### 6.5 Environment Activation (env.sh)

Each bash tool call is a fresh subprocess — no shell state persists. Environment
activation is handled via `env.sh` in the task directory:

- If `env.sh` exists, `_prepare_bash()` wraps every bash command with `. ./env.sh &&`
- This covers worker bash calls (`_execute_tool`) and reviewer bash calls (`_execute_tool_readonly`)
- If `env.sh` does not exist, commands run with bare system PATH
- Agents write `env.sh` after discovering or creating an environment (guided by
  env skills: `common_env`, `local_env`, `temp_env`). If no env skill is declared,
  the skill named by `DEFAULT_ENV_SKILL` in `ENV.sh` is auto-injected (default
  `temp_env`). If that skill is missing from `Nam/skills/` (deleted), the driver
  appends a minimal hardcoded fallback prompt pointing at `/tmp/mamba_env`,
  which is always isolated and ephemeral (container `/tmp` is a fresh per-run
  bind, discarded on exit)
- Shared pre-built envs live at `/mnt/sci_envs/` (verilator, root, pytorch, etc.)
- Error recovery: malformed env.sh produces visible errors; agent can fix or delete it

Replaces the old `AGENT_TOOLCHAIN_PATH` mechanism which polluted all tasks with
all envs' binaries indiscriminately.

**Interactive debug shell**: `F/F.debug.sh` opens a shell in the same container
the agent ran in, for continuing work on a task manually.

```
cd F/tasks/<task>_<ts>
bash $BASEDIR/F/F.debug.sh
```

- `$PWD → /srv` (also `HOME` and cwd); `F/mnt → /mnt`, `F/home → /home` (only if they exist); fresh `/tmp`
- Overlay mounted `ro`, driver micromamba env activated
- Auto-sources `/srv/env.sh` if present — bare `python`/`gcc`/... resolve to the agent's env (for `temp_env` runs the `/tmp/mamba_env` it points at is already gone)
- GPU auto-detect follows the same rule as `portal.py`: respect `CUDA_VISIBLE_DEVICES` if set, else use `nvidia-smi`; pass `--nv` whenever any GPU is visible, and echo what was detected

### 6.6 GPU Metadata

```
GPU: no | local | 1-4 | all | ALL | slurm | on   (default: no)
```

GPU controls exactly two hard things: `--nv` (GPU passthrough) and `CUDA_VISIBLE_DEVICES`
(which GPUs are visible). **Never disable usable local GPUs** — if free, always map them.

| Value | `--nv` | CUDA_VISIBLE_DEVICES | Slurm default | Hint |
|-------|--------|---------------------|---------------|------|
| `no` | no | — | off | No GPU |
| `local` | yes (require) | Auto-pin 1 free | off | "GPU pinned" |
| `1`-`4` | yes (require) | Auto-pin N free | off | "N GPUs pinned" |
| `all` | yes (require) | All host-visible | off | "All visible GPUs" |
| `ALL` | yes (require) | ALL physical (**debug!**) | off | "Debug: all physical" |
| `slurm` | yes if available | Auto-pin 1 free if available | **on** | "Prefer SLURM GPU for real workload" |
| `on` | yes if available | Auto-pin 1 free if available | off | "Check nvidia-smi" |

`GPU: slurm` vs `GPU: on`: both map local GPU if available. The only difference
is `slurm` changes Slurm default to on (enabling sbatch) and hints the agent to
prefer SLURM for production GPU work. Local GPU is still available for testing.

**Auto-pin logic** (`portal.resolve_gpu` / `portal._select_gpus`):
1. Determine usable GPUs: respect host `CUDA_VISIBLE_DEVICES` (if set), else all physical
2. Find free GPUs: no running compute processes (`nvidia-smi --query-compute-apps`)
3. Pick first N free GPUs, set `CUDA_VISIBLE_DEVICES`
4. If user already pinned to exactly N devices, leave unchanged
5. If fewer free than requested:
   - `GPU_ALLOW_OVERUSE=false` (default): error, refuse to run
   - `GPU_ALLOW_OVERUSE=true`: pass all usable GPUs (warning)
6. Overuse from parallel agents competing for GPUs: known issue, deferred

### 6.6 Slurm Metadata

```
Slurm: off | on   (default: off)
```

Slurm controls exactly one hard thing: whether sbatch/squeue/scancel are bind-mounted
into the container. `Slurm: off` is a **hard safety barrier** — no SLURM access at all.

| Slurm | Hard action | Implications |
|-------|-------------|-------------|
| `off` | Don't bind sbatch (safety barrier) | Agent cannot submit jobs |
| `on` | Bind sbatch + SLURM libs into container | Implies `BashTime: -1` |

`GPU: slurm` implies `Slurm: on`. Explicit `Slurm: off` with `GPU: slurm` is an ERROR.

The outer **never** auto-submits sbatch. The agent + skill decide whether, when, and
how to submit SLURM jobs (wall time, CPUs, GPUs, QOS). The outer only provides access.

### 6.7 Environment Hints (soft metadata injection)

Task metadata controls the outer system (hard). Environment hints (`[ENVIRONMENT HINTS]`
block) translate metadata into actionable guidance for the agent (soft). Appended to the
agent's first message, parsed from `task_content` at injection time.

| Metadata | Hard (outer) | Soft hint (inner) |
|----------|-------------|-------------------|
| `BashTime: -1` | No timeout cap, no total wall | "Set timeout=86400 for workload commands" |
| `GPU: local/N/all` | `--nv`, pin GPUs | "GPU(s) pinned via CUDA_VISIBLE_DEVICES" |
| `GPU: ALL` | `--nv`, all physical | "All physical GPUs exposed (debug)" |
| `GPU: slurm` | `--nv` if available, Slurm default→on | "Prefer SLURM GPU for real workload" |
| `GPU: on` | `--nv` if available | "Check nvidia-smi; if no GPU, use SLURM" |
| `Slurm: on` | Bind sbatch (off = hard barrier) | "SLURM submission enabled" |
| `CommonStorage: rw` | Bind `/mnt` read-write | "Check /mnt/sci_envs/ for existing envs" |
| `CommonStorage: ro` | Bind `/mnt` read-only | "Can use but not modify shared envs" |

Not all metadata needs hints: Rank, ForceModel, ControlModel, Thinking, NoMemory,
TaskGroup are fully handled by the outer system and invisible to the agent.

### 6.8 Early Break

- 5 consecutive nudges (text-only, no tool calls) → break to review
- 5 consecutive API errors → break to review
- Both trigger review for potential model rotation/escalation

---

## 7. Context Management

### 7.1 Injection Caps

| Injection point | Cap | Constant |
|----------------|-----|----------|
| Task content | 4000 chars | CAP_TASK |
| Global memory | 1000 chars | CAP_GLOBAL |
| Task memory | 4000 chars | CAP_MEMORY |
| Tool results | 10000 chars | _truncate() — head + last 5 lines |
| Checkpoint task | 4000 chars | CAP_TASK |
| Checkpoint memory | 4000 chars | CAP_MEMORY |

Full content always available via `memory_read` and `read_file` tools.
Truncation shows head + last 5 lines so agents see both errors and final results.

### 7.2 read_file with offset/limit

```python
read_file(path="large.log", offset=5000, limit=3000)
# Returns chars 5000-8000, with "[Showing 5000-8000 of 50000 chars]"
```

### 7.3 Message Trimming

`_trim_messages()` keeps: first 2 messages (system + task) + last (MAX_CONTEXT - 3) messages + trim notice. Default MAX_CONTEXT = 80 messages.

### 7.4 History Index

After each task, rank -1 model summarizes `.history.md` → `.history_index.md`.
Reflection and evolution agents read the index first, then dive into full history with offset/limit.

---

## 8. Skill System

### 8.1 Two Skill Types

**Tool Skill** (`skill.yaml` + `run.py`): Adds a callable tool to the agent's toolkit.
```
skills/text_stats/
├── skill.yaml    # name, description, OpenAI tool schema
└── run.py        # def execute(args, task_dir) → str
```

Examples: `text_stats`, `json_tool`, `rtfl` (structured log parser)

**Context Skill** (`SKILL.md`): Injects instructions/knowledge into agent context.
```
skills/NERSC_slurm/
├── SKILL.md      # ---frontmatter--- + full instructions
└── templates/    # reference files
```

Examples: `common_env`, `local_env`, `temp_env`, `NERSC_slurm`

### 8.2 Skill Loading

At driver startup: scan `SKILLS_DIR` for subdirectories.
- `skill.yaml` → parse manifest, import `run.py`, register as tool skill
- `SKILL.md` → parse frontmatter, store content as context skill
- Build `_skill_catalog` string for prescan

### 8.3 Skill Selection

1. Task .md declares: `Skills: text_stats, NERSC_slurm`
2. Prescan sees catalog + task hints → selects skills in plan
3. **Default env skill**: if no env skill (`common_env`, `local_env`, `temp_env`) is
   declared, the system auto-injects `DEFAULT_ENV_SKILL` (from ENV.sh, default `temp_env`).
   If that skill is missing from `Nam/skills/`, the driver appends a hardcoded fallback
   prompt guiding the agent to `/tmp/mamba_env`. Every task gets env guidance — agents
   always know where to install packages.
4. `_run_sam` builds tools: `TOOLS + selected tool skills`
5. Context skills injected into user message
6. Worker only sees assigned skills (closed environment)

### 8.4 Review Feedback

Review sees skill usage in history. On retry, review writes to memory:
"Add skill: X" or "Remove skill: Y". Prescan re-reads memory and adjusts.

---

## 9. Memory & History

### 9.1 Memory Files

| File | Scope | Writers | Purpose |
|------|-------|---------|---------|
| `.memory.md` | Task | Worker, reflect, review | Persistent task state |
| `.global_memory.md` | System | Evolution only | Cross-task knowledge |
| `.taskgroup_memory/<name>.md` | Group | Driver (auto) + final review | Structured ledger + failure learnings (see 9.3) |

### 9.2 History & Review Files

| File | Scope | Writers | Purpose |
|------|-------|---------|---------|
| `.history.md` | Task | Driver (auto) | Full verbose execution log |
| `.history_index.md` | Task | Rank -1 model | Auto-generated outline |
| `.suggestion.md` | Task | Final review (highest model) | Conclusion + task/system suggestions |
| `.global_history.md` | System | Driver + evolution | Task runs + evolution changes |
| `.global_suggestion.md` | System | Evolution suggest mode | Human help requests |

### 9.3 TaskGroup Memory

Opt-in cross-task memory for related tasks. Enable with `TaskGroup: name` in task metadata.

**Storage**: `F/run/.taskgroup_memory/<name>.md` — append-only, one file per group.

**Two layers in one file:**

1. **Structured ledger** (always written, success or failure):
   ```
   ---
   **[2026-04-10 15:22]**
   Task: lhco_train_20260410 | PASSED | gemma4 | 111m 8iter
   ```
   Auto-generated by the driver after every task in the group completes. Downstream tasks see upstream pass/fail status without relying on agent-written memory.

2. **Domain learnings** (failure only, appended to the ledger entry):
   ```
   ---
   **[2026-04-10 15:58]**
   Task: lhco_blackbox_20260410 | FAILED | gemma4 | 35m 40iter
   - Download exceeded bash timeout, need pre-staged data
   - CWoLa model exists but BB1 features missing
   ```
   Extracted from the final review's `## TaskGroup learning` section. Only on failure — success learnings omitted to avoid leaking solutions to parallel sibling tasks.

**Injection**: Read at SAM start, appended to the worker's context as `TaskGroup Experience (<name>)`. Independent of `NoMemory` (NoMemory suppresses global memory but not TaskGroup memory).

**Use cases:**
- **Sequential tasks** (train → eval): downstream sees "upstream FAILED" and can abort or flag results as diagnostic instead of loading a tainted model blindly.
- **Parallel tasks** (FW design variants): siblings share failure knowledge ("this Verilog pattern doesn't synthesize") without leaking working solutions.

**Implementation**: `_write_taskgroup_memory()` in driver.py. The ledger line is written unconditionally; the domain learning extraction is gated on `not success`.

### 9.4 History Events

SAM_START, PRESCAN, ITERATION, CHECKPOINT, TOOL_CALL, TOOL_RESULT,
DONE_CLAIMED, REVIEW_START, REVIEW_VERDICT_PASS/FAIL, REVIEW_DECISION,
REVIEW_REJECTED, REVIEW_FALLBACK, NUDGE, NUDGE_LIMIT, API_ERROR,
ERROR_LIMIT, JSON_ERROR, MODEL_CHANGE, RANK_CHANGE, THINKING_ENABLED,
WALL_LIMIT, DELAY_PAUSE, DELAY_RESUME, RETRY, REFLECT_START,
REFLECT_DIAGNOSIS, SAM_VERIFIED, SAM_DONE_NO_EXPECT, LOOP_EXHAUSTED,
MAX_REVIEW_FAILURES, TASK_START, TASK_END, EVOLVE_START, EVOLVE_COMPLETE

---

## 10. Recovery Paths

### 10.1 Done → Review FAIL

```
done → review PASS → return (success)
done → review FAIL → retry (up to MAX_RETRIES)
     → MAX_RETRIES → reflect → return UNVERIFIED
```

### 10.2 Loop Exhausted → Review Triage

```
MAX_ITERATIONS or WALL_LIMIT → review(failed)
  → delay: pause N seconds, resume, re-run
  → retry: update memory + model control + re-run
  → reflect: diagnose, return REFLECTION

MAX_RECOVERY = 3 prevents infinite delay/retry recursion
```

### 10.3 Model Control on Retry

```
Review decision:     Driver action:
(nothing)          → same model, same rank
exclude_model      → next model at same rank
suggested_rank: N  → best model at rank N
enable_thinking    → toggle thinking on current model
```

---

## 11. Evolution System

### 11.1 Three Modes

| Mode | Can write | Purpose |
|------|-----------|---------|
| `suggest` | `.global_suggestion.md` | Read-only analysis, human help requests |
| `code` | `driver.py` | Tune system prompts, constants |
| `model` | `gateway.rank.yaml` | Adjust ranks ±1, budgets, blacklist |

All modes read+write `.global_memory.md` and append `.global_history.md`.

### 11.2 history_stats Tool

Summarizes history without loading full text. Returns: event counts, models used, ranks seen, success/fail rates. Evolution reads this first, then dives into details with `read_file` offset/limit.

### 11.3 Safety

- `write_file` path canonicalized with `os.path.realpath()` before comparison
- Each mode restricted to specific writable paths
- `suggest` mode cannot write to driver.py or rank.yaml

---

## 12. Benchmark Suite (Sam/bench.sh)

Independent benchmark harness for measuring model performance and validating
system changes. Lives in `Sam/`, separate from evolution.

### Modes

| Mode | Purpose |
|------|---------|
| `phase1` | Round-robin all eligible models per rank, 10 reps. Generate `phase1_summary.json`. |
| `phase2` | Run best (work, control) models 3 reps each for validation. |
| `custom <list> <work> <control> <reps>` | Run a fixed (work, control) pair on a custom task list. |
| `prepare` | Check that `_tm` (task-maker) variants have generated `top.md`. |

### Isolation

The benchmark runs with `ISOLATION_MODE=1` so each run gets a fresh
`F/iso_runs/<id>/run/` directory (in `$TMPDIR` for tmpfs speed).
Global memory is not shared across benchmark runs.

### Concurrency

`BENCH_PARALLEL=N` background jobs with a file-based semaphore
(`bench_results/.running/`). Per-task `BENCH_TIMEOUT` (default 30min)
hard-kills runaway tasks. The orchestrator passes `</dev/null`
to background jobs to prevent stdin inheritance breaking the
`while read` loop.

### Task suites

- **`bench_tasks.txt`** — 10 task types × 3 versions (normal/simple/tm) for the
  capability matrix (logic, debug, data pipeline, env discover, shortcut,
  error adapt, multifile, token economy, env setup, algo design).
- **`bench_tasks_agentic.txt`** — 7 SWE-bench/MLE/RepoBench-style agentic tasks
  for end-to-end validation (swe_bench, mle_lite, lib_glue, build_fix,
  repo_context, binary_parse, cli_tool).

### Validation results (2026-04)

- **Lean stack** (`llama4-scout` worker + `qwen3-coder` control): 100% success
  on all 21 agentic-suite runs (7 tasks × 3 reps), 0 failures.
- **Claude stack** (`claude-opus` worker + `claude-haiku` control): 100% success
  on the same suite, ~3.5× faster wall time.
- Confirms the lean stack as production-ready for routine tasks.

---

## 13. Task Metadata

All optional, all hints for prescan (overridable by review on retry):

| Field | Format | Default | Purpose |
|-------|--------|---------|---------|
| `Rank` | `Rank: N` | prescan decides | Task difficulty (0-5), controls worker model selection |
| `Timeout` | `Timeout: N` | per-rank | Wall limit seconds (own time) |
| `BashTime` | `BashTime: N` | MAX_BASH_TIME (300) | Per-bash-call cap (-1 = none) |
| `ThinkTime` | `ThinkTime: N` | per-rank WALL_LIMIT | LLM time cap per attempt (-1 = none). Propagates to subtasks. |
| `Skills` | `Skills: a, b` | prescan decides | Comma-separated skill names |
| `ForceModel` | `ForceModel: name` | (none) | Pin worker to exact model name (bypasses rank selection) |
| `ControlModel` | `ControlModel: name or N` | highest | Pin prescan/review/reflect model. Name = exact model, N = highest at-or-below rank N. Rank < 0 models use text-only review path. |
| `Thinking` | `Thinking: N` | off | Force thinking mode with budget N tokens from start (not just on retry) |
| `NoMemory` | `NoMemory: on\|off` | off | When on, task does not read global memory and does not append to global history (clean-room run, no cross-task feedback). Does NOT affect TaskGroup memory. |
| `TaskGroup` | `TaskGroup: name` | (none) | Opt-in cross-task memory with structured ledger. See **TaskGroup Memory** below. Independent of NoMemory. |
| `CommonHome` | `CommonHome: ro\|rw\|disable` | rw | Mount F/home → /home. rw = persistent writes (default). ro = read-only (tmpfs absorbs writes to image paths but NOT to bind mounts — ro /home will error on writes). disable = no mount. Portal symlinks ~/.local and ~/.cache to /tmp to prevent cross-run pollution. |
| `CommonStorage` | `CommonStorage: rw\|ro\|disable` | rw | Mount F/mnt → /mnt. rw = read/write. ro = read-only. disable = no mount. |
| `GPU` | `GPU: no\|local\|1-4\|all\|ALL\|slurm\|on` | no | Controls `--nv` and `CUDA_VISIBLE_DEVICES`. See §6.5. |
| `Slurm` | `Slurm: off\|on` | off | Controls sbatch bind into container. `off` = hard safety barrier. `on` implies `BashTime: -1`. `GPU: slurm` implies `Slurm: on`. |

### GPU / Slurm Routing

`F/portal.py` parses `GPU` + `Slurm` from task metadata BEFORE the apptainer call.
Two orthogonal decisions:

**1. GPU** (`--nv` + `CUDA_VISIBLE_DEVICES`):

| GPU | Local GPU? | `--nv` | CUDA_VISIBLE_DEVICES | Slurm default |
|-----|-----------|--------|---------------------|---------------|
| no | any | no | — | off |
| local / 1-4 | yes | yes | Auto-pin N free | off |
| local / 1-4 | no | **ERROR** | — | — |
| all | yes | yes | All host-visible | off |
| ALL | yes | yes | ALL physical (**debug!**) | off |
| slurm | yes | yes | Auto-pin 1 free | **on** |
| slurm | no | no | — | **on** |
| on | yes | yes | Auto-pin 1 free | off |
| on | no | no | — | off |

Rule: **never disable usable local GPUs**. If free and available, always map them.
`GPU: slurm` + local GPU = agent has local GPU for testing AND sbatch for production.

**2. Slurm** (sbatch bind):

| Slurm (final) | Action |
|---------------|--------|
| off | Don't bind sbatch — **hard safety barrier** |
| on | Bind sbatch + SLURM libs, imply BashTime: -1 |

The outer **never** auto-submits sbatch. Agent + skill decide when/how to submit.

**Auto-pin logic** (`portal.resolve_gpu` / `portal._select_gpus`):
1. Usable set: respect host `CUDA_VISIBLE_DEVICES`, else all physical
2. Free GPUs: no running compute processes (`nvidia-smi --query-compute-apps`)
3. Pick first N free, propagate via `--env CUDA_VISIBLE_DEVICES`
4. Already pinned to exact count → leave unchanged
5. Fewer free than requested: `GPU_ALLOW_OVERUSE=true` passes all (warn), `false` errors
6. Overuse from parallel agents: known issue, deferred

Per-job env overrides (benchmarks / parallel runs):

| Env var | Effect |
|---------|--------|
| `GPU_FORCE=<value>` | Override `GPU` metadata |
| `SLURM_FORCE=off\|on` | Override `Slurm` metadata |
| `GPU_ALLOW_OVERUSE=true\|false` | Allow fewer free GPUs than requested (default: false) |
| `CUDA_VISIBLE_DEVICES=X,Y` | Pre-pin GPUs (skips auto-pin if count matches) |

---

## 14. Configuration

### ENV.sh Parameters

| Variable | Default | Purpose |
|----------|---------|---------|
| `GATEWAY_PORT` | UID-derived | LiteLLM gateway port |
| `FALLBACK_HIGHEST` | (required) | Fallback model when rank system unavailable (prescan, review, evolution, ask) |
| `FALLBACK_WORKING` | (required) | Fallback model for worker agents when rank system unavailable |
| `SCIFI_MODEL` | (required) | Fixed model group for SciFi (outside container, no Pam) |
| `MAX_ITERATIONS` | 50 | Absolute per-SAM iteration cap (overridden per-rank) |
| `CHECKPOINT_EVERY` | 5 | Re-grounding interval |
| `MAX_CONTEXT` | 80 | Max messages before trimming |
| `MAX_DEPTH` | 5 | Max subtask nesting |
| `MAX_REVIEW_ITER` | 10 | Review agent iteration limit |
| `MAX_REFLECT_ITER` | 15 | Reflection agent iteration limit |
| `MAX_RETRIES` | 3 | Review rejections before reflect |
| `MAX_PARALLEL_AGENTS` | 4 | Concurrent subtask limit |
| `MAX_BASH_TIME` | 300 | Global bash timeout cap |
| `WALL_LIMIT_PER_RANK` | 60,120,240,300,360,600 | Per-rank LLM-only wall limit (excludes bash) |
| `ITER_LIMIT_PER_RANK` | 10,20,30,30,50,50 | Per-rank iteration cap |
| `TOTAL_WALL_PER_RANK` | 1800,1800,1800,1800,1800,1800 | Per-rank total wall limit (incl. bash) |
| `SKILLS_DIR` | ./skills | Skill library path |
| `MAX_EVOLVE_ITER` | 20 | Evolution iteration limit |

### gateway.rank.yaml Fields

| Field | Required | Purpose |
|-------|----------|---------|
| `rank` | yes | Model tier (-2 to N, dynamic) |
| `name` | yes | Model name (matches gateway config) |
| `budget` | yes | Max calls per run (-1 unlimited, 0 blacklist) |
| `thinkable` | no | Supports extended thinking (default false) |
| `max_thinking_budget` | no | Max thinking tokens |
| `max_tokens` | no | Max output tokens |
| `connection_max` | no | Global connection error threshold |

### gateway.rank.yaml Auto-generation

If `gateway.rank.yaml` is missing at bootstrap time, Pam bootstrap auto-generates
it by scanning `gateway.model.yaml` for model names. All models get:
- `rank: 0` (driver default)
- `budget: -1` (unlimited, fail-safe)
- `thinkable: false` (safe default)

Models are sorted alphabetically in the YAML. Since the driver uses **config order**
(first model in list at a given rank wins), alphabetical sort ensures "claude-*"
models are picked first when multiple models share the same rank.

This auto-generated config is functional but suboptimal. Run `SciF MAINTAIN`
(evolution model mode) to assign proper ranks based on observed performance.

---

## 15. Environment Flow

How configuration flows from user → ENV.sh → shell wrappers → container:

```
ENV.sh (host)
  │  defines: BASEDIR, APPTAINER, SIF, OVERLAY, FDIR, TASKS_SRC,
  │           SKILLS_SRC, RANK_SRC, GATEWAY_PORT, FALLBACK_HIGHEST,
  │           FALLBACK_WORKING, SCIFI_MODEL, CAM_DIR, ...
  │
  ├─ SciF sources ENV.sh (the ONLY script that sources it)
  │    │
  │    └─ calls individual .sh scripts which CHECK env vars (never source)
  │         │
  │         └─ --env flags pass selected vars INTO the container
  │              │
  │              └─ Python code reads os.environ[...] or os.environ.get(...)
  │
  └─ SciFi reads SCIFI_MODEL from os.environ (set by ENV.sh via SciF)
```

### ENV.sh → container env var mapping

`portal.py` selects which ENV.sh variables to pass through via `--env`.
`--cleanenv` strips everything else — the container sees ONLY these:

| Variable | Set in ENV.sh | Passed by | Read by (inside container) |
|----------|--------------|-----------|---------------------------|
| `GATEWAY_URL` | derived from `GATEWAY_PORT` | portal.py (driver, evolution, ask profiles) | All Python agents (API calls) |
| `FALLBACK_HIGHEST` | model group name | portal.py (driver, evolution, ask) | driver.py→Pam, evolution.py, ask.py |
| `FALLBACK_WORKING` | model group name | portal.py (driver) | driver.py→Pam |
| `SCIFI_MODEL` | model group name | (not passed — SciFi runs on host) | SciFi (os.environ) |
| `MAX_ITERATIONS` | `50` | portal.py (driver) | driver.py |
| `CHECKPOINT_EVERY` | `5` | portal.py (driver) | driver.py |
| `MAX_CONTEXT` | `80` | portal.py (driver) | driver.py |
| `MAX_DEPTH` | `5` | portal.py (driver) | driver.py |
| `MAX_REVIEW_ITER` | `10` | portal.py (driver) | driver.py |
| `MAX_REFLECT_ITER` | `15` | portal.py (driver) | driver.py |
| `MAX_RETRIES` | `3` | portal.py (driver) | driver.py |
| `MAX_PARALLEL_AGENTS` | `4` | portal.py (driver) | driver.py |
| `MAX_BASH_TIME` | `300` | portal.py (driver) | driver.py |
| `WALL_LIMIT_PER_RANK` | `60,120,240,300,360,600` | portal.py (driver) | driver.py |
| `ITER_LIMIT_PER_RANK` | `10,20,30,40,50,50` | portal.py (driver) | driver.py |
| `TOTAL_WALL_PER_RANK` | `300,600,1200,1800,3600,3600` | portal.py (driver) | driver.py |
| `SKILLS_DIR` | `/srv/skills` | portal.py (driver), task_maker.sh, skill_maker.sh | driver.py, skill_maker.py |
| `MAX_EVOLVE_ITER` | `20` | portal.py (evolution) | evolution.py |
| `CAM_DIR` | `$BASEDIR/Cam` → `/cam` | portal.py (all profiles, conditional) | All Python agents (audit) |

**Note**: `CAM_DIR` is remapped: host `$BASEDIR/Cam` is bound to `/cam` in the container,
and `--env CAM_DIR=/cam` tells Python to write there. If `CAM_DIR` is unset on host,
both the bind and env are skipped — all `_cam()` calls become no-ops.

---

## 16. Container File Structure

### Apptainer isolation model

| Flag | Effect |
|------|--------|
| `--contain` | Minimal `/dev`, empty `/tmp` and `$HOME`. Container sees NO host filesystem. |
| `--cleanenv` | Strips ALL host env vars. Only explicit `--env` vars pass through. |
| `--no-home` | Blocks host `$HOME` from being mounted. `HOME=/home` (mapped from `F/home/`, writable by default). Portal symlinks `~/.local` and `~/.cache` to `/tmp/` to prevent pip --user and cache pollution across runs. |
| `--writable-tmpfs` | RAM-backed writable layer on top of read-only SIF. Lost on exit. Absorbs writes to read-only paths in the container image. Does NOT affect bind mounts (e.g. `/home` bound ro will still error on writes). |
| `--overlay <img>:ro` | Persistent read-only overlay (Python env). `:rw` only during bootstrap install. |
| `--bind src:dst:mode` | Maps specific host path into container. `:ro` or rw (default). |
| `--pwd /path` | Sets initial working directory inside the container. |

**Key principle**: `--no-home` + `--contain` + `--cleanenv` + `--writable-tmpfs` = blank slate with safety net. The container sees ONLY:
1. The SIF filesystem (Rocky Linux base)
2. The overlay (Python env, read-only at runtime)
3. Explicit `--bind` mounts (including F/home → /home, F/mnt → /mnt)
4. Explicit `--env` variables
5. RAM-backed tmpfs overlay (absorbs writes to container image paths, discarded on exit)

**HOME=/home** is bound from `F/home/` (writable by default, CommonHome: rw). Portal
creates symlinks `~/.local → /tmp/.local` and `~/.cache → /tmp/.cache` on container
entry so pip --user installs and caches go to tmpfs (discarded on exit) instead of
polluting the persistent home across runs. SSH keys (`.ssh/`) and git config remain
in the real `/home/` and persist.

Nothing from the host leaks in unless explicitly allowed.

### Host file structure (outside container)

```
$BASEDIR/                           ← ENV.sh sets this
├── ENV.sh                          ← All configuration
├── SciF                            ← Scripted entry point (sources ENV.sh)
├── SciFi                           ← Intelligent entry point (stdlib Python)
├── F/
│   ├── driver.py                   ← SAM driver (core engine)
│   ├── task_parser.py              ← Deterministic task .md parser
│   ├── portal.py                   ← Unified container launcher
│   ├── evolution.py                ← System evolution
│   ├── ask.py                      ← Interactive agent
│   ├── F.overlay.img               ← Python env overlay (2GB ext2)
│   ├── F.design.md, F.usage.md     ← System documentation
│   ├── home/                       ← Common home (bind → /home, shared across tasks)
│   │   └── .ssh/                   ← SSH keys for git checkout etc.
│   ├── mnt/                        ← Common storage (bind → /mnt, shared across tasks)
│   ├── run/                        ← Global state (persistent)
│   │   ├── .global_memory.md
│   │   ├── .global_history.md
│   │   └── .global_suggestion.md
│   └── tasks/                      ← Completed task runs (persistent)
│       └── task_name_YYYYMMDDHHMMSS/
├── Kam/                            ← Container images
│   └── rl9_micromamba_0.sif        ← Base SIF (L0)
├── Sam/
│   ├── task_maker.py, task_maker.sh
│   ├── tasks/                      ← Task source definitions
│   └── task_template/
├── Nam/
│   ├── skill_maker.py, skill_maker.sh
│   └── skills/                     ← Skill library
├── Pam/
│   ├── pam.py                      ← Model selection (bound into all containers)
│   ├── gateway.sh, gateway.debug.sh
│   ├── gateway.sif                 ← LiteLLM container
│   ├── gateway.rank.yaml           ← Model ranking
│   └── gateway.model.yaml         ← LiteLLM config (keys via env vars from ENV.sh)
└── Cam/                            ← Audit logs (never deleted)
    └── *.jsonl
```

### Container file structure (inside container, per script)

#### portal.py driver profile → `/srv` namespace

```
/srv/                               ← --pwd /srv
├── driver.py                       ← bind $FDIR/driver.py :ro
├── task_parser.py                  ← bind $FDIR/task_parser.py :ro
├── pam.py                          ← bind $BASEDIR/Pam/pam.py :ro
├── gateway.rank.yaml               ← bind $RANK_SRC :ro
├── skills/                         ← bind $SKILLS_SRC :ro
├── run/                            ← bind $FDIR/run :rw  (PERSISTENT)
│   ├── .global_memory.md
│   ├── .global_history.md
│   └── .global_suggestion.md
├── <task_name>/                    ← bind $RUN_DIR :rw  (PERSISTENT, agent's ./)
│   ├── top.md
│   ├── .memory.md, .history.md, ...
│   └── output files written by agent
├── /home/                          ← bind $FDIR/home (CommonHome: ro|rw|disable)
│   └── .ssh/                       ← SSH keys, git config (shared across tasks)
├── /mnt/                           ← bind $FDIR/mnt (CommonStorage: rw|ro|disable)
│   └── (shared data, reusable envs, datasets)
├── /cam/                           ← bind $CAM_DIR :rw  (PERSISTENT, conditional)
├── /tmp/                           ← bind fresh `$TMPDIR/scif_tmp_*` :rw (per-run, cleaned on exit)
├── /usr/bin/sbatch,...             ← bind host SLURM :ro
└── (everything else)               ← SIF + overlay (read-only) + writable-tmpfs (disposable)
```

**Writable paths** (agent perspective):
- `./` (task dir) — persistent, task-specific outputs go here
- `/mnt/` — persistent shared storage (if CommonStorage != disable)
- `/home/` — depends on CommonHome: ro = writes go to tmpfs (discarded), rw = persistent
- `/tmp/` — writable, per-run host dir under `$TMPDIR` (isolated between concurrent runs, removed when the container exits)
- Everything else — writable-tmpfs absorbs writes silently (discarded on exit)

#### portal.py evolution profile → `/srv` namespace

```
/srv/                               ← --pwd /srv
├── evolution.py                    ← bind :ro
├── driver.py                       ← bind :rw  (code mode writes)
├── task_parser.py                  ← bind :ro
├── pam.py                          ← bind :ro
├── gateway.rank.yaml               ← bind :rw  (model mode writes)
├── skills/                         ← bind :ro
├── run/                            ← bind :rw  (writes memory, history, suggestion)
├── tasks/                          ← bind :ro  (reads completed tasks)
│   └── task_name_*/
└── /cam/                           ← bind :rw  (conditional)
```

#### portal.py ask profile → `/srv` namespace (fully read-only except Cam)

```
/srv/                               ← --pwd /srv
├── ask.py                          ← bind :ro
├── F.design.md, F.usage.md         ← bind :ro  (agent reads for context)
├── driver.py, evolution.py, pam.py ← bind :ro  (reference)
├── gateway.rank.yaml, ENV.sh       ← bind :ro  (reference)
├── run/                            ← bind :ro
├── tasks/                          ← bind :ro
├── skills/                         ← bind :ro
├── task_defs/                      ← bind $TASKS_SRC :ro
└── /cam/                           ← bind :rw  (only writable path)
```

#### Sam/task_maker.sh, Nam/skill_maker.sh → `/srv` namespace

```
/srv/                               ← --pwd /srv
├── Sam/ or Nam/                    ← bind $BASEDIR/Sam or Nam :rw (host dir)
│   ├── task_maker.py or skill_maker.py
│   ├── task_template/ or skill_template/
│   └── tasks/ or skills/           ← maker writes output here
├── lib/                            ← virtual (no host mapping)
│   ├── driver.py                   ← bind $FDIR/driver.py :ro
│   ├── pam.py                      ← bind $BASEDIR/Pam/pam.py :ro
│   └── gateway.rank.yaml           ← bind $RANK_SRC :ro
├── skills/                         ← bind $SKILLS_SRC :ro
└── /cam/                           ← bind :rw (conditional)
```

**Key rule**: imports (`driver.py`, `gateway.rank.yaml`) go to `/srv/lib/` (virtual),
NOT into the host-mapped `Sam/` or `Nam/` directory. This prevents Apptainer from
creating stub mount-point files on the host filesystem.

#### Pam/gateway.sh → `/app` namespace

```
/app/                               ← container default (LiteLLM)
├── config.yaml                     ← bind gateway.model.yaml :rw
└── (LiteLLM code from SIF)
```

Minimal — gateway only needs its config file.

### What persists vs what's disposable

| Path (in container) | Persists? | Why |
|---------------------|-----------|-----|
| `/srv/<task>/` (= `./`) | Yes | Bound to `$RUN_DIR` — task outputs, new envs |
| `/srv/run/` | Yes | Bound to `$FDIR/run` — global memory, history |
| `/mnt/` | Yes (if CommonStorage != disable) | Bound to `$FDIR/mnt` — shared storage, reusable envs |
| `/home/` | Depends | CommonHome: rw = persists to `$FDIR/home`. ro = tmpfs absorbs (discarded). |
| `/cam/` | Yes | Bound to `$CAM_DIR` — audit logs |
| `/srv/gateway.rank.yaml` | Yes (evolution only) | Bound to `$RANK_SRC` — model config |
| `/srv/driver.py` | Yes (evolution code only) | Bound to `$FDIR/driver.py` rw |
| `/srv/Sam/` or `/srv/Nam/` (makers) | Yes | Bound to `$BASEDIR/Sam` or `Nam` — writes output |
| `/tmp/` | No | Per-run fresh dir under `$TMPDIR` (`scif_tmp_*`) — removed by portal.py after the container exits |
| Everything else | No | writable-tmpfs — RAM-backed, lost on container exit |

---

## 17. Entry Points

### Three-layer entry point design

| Layer | Entry | Nature | Purpose |
|-------|-------|--------|---------|
| `F/*.sh` | Definite | Bash scripts | Each does one specific operation |
| `SciF` | Unified | Bash dispatcher | Routes commands, auto-starts gateway, validates |
| `SciFi` | Flexible | Python + LLM | Understands intent, suggests SciF commands |

### SciF commands

```
Lifecycle:   BOOTSTRAP, START, END, RESET, MAINTAIN, STATUS
Work:        RUN <task>, MAKE <desc.md>, MAKE <desc.md> --skill <name>
Agent:       ASK (multi-turn), EVOLVE [suggest|model|code]
Guide:       SciFi <question> (one-shot, read-only)
```

### Bootstrap dependency chain

```
  Apptainer binary exists
    ↓
  Kam: container SIF (rl9_micromamba_0.sif)
    ↓
  .secret.sh: at least one API key set (sourced by ENV.sh)
    ↓
  Pam: gateway.model.yaml references keys via os.environ/
    ↓
  Pam: gateway.sif (built from precursor + gateway.def with %startscript)
    ↓
  Gateway can start → SciFi LLM mode becomes available
    ↓
  F: overlay + Python env (openai, requests)
    ↓
  System ready → SciF START
```

SciF (bash) works at any stage. SciFi works in two modes:
- **Pre-gateway**: rule-based diagnosis (checks files, suggests fixes)
- **Post-gateway**: LLM-driven (reads F.usage.md, suggests SciF commands)

### SciFi safety model

LLM calls retry once on timeout (30s per attempt, 60s worst case). The decision
call is read-only — safe to retry with no side effects.

Command routing uses a **two-layer fence**:

1. **Fence floor**: hard-coded minimum restrictiveness per command type
   (`run` < `interactive` < `suggest`). E.g. RESET is always at least `suggest`.
2. **LLM intent**: the LLM classifies the user's intent independently.
3. **Final action** = `max(fence, LLM)` — the more restrictive wins.

The fence can never be lowered by the LLM (prevents prompt injection from
downgrading a `suggest` command to `run`). The LLM can raise it (e.g. flag
suspicious input as `suggest` even for a normally-direct command like RUN).
Shell metacharacters (`;|&\`$(`) are rejected before classification.

### Bootstrap sequence (SciF BOOTSTRAP)

Each module bootstrap is self-contained: checks its own preconditions,
builds its artifacts, verifies output. BOOTSTRAP.sh just calls them
in order and stops on first failure.

```
[1/4] Pam bootstrap (gateway.bootstrap.sh)
  ├─ Check: APPTAINER exists + executable
  ├─ Check: gateway.model.yaml exists + no <SETME>
  ├─ Check: at least one API key set in .secret.sh (sourced by ENV.sh)
  ├─ Auto-generate gateway.rank.yaml if missing
  ├─ Pull precursor SIF (skip if exists)
  ├─ Build gateway.sif from gateway.def (skip if exists)
  ├─ Verify: gateway.sif created
  ├─ Start temp gateway (gateway.debug.sh backgrounded)
  ├─ Health check + model count
  └─ (temp gateway killed on exit via trap)

[2/4] Kam bootstrap (rl9_micromamba.bootstrap.sh 0)
  ├─ Check: BASEDIR set, def file exists
  ├─ Skip if SIF exists
  ├─ Build L0 from rl9_micromamba_0.def
  └─ Verify: SIF created

[3/4] F bootstrap (F.bootstrap.sh)
  ├─ Check: SIF exists (Kam done first)
  ├─ Create 2GB overlay (skip if exists)
  ├─ Install Python 3.12 + openai + requests
  └─ Verify: import openai succeeds

[4/4] Smoke test
  ├─ Run test_hello task
  └─ Verify PASS from review
```
