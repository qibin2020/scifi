---
Rank: 1
NoMemory: on
---

# h5py round-trip

## Todo
Write `h5_roundtrip.py` that creates a (100,3) float + (100,) string label in `data.h5` using h5py. Read back. Write `verify.json` with the shapes and `ok:true`.

## Expect
- data.h5 exists > 1 KB
- verify.json has "ok": true
