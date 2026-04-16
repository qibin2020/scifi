---
Rank: 1
NoMemory: on
---

# Medium Smoke Test

## Context
Test that non-trivial tasks still run post-processing (index + final review).

## Todo
1. Write 5 lines of "line N" to multi.txt (N=1..5)
2. Read multi.txt and reverse the lines, write to reversed.txt
3. Use bash to count words in reversed.txt, save to count.txt

## Expect
- multi.txt exists with 5 lines
- reversed.txt exists with 5 lines in reversed order
- count.txt contains an integer
