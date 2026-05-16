---
Rank: 1
NoMemory: on
---

# Prescan Test -- Skill Selection

## Context
This task requires Python with numpy but does NOT declare Skills:.
The prescan (LLM mode) should detect from the content that an env skill
is needed and select one (e.g. common_env or temp_env).

In metadata mode, the default env skill is auto-injected.
In LLM mode, the prescan should explicitly select the right env skill.

## Todo
1. Install numpy if not available
2. Run: python3 -c "import numpy; print(numpy.array([1,2,3]).sum())"
3. Write the output ("6") to `output.txt`

## Expect
- `output.txt` exists and contains "6"
