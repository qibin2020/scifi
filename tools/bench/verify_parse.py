"""Reusable verify output parsing for cam log analysis.

Use TASK_RESULT event for verdicts (definitive).
Use these helpers ONLY for analyzing intermediate verify outputs within a SAM.
"""
import re

# Real verify pass: starts at line boundary, has a number
VERIFY_PASS_RE = re.compile(r'(?:^|\n)PASSED: All (\d+) outputs match', re.MULTILINE)

# Real verify fail: mismatch
VERIFY_FAIL_MISMATCH_RE = re.compile(r'(?:^|\n)FAILED: (\d+)/(\d+) mismatches', re.MULTILINE)

# Real verify fail: zero outputs
VERIFY_FAIL_ZERO_RE = re.compile(r'(?:^|\n)FAILED: only got (\d+) outputs', re.MULTILINE)


def count_verify_results(tool_result_text):
    """Parse a TOOL_RESULT's result text. Returns (n_pass, n_fail_mismatch, n_fail_zero)."""
    n_pass = len(VERIFY_PASS_RE.findall(tool_result_text))
    n_fail_mm = len(VERIFY_FAIL_MISMATCH_RE.findall(tool_result_text))
    n_fail_zero = len(VERIFY_FAIL_ZERO_RE.findall(tool_result_text))
    return n_pass, n_fail_mm, n_fail_zero


def task_verdict(events):
    """Get definitive verdict from cam events. Returns 'PASS', 'FAIL', or 'running'."""
    for e in reversed(events):
        if e.get('event') == 'TASK_RESULT':
            return e.get('verdict', '?')
    return 'running'
