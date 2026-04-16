---
Rank: 0
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# Cold Start — Conda Env with numpy

## Context
Test that the common_env skill creates a shared environment at /mnt/sci_envs/.

## Todo
1. Use the common_env skill to create a new shared env with python and numpy
2. Verify numpy imports successfully
3. Write the numpy version to `result.txt`

## Expect
- `result.txt` exists and contains a numpy version string
- An environment exists under /mnt/sci_envs/ (not under ./)
