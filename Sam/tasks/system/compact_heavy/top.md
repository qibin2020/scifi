---
Rank: 2
NoMemory: on
---

# Heavy Context Compaction Test

## Context
This task requires many iterations with large bash output to test whether
context compaction prevents slowdown over 15+ iterations.

You must build a C program step by step, deliberately introducing and fixing
errors to force multiple compile-fix cycles. Each compilation produces long output.

## Todo
1. Write a C file `matrix.c` that multiplies two 3x3 matrices and prints the result
2. First version: introduce a deliberate off-by-one bug in the loop bounds
3. Compile with `gcc -Wall -Wextra -o matrix matrix.c` (produces warnings)
4. Run `./matrix` — output will be wrong
5. Fix the bug
6. Recompile and run — verify correct output
7. Now extend: add a function to compute the determinant of a 3x3 matrix
8. Compile, run, verify the determinant is correct
9. Add a function to transpose the matrix
10. Compile, run, verify transpose is correct
11. Write final results to `output.txt`: "multiply=OK determinant=OK transpose=OK"

## Expect
- `matrix.c` exists and compiles without errors
- `./matrix` runs and prints correct matrix multiplication
- `output.txt` exists and contains "multiply=OK determinant=OK transpose=OK"
