---
Rank: 0
BashTime: -1
NoMemory: on
---

# BashTime Smoke Test

## Context
Test BashTime: -1 propagation. The agent should be able to run long bash commands.

## Todo
1. Run `sleep 5 && echo done` with timeout=120 and write the output to result.txt

## Expect
- result.txt exists with "done"
