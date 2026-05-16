---
Rank: 1
NoMemory: on
_System: PRESCAN_MODE=llm
---

# Prescan Test -- LLM Subtask Dependency Detection

## Context
This task has three subtask .md files that must run in order.
The LLM prescan should read them and detect the dependency chain:
  setup.md -> compute.md -> verify.md

## Todo
1. Dispatch all subtasks
2. Confirm final output

## Expect
- `result.txt` exists and contains "6" (factorial of 3)
- `status.txt` exists and contains "VERIFIED"
