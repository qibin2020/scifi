#!/usr/bin/env python3
"""Unit tests for task_parser.py.

Tests cover: frontmatter parsing, section extraction, title extraction,
error handling, metadata filtering, edge cases, and integration with
real task files on disk.

Python 3.6 compatible.
"""

import os
import sys
import glob
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_parser import parse_task, public_meta, TaskFormatError

BASEDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================================
# Frontmatter parsing
# ============================================================

class TestFrontmatter(unittest.TestCase):

    def test_basic_frontmatter(self):
        p = parse_task("---\nRank: 2\nBashTime: -1\n---\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["meta"]["Rank"], "2")
        self.assertEqual(p["meta"]["BashTime"], "-1")

    def test_extra_spaces_in_values(self):
        p = parse_task("---\nRank:   3  \n---\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["meta"]["Rank"], "3")

    def test_colon_in_value(self):
        p = parse_task("---\nNote: key: with: colons\n---\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["meta"]["Note"], "key: with: colons")

    def test_empty_value(self):
        p = parse_task("---\nTag:\n---\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["meta"]["Tag"], "")

    def test_underscore_key(self):
        p = parse_task("---\n_Hidden: yes\nPublic: no\n---\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertIn("_Hidden", p["meta"])
        self.assertIn("Public", p["meta"])

    def test_title_line_in_frontmatter_ignored(self):
        p = parse_task("---\n# Title\nRank: 1\n---\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(len(p["meta"]), 1)
        self.assertEqual(p["meta"]["Rank"], "1")

    def test_no_frontmatter(self):
        p = parse_task("## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["meta"], {})

    def test_unclosed_frontmatter_raises(self):
        with self.assertRaises(TaskFormatError) as cm:
            parse_task("---\nRank: 1\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertIn("never closed", str(cm.exception))

    def test_leading_whitespace_before_frontmatter(self):
        p = parse_task("\n\n---\nRank: 0\n---\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["meta"]["Rank"], "0")

    def test_many_metadata_keys(self):
        task = "---\nRank: 2\nBashTime: -1\nGPU: local\nSlurm: on\nSkills: a, b\n" \
               "NoMemory: on\nCommonStorage: rw\nCommonHome: disable\n_Note: x\n---\n\n## Todo\ndo\n\n## Expect\nok\n"
        p = parse_task(task)
        self.assertEqual(len(p["meta"]), 9)


# ============================================================
# Title extraction
# ============================================================

class TestTitle(unittest.TestCase):

    def test_title_after_frontmatter(self):
        p = parse_task("---\nRank: 1\n---\n\n# My Task\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["title"], "My Task")

    def test_no_title(self):
        p = parse_task("---\nRank: 0\n---\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["title"], "")

    def test_title_with_special_chars(self):
        p = parse_task("---\nRank: 0\n---\n\n# CaloVQ — VQ-VAE (v3)\n\n## Todo\ndo\n\n## Expect\nok\n")
        self.assertEqual(p["title"], "CaloVQ — VQ-VAE (v3)")

    def test_title_not_confused_with_subsection(self):
        p = parse_task("---\nRank: 0\n---\n\n## Todo\ndo\n\n### Not a title\n\n## Expect\nok\n")
        self.assertEqual(p["title"], "")


# ============================================================
# Section extraction
# ============================================================

class TestSections(unittest.TestCase):

    def test_all_three_sections(self):
        p = parse_task("---\nRank: 0\n---\n\n## Context\nctx\n\n## Todo\ntodo\n\n## Expect\nexpect\n")
        self.assertEqual(p["context"], "ctx")
        self.assertEqual(p["todo"], "todo")
        self.assertEqual(p["expect"], "expect")

    def test_missing_context_ok(self):
        p = parse_task("---\nRank: 0\n---\n\n## Todo\ntodo\n\n## Expect\nexpect\n")
        self.assertEqual(p["context"], "")
        self.assertEqual(p["todo"], "todo")

    def test_empty_context_body(self):
        p = parse_task("---\nRank: 0\n---\n\n## Context\n\n## Todo\ntodo\n\n## Expect\nexpect\n")
        self.assertEqual(p["context"], "")

    def test_missing_todo_raises(self):
        with self.assertRaises(TaskFormatError) as cm:
            parse_task("---\nRank: 0\n---\n\n## Context\nctx\n\n## Expect\nok\n")
        self.assertIn("Todo", str(cm.exception))

    def test_missing_expect_raises(self):
        with self.assertRaises(TaskFormatError) as cm:
            parse_task("---\nRank: 0\n---\n\n## Todo\ndo\n")
        self.assertIn("Expect", str(cm.exception))

    def test_unknown_section_raises(self):
        with self.assertRaises(TaskFormatError) as cm:
            parse_task("---\nRank: 0\n---\n\n## Todo\ndo\n\n## Results\nbad\n\n## Expect\nok\n")
        self.assertIn("Results", str(cm.exception))

    def test_duplicate_section_raises(self):
        with self.assertRaises(TaskFormatError) as cm:
            parse_task("---\nRank: 0\n---\n\n## Todo\nfirst\n\n## Todo\nsecond\n\n## Expect\nok\n")
        self.assertIn("Duplicate", str(cm.exception))

    def test_subsections_preserved(self):
        task = "---\nRank: 0\n---\n\n## Context\nIntro\n\n### Background\nDetails\n\n" \
               "## Todo\n1. Step\n\n### Notes\nExtra\n\n## Expect\n- ok\n"
        p = parse_task(task)
        self.assertIn("### Background", p["context"])
        self.assertIn("### Notes", p["todo"])

    def test_sections_any_order(self):
        p = parse_task("---\nRank: 0\n---\n\n## Expect\nok\n\n## Todo\ndo\n\n## Context\nbg\n")
        self.assertEqual(p["context"], "bg")
        self.assertIn("do", p["todo"])

    def test_large_section(self):
        big = "x" * 50000
        p = parse_task("---\nRank: 0\n---\n\n## Context\n%s\n\n## Todo\ndo\n\n## Expect\nok\n" % big)
        self.assertEqual(len(p["context"]), 50000)


# ============================================================
# public_meta filtering
# ============================================================

class TestPublicMeta(unittest.TestCase):

    def test_filters_underscore_prefix(self):
        meta = {"Rank": "2", "_DriverNote": "secret", "Skills": "a"}
        pub = public_meta(meta)
        self.assertIn("Rank", pub)
        self.assertIn("Skills", pub)
        self.assertNotIn("_DriverNote", pub)

    def test_all_private(self):
        self.assertEqual(public_meta({"_A": "1", "_B": "2"}), {})

    def test_empty(self):
        self.assertEqual(public_meta({}), {})

    def test_all_public(self):
        meta = {"A": "1", "B": "2"}
        self.assertEqual(public_meta(meta), meta)


# ============================================================
# Full task format (comprehensive)
# ============================================================

class TestFullTask(unittest.TestCase):
    """Tests a complete task with all features."""

    TASK = """\
---
Rank: 2
BashTime: -1
Skills: common_env, text_stats
NoMemory: on
_DriverNote: secret
---

# My Full Task

## Context
Background info.

### Subsection
More context.

## Todo
1. Step one
2. Step two

## Expect
- output.txt exists
- tests pass
"""

    def test_meta(self):
        p = parse_task(self.TASK)
        self.assertEqual(p["meta"]["Rank"], "2")
        self.assertEqual(p["meta"]["_DriverNote"], "secret")
        self.assertEqual(len(p["meta"]), 5)

    def test_title(self):
        p = parse_task(self.TASK)
        self.assertEqual(p["title"], "My Full Task")

    def test_context(self):
        p = parse_task(self.TASK)
        self.assertIn("Background info.", p["context"])
        self.assertIn("### Subsection", p["context"])

    def test_todo(self):
        p = parse_task(self.TASK)
        self.assertIn("Step one", p["todo"])

    def test_expect(self):
        p = parse_task(self.TASK)
        self.assertIn("output.txt exists", p["expect"])

    def test_public_meta(self):
        p = parse_task(self.TASK)
        pub = public_meta(p["meta"])
        self.assertNotIn("_DriverNote", pub)
        self.assertIn("Rank", pub)

    def test_return_keys(self):
        p = parse_task(self.TASK)
        self.assertEqual(set(p.keys()), {"meta", "title", "context", "todo", "expect"})


# ============================================================
# Integration: parse real task files from disk
# ============================================================

class TestRealTaskFiles(unittest.TestCase):
    """Parse actual task files from Sam/tasks/ to catch format drift."""

    def _task_dirs(self):
        """Find all task dirs with top.md under Sam/tasks/."""
        pattern = os.path.join(BASEDIR, "Sam", "tasks", "*", "*", "top.md")
        files = glob.glob(pattern)
        # Also flat dirs
        pattern2 = os.path.join(BASEDIR, "Sam", "tasks", "*", "top.md")
        files.extend(glob.glob(pattern2))
        return files

    def test_all_tasks_parse(self):
        """Every top.md in Sam/tasks/ should parse without error."""
        files = self._task_dirs()
        if not files:
            self.skipTest("No task files found")
        errors = []
        for f in files:
            try:
                parse_task(open(f).read())
            except TaskFormatError as e:
                errors.append("%s: %s" % (f, e))
        self.assertEqual(errors, [], "Tasks failed to parse:\n" + "\n".join(errors))

    def test_all_tasks_have_todo_and_expect(self):
        """Every parsed task has non-empty todo and expect."""
        files = self._task_dirs()
        if not files:
            self.skipTest("No task files found")
        for f in files:
            try:
                p = parse_task(open(f).read())
                self.assertTrue(p["todo"], "Empty todo in %s" % f)
                self.assertTrue(p["expect"], "Empty expect in %s" % f)
            except TaskFormatError:
                pass  # tested in test_all_tasks_parse

    def test_system_tasks_have_rank(self):
        """System test tasks should have Rank metadata."""
        pattern = os.path.join(BASEDIR, "Sam", "tasks", "system", "*", "top.md")
        files = glob.glob(pattern)
        if not files:
            self.skipTest("No system tasks found")
        for f in files:
            p = parse_task(open(f).read())
            self.assertIn("Rank", p["meta"],
                         "System task %s missing Rank" % os.path.basename(os.path.dirname(f)))


if __name__ == "__main__":
    unittest.main()
