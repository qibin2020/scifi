---
Rank: 1
Timeout: 600
NoMemory: on
---

# pandas CSV group summary

## Context

Read `seed_csv.csv` (1000 rows, two columns: `category`, `value`), group by
`category`, compute mean and std per group, write `summary.csv` and a bar chart
`bar.png`. The seed file is provided in the task directory.

## Todo

1. Create env: `MAMBA_ROOT_PREFIX=./env micromamba create -n work -c conda-forge python=3.12 -y`
2. Install: `MAMBA_ROOT_PREFIX=./env micromamba run -n work pip install pandas matplotlib`
3. Write `summary.py`:
   - Read `seed_csv.csv` with pandas
   - Group by `category`, aggregate mean and std of `value`
   - Save to `summary.csv` (columns: `category, mean, std`)
   - Plot a bar chart of mean per category to `bar.png`
4. Run: `MAMBA_ROOT_PREFIX=./env micromamba run -n work python summary.py`

## Expect

- `summary.csv` exists with columns `category, mean, std` and 4 data rows (one per category alpha/beta/gamma/delta)
- `bar.png` exists, valid PNG, > 1 KB
