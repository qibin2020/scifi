---
Rank: 1
Timeout: 300
CommonStorage: ro
NoMemory: on
---

# Read a shared seed from /mnt/sci_shared

## Context

The shared workspace `/mnt/sci_shared/` is pre-populated by the suite setup. It
contains `seed.txt` with simple `key=value` lines. Read it, parse the lines,
and write `parsed.json` with a JSON object mapping each key to its value.

## Todo

1. Read `/mnt/sci_shared/seed.txt`
2. For each line of the form `key=value`, add it to a dict (skip comment-style lines like `seed_id=...` if you wish, OR include all of them — your choice, just be consistent)
3. Write `parsed.json` with the dict

## Expect

- `parsed.json` exists, valid JSON
- The JSON has at least the keys `alpha`, `beta`, `gamma` from the seed file
