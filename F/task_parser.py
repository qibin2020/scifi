"""Deterministic task markdown parser.

Format:
    ---
    Key: Value
    AnotherKey: some value
    ---

    # Title (optional)

    ## Context
    ...

    ## Todo
    ...

    ## Expect
    ...

Frontmatter (`---` delimited) is open key-value (no whitelist).
Keys starting with '_' are driver-private, filtered by public_meta().
Title is a single `# ` line between frontmatter and first ## section.
Sections use exactly `## ` headers. `###` subsections are preserved.
No other `## ` headers allowed.

Python 3.6 compatible (runs on host outside container).
"""

import re

__all__ = ["parse_task", "public_meta", "TaskFormatError"]

SECTIONS = ("Context", "Todo", "Expect")
_SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_META_RE = re.compile(r"^([A-Za-z_]\w*)\s*:\s*(.*)$")


class TaskFormatError(ValueError):
    """Raised when a task markdown file is malformed."""
    pass


def parse_task(text):
    """Parse task markdown into structured dict.

    Returns {"meta": dict, "title": str, "context": str, "todo": str, "expect": str}
    Raises TaskFormatError on malformed input.
    """
    meta = {}
    body = text

    # --- Frontmatter extraction ---
    stripped = text.lstrip("\n\r ")
    if stripped.startswith("---"):
        first = text.index("---")
        rest = text[first + 3:]
        close_idx = rest.find("\n---")
        if close_idx < 0:
            raise TaskFormatError("Frontmatter opened with --- but never closed")
        fm_block = rest[:close_idx]
        body = rest[close_idx + 4:]

        for line in fm_block.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _META_RE.match(line)
            if m:
                meta[m.group(1)] = m.group(2).strip()

    # --- Title extraction (between frontmatter and first ## section) ---
    title = ""
    for line in body.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("## "):
            break
        if s.startswith("# ") and not s.startswith("##"):
            title = s[2:].strip()
            break

    # --- Section extraction ---
    headers = list(_SECTION_RE.finditer(body))

    for h in headers:
        name = h.group(1).strip()
        if name not in SECTIONS:
            line_num = body[:h.start()].count("\n") + 1
            raise TaskFormatError(
                "Unknown section '## %s' at line %d. "
                "Allowed: ## Context, ## Todo, ## Expect" % (name, line_num))

    sections = {}
    for i, h in enumerate(headers):
        name = h.group(1).strip()
        if name in sections:
            line_num = body[:h.start()].count("\n") + 1
            raise TaskFormatError(
                "Duplicate section '## %s' at line %d" % (name, line_num))
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(body)
        sections[name] = body[start:end].strip()

    if "Todo" not in sections:
        raise TaskFormatError("Missing required section: ## Todo")
    if "Expect" not in sections:
        raise TaskFormatError("Missing required section: ## Expect")

    return {
        "meta": meta,
        "title": title,
        "context": sections.get("Context", ""),
        "todo": sections["Todo"],
        "expect": sections["Expect"],
    }


def public_meta(meta):
    """Filter out _-prefixed (driver-private) keys."""
    return {k: v for k, v in meta.items() if not k.startswith("_")}
