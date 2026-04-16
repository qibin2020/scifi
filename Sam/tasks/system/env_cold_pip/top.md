---
Rank: 0
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# Cold Start — Conda + pip install

## Context
Test that the common_env skill handles pip packages in shared environments.

## Todo
1. Use the common_env skill to create a shared env with python, then pip install requests
2. Verify requests imports successfully
3. Write the requests version to `result.txt`

## Expect
- `result.txt` exists and contains a version string
- The environment is at /mnt/sci_envs/ (not local ./)
