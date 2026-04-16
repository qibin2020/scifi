---
Rank: 0
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: ro
---

# Warm Start — Reuse Shared Env

## Context
Test that the common_env skill discovers and reuses existing shared environments.
Do NOT install anything new — only reuse what already exists at /mnt/sci_envs/.

## Todo
1. Use the common_env skill to discover existing environments at /mnt/sci_envs/
2. List all available shared envs and their packages
3. Pick any env that has python, run `python --version`
4. Write the env name and python version to `result.txt`

## Expect
- `result.txt` exists and contains an env name and python version
- No new environment was created (only reused existing)
