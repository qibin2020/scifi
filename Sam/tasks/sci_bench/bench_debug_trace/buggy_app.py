"""Data processor that computes basic statistics on a list of numbers.

Contains 3 bugs:
  Bug 1: Off-by-one in the loop (skips first element)
  Bug 2: Wrong variable name (total vs sum_val)
  Bug 3: Missing import (collections.Counter)
"""


def compute_stats(data):
    """Return a dict with mean, median, and mode for *data*.

    Parameters
    ----------
    data : list[int | float]
        Non-empty list of numbers.

    Returns
    -------
    dict with keys "mean", "median", "mode".
    """
    if not data:
        return {"mean": 0, "median": 0, "mode": 0}

    # --- mean ---
    sum_val = 0
    # BUG 1: should be range(len(data)), not range(1, len(data))
    for i in range(1, len(data)):
        sum_val += data[i]
    # BUG 2: uses 'total' but the variable is called 'sum_val'
    mean = total / len(data)

    # --- median ---
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n % 2 == 1:
        median = sorted_data[n // 2]
    else:
        median = (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2

    # --- mode ---
    # BUG 3: Counter is used but never imported (from collections import Counter)
    counts = Counter(data)
    mode = counts.most_common(1)[0][0]

    return {"mean": mean, "median": median, "mode": mode}
