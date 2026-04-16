---
Rank: 3
Timeout: 900
NoMemory: on
---

# Paper to code: implement softmax from a paper reference

## Context

Fetch a known reference page that describes a simple ML primitive, implement
it in Python from scratch (no `import torch.nn.functional`), test it, and write
a notes.md linking the implementation back to the source.

The target primitive is the **softmax** function. Use the Wikipedia page as the
source: `https://en.wikipedia.org/wiki/Softmax_function`.

## Todo

1. Fetch the Wikipedia page text. Identify the standard softmax formula.
2. Write `softmax.py` containing a function `def softmax(x: list[float]) -> list[float]` that implements the numerically stable softmax (subtract max for stability). NO PyTorch / NumPy required (pure Python is fine; numpy is allowed).
3. Write `test_softmax.py` with at least 3 pytest tests:
   - softmax of `[0, 0, 0]` is `[1/3, 1/3, 1/3]` (within 1e-6)
   - softmax outputs sum to 1 (within 1e-6)
   - softmax of large values like `[1000, 1001, 1002]` does not overflow
4. Run the tests. They must all pass.
5. Write `notes.md` linking the source URL and quoting the formula in plain text.

## Expect

- `softmax.py` exists
- `test_softmax.py` exists with at least 3 tests
- All tests pass (pytest exit 0)
- `notes.md` exists, contains the URL `https://en.wikipedia.org/wiki/Softmax_function`
