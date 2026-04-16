"""RTFL — Read The F***ing Log.

Structured log parser that extracts signal from large logs without dumping
everything into context. Combines pattern-based extraction (errors, stack
traces, exit codes) with targeted navigation (grep, slice, head, tail).
"""
import os
import re
import subprocess

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_OUTPUT_LINES = 200          # hard cap on returned lines
DEFAULT_HEAD_TAIL = 50          # default lines for head/tail
DEFAULT_CONTEXT = 3             # default grep context lines
SKELETON_HEAD = 20              # lines from top in skeleton
SKELETON_TAIL = 30              # lines from bottom in skeleton

# Patterns that signal important log events (case-insensitive)
ERROR_PATTERNS = [
    r'(?i)\b(error|fatal|critical|panic|segfault|segmentation fault)\b',
    r'(?i)\b(failed|failure|abort|aborted|killed|terminated)\b',
    r'(?i)\b(exception|traceback|stack trace)\b',
    r'(?i)\b(oom|out of memory|cannot allocate|memory error)\b',
    r'(?i)(exit code|return code|exit status|exited with)\s*[:\s=]*[1-9]',
]

WARNING_PATTERNS = [
    r'(?i)\bwarn(ing)?\b',
    r'(?i)\bdeprecated\b',
]

# Test/build summary patterns
SUMMARY_PATTERNS = [
    r'(?i)\d+\s+(passed|failed|error|skipped)',
    r'(?i)(PASSED|FAILED|OK|FAIL)\s*[:\s]',
    r'(?i)(test|tests|build|compile|make)\s+(succeeded|failed|passed|complete)',
    r'(?i)(real|user|sys)\s+\d+m[\d.]+s',  # time output
    r'(?i)^=+\s*(FAILURES|ERRORS|test session)',  # pytest headers
]

# Stack trace indicators (for multi-line capture)
STACK_START = [
    r'(?i)^Traceback \(most recent',
    r'(?i)^\s+at\s+\S+\(',                # Java/JS stack frames
    r'(?i)^#\d+\s+0x[0-9a-f]+',           # gdb backtrace
    r'(?i)^  File "',                       # Python stack frame
]


def _resolve_path(path, task_dir):
    if not os.path.isabs(path):
        path = os.path.join(task_dir, path)
    return path


def _read_lines(path):
    """Read file lines, handle encoding errors gracefully."""
    try:
        with open(path, "r", errors="replace") as f:
            return f.readlines()
    except FileNotFoundError:
        return None
    except IsADirectoryError:
        return None


def _format_line(lineno, line):
    """Format a line with its line number."""
    return f"{lineno:>6}| {line.rstrip()}"


def _cap_output(lines, label=""):
    """Cap output and add truncation notice if needed."""
    if len(lines) > MAX_OUTPUT_LINES:
        kept = lines[:MAX_OUTPUT_LINES]
        kept.append(f"... [{len(lines) - MAX_OUTPUT_LINES} more lines truncated]")
        return "\n".join(kept)
    return "\n".join(lines)


def _match_any(line, patterns):
    """Check if line matches any of the given patterns."""
    for p in patterns:
        if re.search(p, line):
            return True
    return False


def _extract_stack_traces(lines, max_traces=5, max_lines_per=20):
    """Extract multi-line stack traces."""
    traces = []
    i = 0
    while i < len(lines) and len(traces) < max_traces:
        if _match_any(lines[i], STACK_START):
            trace_start = i
            j = i + 1
            # Capture continuation: indented lines or known frame patterns
            while j < len(lines) and j - trace_start < max_lines_per:
                ln = lines[j]
                # Stack frames are typically indented or match frame patterns
                if (ln.startswith((" ", "\t"))
                        or re.match(r"(?i)^\s+(at|File|#\d)", ln)
                        or re.match(r"(?i)^\w+Error:", ln)
                        or re.match(r"(?i)^\w+Exception:", ln)):
                    j += 1
                else:
                    break
            traces.append((trace_start, j))
            i = j
        else:
            i += 1
    return traces


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def _skeleton(lines, path):
    """Structured overview: errors, warnings, stack traces, summary, head/tail."""
    total = len(lines)
    out = []
    out.append(f"=== RTFL Skeleton: {os.path.basename(path)} ({total} lines) ===")
    out.append("")

    # --- Exit code detection ---
    exit_lines = []
    for i, ln in enumerate(lines):
        if re.search(r'(?i)(exit code|return code|exit status|exited with)\s*[:\s=]*\d+', ln):
            exit_lines.append(_format_line(i + 1, ln))
    if exit_lines:
        out.append("── EXIT/RETURN CODES ──")
        out.extend(exit_lines[:10])
        out.append("")

    # --- Errors ---
    error_lines = []
    for i, ln in enumerate(lines):
        if _match_any(ln, ERROR_PATTERNS) and not _match_any(ln, [r'(?i)\bno error']):
            error_lines.append(_format_line(i + 1, ln))
    if error_lines:
        out.append(f"── ERRORS ({len(error_lines)} total) ──")
        if len(error_lines) > 30:
            out.extend(error_lines[:15])
            out.append(f"  ... [{len(error_lines) - 25} more errors] ...")
            out.extend(error_lines[-10:])
        else:
            out.extend(error_lines)
        out.append("")
    else:
        out.append("── ERRORS: none detected ──")
        out.append("")

    # --- Warnings (count only unless few) ---
    warning_lines = []
    for i, ln in enumerate(lines):
        if _match_any(ln, WARNING_PATTERNS):
            warning_lines.append(_format_line(i + 1, ln))
    if warning_lines:
        if len(warning_lines) <= 10:
            out.append(f"── WARNINGS ({len(warning_lines)}) ──")
            out.extend(warning_lines)
        else:
            out.append(f"── WARNINGS ({len(warning_lines)} total, showing first 5 + last 5) ──")
            out.extend(warning_lines[:5])
            out.append(f"  ... [{len(warning_lines) - 10} more warnings] ...")
            out.extend(warning_lines[-5:])
        out.append("")

    # --- Stack traces ---
    traces = _extract_stack_traces([ln for ln in lines], max_traces=3)
    if traces:
        out.append(f"── STACK TRACES ({len(traces)} detected) ──")
        for idx, (start, end) in enumerate(traces):
            out.append(f"  [trace {idx+1}] lines {start+1}-{end}:")
            for k in range(start, min(end, start + 15)):
                out.append(f"  {_format_line(k + 1, lines[k])}")
            if end - start > 15:
                out.append(f"    ... [{end - start - 15} more trace lines]")
        out.append("")

    # --- Test/build summaries ---
    summary_lines = []
    for i, ln in enumerate(lines):
        if _match_any(ln, SUMMARY_PATTERNS):
            summary_lines.append(_format_line(i + 1, ln))
    if summary_lines:
        out.append(f"── TEST/BUILD SUMMARIES ──")
        out.extend(summary_lines[:20])
        out.append("")

    # --- Head ---
    head_n = min(SKELETON_HEAD, total)
    out.append(f"── HEAD (first {head_n} lines) ──")
    for i in range(head_n):
        out.append(_format_line(i + 1, lines[i]))
    out.append("")

    # --- Tail ---
    tail_n = min(SKELETON_TAIL, total)
    tail_start = max(0, total - tail_n)
    # Don't overlap with head
    if tail_start < head_n:
        tail_start = head_n
    if tail_start < total:
        out.append(f"── TAIL (last {total - tail_start} lines) ──")
        for i in range(tail_start, total):
            out.append(_format_line(i + 1, lines[i]))
    out.append("")

    out.append(f"=== END SKELETON ({total} total lines) ===")
    return _cap_output(out)


