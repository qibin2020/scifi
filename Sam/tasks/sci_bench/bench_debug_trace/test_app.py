"""Tests for compute_stats in buggy_app.py.

All 5 tests should PASS once the 3 bugs are fixed:
  1. Add ``from collections import Counter`` at the top of buggy_app.py
  2. Change ``range(1, len(data))`` to ``range(len(data))``
  3. Change ``total`` to ``sum_val``
"""

import pytest
from buggy_app import compute_stats


def test_normal_input():
    data = [10, 20, 30, 40, 50]
    result = compute_stats(data)
    assert result["mean"] == 30.0
    assert result["median"] == 30
    assert result["mode"] == 10  # all unique; first encountered


def test_empty_input():
    result = compute_stats([])
    assert result == {"mean": 0, "median": 0, "mode": 0}


def test_single_element():
    result = compute_stats([42])
    assert result["mean"] == 42.0
    assert result["median"] == 42
    assert result["mode"] == 42


def test_duplicates():
    data = [3, 7, 7, 2, 5]
    result = compute_stats(data)
    assert result["mean"] == pytest.approx(4.8)
    assert result["median"] == 5
    assert result["mode"] == 7


def test_negative_numbers():
    data = [-5, -1, -3, -1, -2]
    result = compute_stats(data)
    assert result["mean"] == pytest.approx(-2.4)
    assert result["median"] == -2
    assert result["mode"] == -1
