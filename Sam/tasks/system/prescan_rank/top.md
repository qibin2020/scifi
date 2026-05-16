---
NoMemory: on
---

# Prescan Test -- Rank Estimation

## Context
This task has NO Rank: declared. The prescan must assign one.

In metadata mode, DEFAULT_RANK should be used.
In LLM mode, the prescan should estimate difficulty from the content below.

This is a trivial task (should be rank 0-1).

## Todo
1. Write "hello" to `output.txt`

## Expect
- `output.txt` exists and contains "hello"
