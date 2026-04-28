#!/usr/bin/env python3
"""Pam — common model selection for the SciF system.

Encapsulates rank config, health checking, connection error tracking,
and model selection. All container-based scripts share one Pam instance.

Budget tracking stays in callers — Pam checks but doesn't track usage.

Stdlib only. Thread-safe.
"""

import os, json, re, time, threading, random, urllib.request


class PamNoModel(Exception):
    """No model available matching the criteria."""


class Pam:
    """Model selector backed by gateway.rank.yaml and gateway health."""

    def __init__(self, rank_yaml_path, gateway_url=None,
                 fallback_highest=None, fallback_working=None):
        self._gateway = gateway_url or os.environ.get("GATEWAY_URL", "http://localhost:4000")
        self._fallback_highest = fallback_highest or os.environ.get("FALLBACK_HIGHEST", "")
        self._fallback_working = fallback_working or os.environ.get("FALLBACK_WORKING", "")
        self._rank_yaml_path = rank_yaml_path

        # Parsed config
        self._config = self._load(rank_yaml_path)

        # Health state
        self._unhealthy = set()
        self._health_ts = 0.0
        self._health_lock = threading.Lock()
        self._HEALTH_TTL = 60

        # Litellm model name mapping (built once)
        self._litellm_map = {}
        self._map_built = False

        # Connection error tracking
        self._conn_errors = 0
        self._conn_lock = threading.Lock()

        # Per-model session blacklist (models that failed at runtime)
        self._blacklist = set()
        self._blacklist_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Config parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_rank_yaml(text):
        # Strip inline `# ...` comments before parsing a value. Real YAML only
        # treats '#' as a comment when preceded by whitespace; we split on the
        # bare '#' for simplicity. Safe here because our scalars (model names,
        # ints, bools) never legitimately contain '#'. Without this strip,
        # `name: gemma4   # 31b` becomes the literal name `gemma4   # 31b`,
        # which the gateway then rejects with a 400.
        def _val(line_after_colon):
            return line_after_colon.split('#', 1)[0].strip()

        result = {"models": [], "connection_max": 10}
        current = None
        for line in text.split('\n'):
            s = line.strip()
            if not s or s.startswith('#') or s == 'models:':
                continue
            if s.startswith('- rank:'):
                if current:
                    result["models"].append(current)
                current = {"rank": int(_val(s.split(':', 1)[1])), "budget": -1}
            elif s.startswith('name:') and current is not None:
                current["name"] = _val(s.split(':', 1)[1])
            elif s.startswith('budget:') and current is not None:
                current["budget"] = int(_val(s.split(':', 1)[1]))
            elif s.startswith('thinkable:') and current is not None:
                current["thinkable"] = _val(s.split(':', 1)[1]).lower() == 'true'
            elif s.startswith('max_thinking_budget:') and current is not None:
                current["max_thinking_budget"] = int(_val(s.split(':', 1)[1]))
            elif s.startswith('max_tokens:') and current is not None:
                current["max_tokens"] = int(_val(s.split(':', 1)[1]))
            elif s.startswith('connection_max:'):
                result["connection_max"] = int(_val(s.split(':', 1)[1]))
        if current:
            result["models"].append(current)
        return result

    def _load(self, path):
        if not path or not os.path.exists(path):
            return None
        with open(path) as f:
            return self._parse_rank_yaml(f.read())

    def reload(self):
        """Re-read rank yaml from disk (for evolution)."""
        self._config = self._load(self._rank_yaml_path)

    # ------------------------------------------------------------------
    # Health checking (private, auto-called by _can_use)
    # ------------------------------------------------------------------

    def _build_map(self):
        if self._map_built:
            return
        try:
            req = urllib.request.Request(f"{self._gateway}/v1/model/info")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            mapping = {}
            for entry in data.get("data", []):
                name = entry.get("model_name", "")
                lm = entry.get("litellm_params", {}).get("model", "")
                if name and lm:
                    mapping[lm] = name
                    parts = lm.split("/", 1)
                    if len(parts) > 1:
                        mapping[parts[1]] = name
            self._litellm_map = mapping
            self._map_built = True
        except Exception:
            pass

    def _refresh_health(self):
        now = time.time()
        with self._health_lock:
            if now - self._health_ts < self._HEALTH_TTL:
                return
            self._health_ts = now
        self._build_map()
        try:
            req = urllib.request.Request(f"{self._gateway}/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            sick = set()
            for entry in data.get("unhealthy_endpoints", []):
                lm = entry.get("model", "")
                name = self._litellm_map.get(lm, lm)
                sick.add(name)
            with self._health_lock:
                self._unhealthy = sick
        except Exception:
            pass  # keep previous state

    # ------------------------------------------------------------------
    # Connection error tracking (called by API callers)
    # ------------------------------------------------------------------

    def report_connection_ok(self):
        with self._conn_lock:
            self._conn_errors = max(0, self._conn_errors - 1)

    def report_connection_error(self):
        with self._conn_lock:
            self._conn_errors += 1

    def blacklist_model(self, name):
        """Blacklist a model for the rest of this session.
        Called when a model hits error_limit or nudge_limit."""
        with self._blacklist_lock:
            self._blacklist.add(name)

    def is_blacklisted(self, name):
        with self._blacklist_lock:
            return name in self._blacklist

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def all_ranks(self):
        """Sorted unique non-negative ranks."""
        if not self._config:
            return []
        return sorted(set(m["rank"] for m in self._config["models"] if m["rank"] >= 0))

    def max_rank(self):
        ranks = self.all_ranks()
        return ranks[-1] if ranks else 0

    def config(self, name):
        """Full config dict for a model, or {}."""
        if not self._config:
            return {}
        for m in self._config["models"]:
            if m["name"] == name:
                return dict(m)
        return {}

    def is_thinkable(self, name):
        return self.config(name).get("thinkable", False)

    # ------------------------------------------------------------------
    # Internal selection helpers
    # ------------------------------------------------------------------

    def _models_at_rank(self, rank):
        if not self._config:
            return []
        return [m for m in self._config["models"] if m["rank"] == rank]

    def _can_use(self, m, usage=None, require_thinkable=False):
        """Check blacklist, budget, and requirements for one model entry.
        Health check via /health is intentionally NOT used: LiteLLM's health
        endpoint returns many false positives (endpoints that work fine in
        practice but get marked sick by background probes). We rely on
        session blacklist (via report_connection_error / nudge_limit /
        error_limit) to catch actually-broken models."""
        if self.is_blacklisted(m["name"]):
            return False
        if require_thinkable and not m.get("thinkable", False):
            return False
        if usage is not None and m["budget"] >= 0:
            if usage.get(m["name"], 0) >= m["budget"]:
                return False
        return True

    def _pick_from_rank(self, rank, exclude=None, usage=None,
                        require_thinkable=False, shuffle=False):
        """Pick first available model at a rank.
        Returns {"name", "rank", ...} dict or None."""
        models = self._models_at_rank(rank)
        if shuffle:
            models = list(models)
            random.shuffle(models)
        for m in models:
            if m["name"] == exclude:
                continue
            if self._can_use(m, usage, require_thinkable):
                return self._result(m, usage)
        return None

    def _result(self, m, usage=None):
        """Build return dict from a model entry."""
        budget = m.get("budget", -1)
        used = usage.get(m["name"], 0) if usage else 0
        return {
            "name": m["name"],
            "rank": m["rank"],
            "thinkable": m.get("thinkable", False),
            "max_tokens": m.get("max_tokens", 4096),
            "max_thinking_budget": m.get("max_thinking_budget", 0),
            "budget": budget,
            "budget_remaining": budget - used if budget >= 0 else None,
        }

    def _fallback_result(self, name, rank):
        """Build a fallback result when no config is available."""
        return {
            "name": name,
            "rank": rank,
            "thinkable": False,
            "max_tokens": 4096,
            "max_thinking_budget": 0,
            "budget": -1,
            "budget_remaining": None,
        }

    # ------------------------------------------------------------------
    # Public selection
    # ------------------------------------------------------------------

    def select(self, rank, exclude=None, usage=None,
               require_thinkable=False, shuffle=False, force_model=None):
        """Pick a model.

        rank: int (at-or-below waterfall), negative int (exact rank, e.g. -1),
              or "highest".
        exclude: model name to skip (for rotation on retry).
        usage: {model_name: call_count} for budget checking. None = skip budget check.
        require_thinkable: only pick models with thinkable=true.
        shuffle: randomize within rank (for subtask diversity).
        force_model: model name to force-select (bypasses all selection logic).
                     Used for controlled experiments and benchmarking.

        Returns dict: {name, rank, thinkable, max_tokens, max_thinking_budget,
                       budget, budget_remaining}.
        Returns None for negative ranks if nothing available (utility models are optional).
        """
        # Force-select: bypass all logic, return the named model directly
        if force_model:
            cfg = self.config(force_model)
            if cfg:
                return self._result(cfg, usage)
            # Model not in rank config — return minimal fallback
            return self._fallback_result(force_model, 0)

        is_highest = (rank == "highest")

        if not self._config:
            name = self._fallback_highest if is_highest else self._fallback_working
            if not name:
                raise PamNoModel("No rank config and no fallback configured")
            return self._fallback_result(name, 0)

        # Negative rank: direct pick from that exact rank (no waterfall)
        if not is_highest and int(rank) < 0:
            return self._pick_from_rank(int(rank), exclude, usage,
                                        require_thinkable, shuffle)

        target = self.max_rank() if is_highest else int(rank)

        # Connection error failsafe: skip to rank -1
        conn_max = self._config.get("connection_max", 10)
        with self._conn_lock:
            conn_exceeded = self._conn_errors >= conn_max
        if conn_exceeded:
            pick = self._pick_from_rank(-1, exclude, usage, require_thinkable, shuffle)
            if pick:
                return pick

        # Walk ranks from highest-at-or-below down to 0
        for r in sorted(self.all_ranks(), reverse=True):
            if r <= target:
                pick = self._pick_from_rank(r, exclude, usage, require_thinkable, shuffle)
                if pick:
                    return pick

        # Nothing below — try above target
        for r in sorted(self.all_ranks()):
            if r > target:
                pick = self._pick_from_rank(r, exclude, usage, require_thinkable, shuffle)
                if pick:
                    return pick

        # Last resort: rank -1 (no exclude)
        pick = self._pick_from_rank(-1, usage=usage)
        if pick:
            return pick

        # Final fallback
        name = self._fallback_highest if is_highest else self._fallback_working
        if name:
            return self._fallback_result(name, target)
        raise PamNoModel(f"No model available for rank={rank}")

    def highest(self, usage=None):
        """Shortcut: name of highest-rank available model."""
        return self.select("highest", usage=usage)["name"]
