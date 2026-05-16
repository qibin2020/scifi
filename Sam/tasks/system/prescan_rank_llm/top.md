---
NoMemory: on
_System: PRESCAN_MODE=llm
---

# Prescan Test -- LLM Rank Estimation

## Context
This task has NO Rank: declared and forces PRESCAN_MODE=llm via _System.
The LLM prescan should read this content and estimate difficulty.

This is a trivial task (should be rank 0-1).

## Todo
1. Write "hello" to `output.txt`

## Expect
- `output.txt` exists and contains "hello"
