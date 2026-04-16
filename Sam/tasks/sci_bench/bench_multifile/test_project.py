"""Tests for the data-processing project.

These tests work with DataProcessor in main.py AND after it is
refactored into models.py (the import falls back automatically).
"""

import json
import os
import sys
import tempfile
import textwrap

import pytest

# Allow imports from the project directory
sys.path.insert(0, os.path.dirname(__file__))

try:
    from models import DataProcessor
except ImportError:
    from main import DataProcessor

from utils import format_output, validate_input
import config


@pytest.fixture
def sample_csv(tmp_path):
    """Write a small CSV and return its path."""
    p = tmp_path / "sample.csv"
    p.write_text(textwrap.dedent("""\
        id,name,score,category
        1,Alice,90,A
        2,Bob,60,B
        3,Carol,80,C
        4,Dave,50,A
        5,Eve,95,B
    """))
    return str(p)


def test_load(sample_csv):
    dp = DataProcessor()
    rows = dp.load(sample_csv)
    assert len(rows) == 5
    assert rows[0]["name"] == "Alice"
    assert rows[0]["score"] == 90.0


def test_filter(sample_csv):
    dp = DataProcessor()
    dp.load(sample_csv)
    above = dp.filter(threshold=75)
    assert len(above) == 3
    names = {r["name"] for r in above}
    assert names == {"Alice", "Carol", "Eve"}


def test_summarize(sample_csv):
    dp = DataProcessor()
    dp.load(sample_csv)
    s = dp.summarize()
    assert s["count"] == 5
    assert s["mean_score"] == 75.0
    assert s["max_score"] == 95.0
    assert s["min_score"] == 50.0


def test_format_output():
    data = [{"a": 1, "b": 2}]
    out = format_output(data, fmt="json")
    parsed = json.loads(out)
    assert parsed == data

    out_csv = format_output(data, fmt="csv")
    assert "a,b" in out_csv
    assert "1,2" in out_csv


def test_validate_input(sample_csv, tmp_path):
    assert validate_input(sample_csv) is True
    assert validate_input(str(tmp_path / "nope.csv")) is False
    # wrong extension
    txt = tmp_path / "data.txt"
    txt.write_text("hi")
    assert validate_input(str(txt)) is False
