---
Rank: 0
Timeout: 300
NoMemory: on
---

# File operations + manifest

## Context

Pure file-system unit test. Create a small directory tree, write 5 files with
deterministic content, compute the MD5 of each, and write a manifest CSV
listing each file with its size and MD5.

The shell is a standard Linux environment — `python3`, `md5sum`, `mkdir`, and
`printf` are guaranteed available. Execute the full pipeline in a single bash
call (a small python or shell script is ideal); do not pre-check tool
availability with `which`/`pwd`/`ls` between steps.

## Todo

1. Create directory `tree/sub1` and `tree/sub2`
2. Write these 5 files with the **exact** content shown:
   - `tree/a.txt` containing the string `alpha\n`
   - `tree/b.txt` containing `beta\n`
   - `tree/sub1/c.txt` containing `gamma\n`
   - `tree/sub2/d.txt` containing `delta\n`
   - `tree/sub2/e.txt` containing `epsilon\n`
3. Compute MD5 of each file
4. Write `manifest.csv` with columns `path,size,md5` and one row per file. Sort the rows alphabetically by `path`.

## Expect

- `manifest.csv` exists with header `path,size,md5`
- Exactly 5 data rows
- `tree/a.txt` row has size `6` and md5 `9f9f90dbe3e5ee1218c86b8839db1995` (the MD5 of `alpha\n`, where `\n` is a single LF byte 0x0a)
