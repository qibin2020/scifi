---
Rank: 1
NoMemory: on
---

# Prescan Test -- Subtask Dependency Detection

## Context
This task has three subtask .md files that must run in a specific order.
The prescan (LLM mode) should read them and detect the dependency chain:
  setup.md -> compute.md -> verify.md

In metadata mode, they run as independent (no ordering).
In LLM mode, the prescan should detect depends_on from content.

## Todo
1. Dispatch all subtasks
2. Confirm final output

## Expect
- `result.txt` exists and contains "6" (factorial of 3)
