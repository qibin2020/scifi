---
Rank: 2
Timeout: 180
BashTime: 60
Skills: text_stats
ForceModel: gemma4
ControlModel: gemma4
NoMemory: on
---

# Task Title

## Context
Background information the agent needs to understand the task.
Include domain knowledge, constraints, and assumptions.

Sub-tasks are referenced by filename: `subtask_name.md`.
Category naming: `category.specific.md` (e.g., `data.load.md`, `data.clean.md`)
shares experience within the `data` category.

## Todo
1. First step — describe what to do
2. Run sub-task `setup.md` (delegates to a sub-SAM)
3. Use `text_stats` skill on the output file
4. Run `bash` command with timeout: `python train.py` (timeout=120)
5. Write results to `output.txt`

## Expect
- `output.txt` exists with specific content
- All sub-tasks completed successfully
- No errors in the process

<!--
METADATA REFERENCE (inside --- fences, all optional):

Rank: N          — Task difficulty (0=trivial, 4=complex). Determines model.
Timeout: N       — Wall time limit in seconds (own time, excludes subtasks).
BashTime: N      — Max bash call timeout. -1 = no limit (for SLURM/training).
ThinkTime: N     — LLM time cap per attempt. -1 = unlimited.
Skills: a, b     — Comma-separated skill names from Nam/skills/.
GPU: V           — no | local | 1-4 | all | ALL | slurm | on (default: no).
Slurm: V         — off | on (default: off). on implies BashTime: -1.
SlurmHours: N    — Wall hours for SLURM allocation (default 4).
SlurmCpus: N     — CPUs per task in SLURM (default 32).
ForceModel: name — Pin worker to exact model name.
ControlModel: V  — Pin prescan/review model.
Thinking: N      — Force thinking mode with budget N tokens.
NoMemory: on|off — No global memory/history (clean-room). Default: off.
TaskGroup: name  — Cross-task domain memory (independent of NoMemory).
CommonHome: V    — ro | rw | disable (default: ro).
CommonStorage: V — rw | ro | disable (default: rw).
_PrivateKey: V   — Keys starting with _ are driver-private (hidden from agent).

VARIANT NAMING:
  _EX  — Extended (full instructions, rich Context)
  _NL  — Natural Language (minimal, conversational)
  _ST  — Structured (task-maker or domain-refined)
  _RH  — Reduced Heuristic (minimal stripped-down)

TASK FORMAT:
  ---             ← frontmatter open
  Key: Value      ← metadata (parsed by task_parser.py)
  ---             ← frontmatter close
  # Title         ← optional, human-readable name
  ## Context      ← optional, domain knowledge
  ## Todo         ← required, numbered steps
  ## Expect       ← required, verifiable success criteria
-->
