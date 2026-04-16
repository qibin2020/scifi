---
Rank: 2
Timeout: 600
CommonStorage: rw
NoMemory: on
---

# /mnt persistent derived state

## Context

Read a pre-seeded dataset from `/mnt/sci_shared/data.csv` (200 rows), process
it, and write a derived directory under `/mnt/sci_shared/derived/` named after
this task run. Demonstrate the cross-run persistence pattern that nu2flows uses.

## Todo

1. Read `/mnt/sci_shared/data.csv` (columns: `sample_id, x, y, label`)
2. Compute the mean of `y` per `label` (`high` and `low`)
3. If `/mnt/sci_shared/derived/` is writable, create a `<unique_run_id>/` subdir there. Otherwise write everything to the task root. (use a timestamp or your task run id)
4. Inside that directory, write:
   - `summary.json` with `{"mean_y_high": <float>, "mean_y_low": <float>, "n_high": <int>, "n_low": <int>}`
   - `manifest.txt` listing the source file path and the derived files

5. Also write a copy of `summary.json` into the task root directory so the reviewer can find it without searching `/mnt`.

## Expect

- A `summary.json` exists in the task root with `mean_y_high` and `mean_y_low` keys; both are positive floats
- If `/mnt/sci_shared/derived/` was writable, `summary.json` + `manifest.txt` exist there too
