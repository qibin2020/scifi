---
Rank: 2
CommonStorage: rw
NoMemory: on
---

# /mnt persist

## Todo
Read `/mnt/sci_shared/data.csv`. Compute mean `y` per `label`. Write `summary.json` to the task root with `mean_y_high` and `mean_y_low`. If `/mnt/sci_shared/derived/` is writable, also write there under a `<run_id>/` subdir with `manifest.txt`.

## Expect
- summary.json in task root with mean_y_high, mean_y_low (positive floats)
- If `/mnt/sci_shared/derived/` was writable, a `summary.json` exists there too
