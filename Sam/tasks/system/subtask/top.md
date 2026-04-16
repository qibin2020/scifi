---
Rank: 1
NoMemory: on
---

# Portal Test — Subtask Dispatch

## Context
Orchestrator task: delegate to `work.md` subtask and verify its output.

## Todo
1. Dispatch `work.md` as a subtask via subagent tool
2. After it completes, verify `sub_output.txt` exists
3. Write "orchestrator done" to `output.txt`

## Expect
- `sub_output.txt` exists and contains "subtask hello"
- `output.txt` exists and contains "orchestrator done"