def _grep(lines, pattern, context_lines):
    """Search for pattern with context lines."""
    out = []
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    matches = []
    for i, ln in enumerate(lines):
        if regex.search(ln):
            matches.append(i)

    if not matches:
        return f"No matches for pattern: {pattern}"

    out.append(f"=== {len(matches)} matches for /{pattern}/ ===")
    out.append("")

    # Merge overlapping context windows
    shown = set()
    for m in matches[:50]:  # cap at 50 matches
        start = max(0, m - context_lines)
        end = min(len(lines), m + context_lines + 1)
        for i in range(start, end):
            if i not in shown:
                marker = ">>>" if i == m else "   "
                out.append(f"{marker} {_format_line(i + 1, lines[i])}")
                shown.add(i)
        out.append("   ---")

    if len(matches) > 50:
        out.append(f"... [{len(matches) - 50} more matches not shown]")

    return _cap_output(out)


def _slice(lines, start, end):
    """Extract line range (1-indexed, inclusive)."""
    total = len(lines)
    start = max(1, start)
    end = min(total, end)
    if start > total:
        return f"Start line {start} exceeds file length ({total} lines)"

    out = [f"=== Lines {start}-{end} of {total} ==="]
    for i in range(start - 1, end):
        out.append(_format_line(i + 1, lines[i]))
    return _cap_output(out)


def _head(lines, n):
    """First N lines."""
    n = min(n, len(lines))
    out = [f"=== HEAD: first {n} of {len(lines)} lines ==="]
    for i in range(n):
        out.append(_format_line(i + 1, lines[i]))
    return _cap_output(out)


def _tail(lines, n):
    """Last N lines."""
    total = len(lines)
    n = min(n, total)
    start = total - n
    out = [f"=== TAIL: last {n} of {total} lines ==="]
    for i in range(start, total):
        out.append(_format_line(i + 1, lines[i]))
    return _cap_output(out)


# ---------------------------------------------------------------------------
# Entry point (called by driver.py)
# ---------------------------------------------------------------------------

def execute(args, task_dir):
    """Main entry point. Called by driver with args dict and task directory."""
    path = _resolve_path(args["path"], task_dir)

    if not os.path.exists(path):
        return f"File not found: {path}"
    if os.path.isdir(path):
        return f"Path is a directory, not a file: {path}"

    lines = _read_lines(path)
    if lines is None:
        return f"Could not read: {path}"
    if not lines:
        return f"File is empty: {path} (0 lines)"

    mode = args.get("mode", "skeleton").strip().lower()

    if mode == "skeleton":
        return _skeleton(lines, path)

    elif mode == "grep":
        pattern = args.get("pattern", "")
        if not pattern:
            return "grep mode requires a 'pattern' parameter"
        ctx = int(args.get("context_lines", DEFAULT_CONTEXT))
        return _grep(lines, pattern, ctx)

    elif mode == "slice":
        start = args.get("start_line", "")
        end = args.get("end_line", "")
        if not start or not end:
            return "slice mode requires 'start_line' and 'end_line' parameters"
        return _slice(lines, int(start), int(end))

    elif mode == "head":
        n = int(args.get("lines", DEFAULT_HEAD_TAIL))
        return _head(lines, n)

    elif mode == "tail":
        n = int(args.get("lines", DEFAULT_HEAD_TAIL))
        return _tail(lines, n)

    else:
        return f"Unknown mode: {mode}. Use: skeleton, grep, slice, head, tail"
