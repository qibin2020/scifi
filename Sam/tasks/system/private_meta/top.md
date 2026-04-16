---
Rank: 0
NoMemory: on
BashTime: 30
Timeout: 300
_DriverNote: this key must not appear in agent prompt
---

# Portal Test — Full Sections + Private Metadata

## Context
This task verifies that the agent receives all three content sections
and public metadata, but NOT `_`-prefixed private metadata.

## Todo
1. Write `output.txt` with the text "full sections work"
2. Write `meta_check.txt`: list all metadata keys visible in your initial prompt
   (one key per line, sorted alphabetically)

## Expect
- `output.txt` exists and contains "full sections work"
- `meta_check.txt` exists
- `meta_check.txt` does NOT contain the string `_DriverNote`
- `meta_check.txt` contains the strings `Rank` and `NoMemory`
