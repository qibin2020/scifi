---
Rank: 1
NoMemory: on
---

# Context Compaction Stress Test

## Context
This task generates deliberately long bash output across multiple iterations
to verify that old tool results are compacted without losing critical info.
The agent must track results across iterations despite compaction.

## Todo
1. Generate a 200-line numbered list: `seq 1 200 > numbers.txt`
2. Print all 200 lines via cat (long output — will be truncated)
3. Compute the sum: `awk '{s+=$1} END {print s}' numbers.txt` (expect 20100)
4. Generate another 200-line file with squares: `awk '{print $1*$1}' numbers.txt > squares.txt`
5. Print all squares (another long output)
6. Compute sum of squares: `awk '{s+=$1} END {print s}' squares.txt` (expect 2686700)
7. Write both sums to `output.txt`: "sum=20100 sumsq=2686700"

## Expect
- `output.txt` exists and contains "sum=20100 sumsq=2686700"
