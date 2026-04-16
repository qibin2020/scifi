---
Rank: 0
NoMemory: on
---

# Edit File Smoke Test

## Context
Verify that the edit_file tool works correctly for in-place string replacement.

## Todo
1. Write a file `data.txt` with the content:
   ```
   name: Alice
   color: red
   count: 3
   ```
2. Use the edit_file tool to change "red" to "blue" in `data.txt`
3. Use the edit_file tool to change "Alice" to "Bob" in `data.txt`
4. Write the final content of `data.txt` to `result.txt`

## Expect
- `data.txt` exists and contains "blue" and "Bob" (not "red" or "Alice")
- `result.txt` exists and matches `data.txt`
