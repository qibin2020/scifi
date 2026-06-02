#!/usr/bin/env python3
"""Smoke test for worker/review model selection (driver.py).

Guards the two things that previously failed *silently*:

  1. PRIORITY — worker resolves ForceModel > WORKER_MODEL > pam.select(rank);
     review resolves ControlModel > REVIEW_MODEL > pam.highest(). A pin must
     also FREEZE the model (override exclude rotation) — that is the bench
     combo-test contract.

  2. NO LEAK — every worker-spawn site must go through _resolve_worker_model.
     A raw pam.select() in a worker path re-enters the rank waterfall and the
     WORKER_MODEL pin leaks (the original bug). An AST guard asserts pam.select
     / pam.highest appear ONLY in the resolver funnels + sanctioned
     utility/recovery functions.

Runnable anywhere: the real `openai` dependency is stubbed before import, and
a synthetic rank config is injected so no gateway/yaml on disk is needed.

Python 3.6 compatible.
"""

import os
import sys
import ast
import types
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PAM_DIR = os.path.join(os.path.dirname(_HERE), "Pam")
sys.path.insert(0, _HERE)
sys.path.insert(0, _PAM_DIR)

# driver.py does `from openai import OpenAI` at import time; the driver runs in
# its own venv, so stub it here to keep this test dependency-free.
if "openai" not in sys.modules:
    _stub = types.ModuleType("openai")
    _stub.OpenAI = object
    sys.modules["openai"] = _stub

# driver reads these at import (hard os.environ[...]).
os.environ.setdefault("FALLBACK_HIGHEST", "fallback-highest")
os.environ.setdefault("FALLBACK_WORKING", "fallback-working")

import driver  # noqa: E402
from pam import Pam  # noqa: E402

DRIVER_PATH = os.path.join(_HERE, "driver.py")

# Synthetic rank config: ranks 2 (two models), 1 (budget-capped), 0, -1, -2.
# Parser keys each block on a leading "- rank:" line.
FIXTURE_YAML = """\
models:
- rank: 2
  name: big-a
  budget: -1
- rank: 2
  name: big-b
  budget: -1
- rank: 1
  name: mid-a
  budget: 2
- rank: 0
  name: small-a
  budget: -1
- rank: -1
  name: util-a
  budget: -1
- rank: -2
  name: text-a
  budget: -1
connection_max: 10
"""


def _make_pam():
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    f.write(FIXTURE_YAML)
    f.close()
    return Pam(rank_yaml_path=f.name,
               fallback_highest="fallback-highest",
               fallback_working="fallback-working")


class ResolutionTest(unittest.TestCase):
    """Behavioural matrix for both selection funnels."""

    def setUp(self):
        # Swap in the synthetic Pam + a clean usage map, and snapshot the env
        # pins so each test starts from "unset".
        self._saved = (driver.pam, driver._usage,
                       driver.WORKER_MODEL, driver.REVIEW_MODEL)
        driver.pam = _make_pam()
        driver._usage = {}
        driver.WORKER_MODEL = ""
        driver.REVIEW_MODEL = ""

    def tearDown(self):
        (driver.pam, driver._usage,
         driver.WORKER_MODEL, driver.REVIEW_MODEL) = self._saved

    # ---- worker axis -------------------------------------------------
    def test_worker_unpinned_picks_rank(self):
        # Highest-at-or-below rank 2, yaml order → big-a.
        self.assertEqual(driver._resolve_worker_model(2), "big-a")

    def test_worker_env_pin_overrides_rank(self):
        driver.WORKER_MODEL = "pinned-x"
        # Pin wins regardless of rank, even if not in the rank config.
        self.assertEqual(driver._resolve_worker_model(2), "pinned-x")
        self.assertEqual(driver._resolve_worker_model(0), "pinned-x")

    def test_worker_forcemodel_beats_env_pin(self):
        driver.WORKER_MODEL = "pinned-x"
        self.assertEqual(
            driver._resolve_worker_model(2, force_model="task-y"), "task-y")

    def test_worker_exclude_rotates_when_unpinned(self):
        self.assertEqual(
            driver._resolve_worker_model(2, exclude="big-a"), "big-b")

    def test_worker_pin_freezes_exclude(self):
        # The bench contract: a pin disables retry rotation.
        driver.WORKER_MODEL = "pinned-x"
        self.assertEqual(
            driver._resolve_worker_model(2, exclude="big-a"), "pinned-x")

    def test_worker_budget_exhaustion_walks_down(self):
        driver._usage = {"mid-a": 2}  # mid-a (budget 2) exhausted
        # rank 1 has only mid-a; over budget → waterfall down to rank 0.
        self.assertEqual(driver._resolve_worker_model(1), "small-a")

    # ---- review axis -------------------------------------------------
    def test_review_default_is_highest(self):
        self.assertEqual(driver._resolve_control_model(None), "big-a")

    def test_review_env_pin_used_when_no_control(self):
        driver.REVIEW_MODEL = "rev-z"
        self.assertEqual(driver._resolve_control_model(None), "rev-z")

    def test_review_controlmodel_by_name(self):
        self.assertEqual(driver._resolve_control_model("big-b"), "big-b")

    def test_review_controlmodel_by_rank(self):
        self.assertEqual(driver._resolve_control_model("0"), "small-a")

    def test_review_controlmodel_beats_env_pin(self):
        driver.REVIEW_MODEL = "rev-z"
        self.assertEqual(driver._resolve_control_model("big-b"), "big-b")


class NoLeakTest(unittest.TestCase):
    """Static guard: pam.select / pam.highest only inside sanctioned funcs.

    Worker spawns must funnel through _resolve_worker_model; a direct
    pam.select in a worker path (run_sam, _run_sam, the scheduler dispatch)
    is exactly the leak this whole change removes."""

    # Funnels + sanctioned utility/recovery paths (rank -1 text utils, and the
    # review recovery paths that intentionally deviate from the REVIEW_MODEL pin).
    ALLOWED = {
        "_resolve_control_model",   # review funnel
        "_resolve_worker_model",    # worker funnel
        "_compact_text",            # rank -1 text utility
        "index_history",            # rank -1 text utility
        "_review_fallback",         # rank -2 review recovery
        "review_sam",               # lateral review rotation (recovery)
    }

    def test_no_direct_pam_select_outside_funnels(self):
        with open(DRIVER_PATH) as f:
            tree = ast.parse(f.read())

        offenders = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                tgt = node.func
                if (isinstance(tgt, ast.Attribute)
                        and tgt.attr in ("select", "highest")
                        and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "pam"
                        and fn.name not in self.ALLOWED):
                    offenders.append("%s (line %d)" % (fn.name, node.lineno))

        self.assertEqual(
            offenders, [],
            "pam.select/highest called outside the sanctioned funnels — route "
            "worker selection through _resolve_worker_model: " + str(offenders))


if __name__ == "__main__":
    unittest.main(verbosity=2)
