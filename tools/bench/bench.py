#!/usr/bin/env python3
"""bench.py — minimalist bench orchestrator for SciF.

Single command, JSON plan, JSON report. Three phases:

  1. Pre-bench gateway probe — TPS sweep + concurrency-ceiling ramp.
     Aborts the whole run if the gateway is unhealthy. Recorded in the report.

  2. For each batch in plan.batches (executed top-to-bottom):
       a. Prepare state per batch.state ("fresh" | "inherit" | "<pin_name>")
       b. Launch N runs (parallel or sequential, with stagger if parallel)
       c. Attribute cam logs to metas (post-batch, race-free; see attribute.py)
       d. If batch.pin set: snapshot live state under <pin_name> via cp -al

  3. Write a single self-contained JSON report under tools/bench/reports/.

Plan format (JSON, see plans/example.json):
  {
    "name": "<plan_name>",
    "state_paths": ["F/mnt"],
    "lock_model": "gemma4",       # optional: rewrite Pam/gateway.rank.yaml to lock to this model
    "total_wall_s": 3600,         # optional: override ENV.sh:TOTAL_WALL_PER_RANK uniformly
    "gateway_probe": {"abort_below_tps": 10, "abort_above_oh_ms": 50},
    "batches": [
      {"name": "...", "task": "...", "n": 1, "parallel": 1,
       "state": "fresh|inherit|<pin>", "pin": "<name>"}
    ]
  }

  lock_model and total_wall_s mutate Pam/gateway.rank.yaml and ENV.sh
  in place. The originals are saved as <file>.bench-backup-<ts> and
  restored automatically when the plan finishes (or via finally on Ctrl-C).

Pre-requisites:
  - ENV.sh sourced (LITELLM_MASTER_KEY, GATEWAY_PORT). bench.py reads them
    from the environment; it does not source ENV.sh on your behalf.
  - Gateway running (Pam/gateway.sh start).

Usage:
  source ENV.sh
  tools/bench/bench.py tools/bench/plans/example.json [--skip-probe]
"""
import argparse, json, os, re, shutil, statistics, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib import request as urlreq, error as urlerr

import attribute  # sibling module

BASEDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS_DIR    = os.path.join(BASEDIR, "tools", "bench", "runs")
STATES_DIR  = os.path.join(BASEDIR, "tools", "bench", "states")
REPORTS_DIR = os.path.join(BASEDIR, "tools", "bench", "reports")

STAGGER_S = 3   # between parallel run launches — keeps cam.py filenames unique


# ─── helpers ──────────────────────────────────────────────────────────────

def utc_compact():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def gateway_url():
    """Compute LiteLLM gateway URL from GATEWAY_PORT (set by ENV.sh) or UID-derived fallback."""
    port = os.environ.get("GATEWAY_PORT")
    if not port:
        port = (os.getuid() % 55535) + 10000
    return f"http://127.0.0.1:{port}"


def post_chat(prompt, max_tokens=8, timeout=60, model=None):
    """One LiteLLM chat-completion call. Returns (status, response_ms_client, headers, body).

    `model` defaults to the env var BENCH_PROBE_MODEL (set by main() from plan's
    lock_model when present), else "gemma4". Probing the actual locked model
    matters because deepseek-v4-pro vs deepseek-v4-flash-off vs gemma4 have
    very different TPS/concurrency characteristics on the same gateway.
    """
    if model is None:
        model = os.environ.get("BENCH_PROBE_MODEL", "gemma4")
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }).encode()
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urlreq.Request(
        f"{gateway_url()}/v1/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    t0 = time.time()
    try:
        with urlreq.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, int((time.time() - t0) * 1000), dict(resp.headers), json.loads(body)
    except urlerr.HTTPError as e:
        return e.code, int((time.time() - t0) * 1000), dict(e.headers or {}), None
    except Exception as e:
        return 0, int((time.time() - t0) * 1000), {}, {"error": str(e)}


# ─── gateway probe (pre-bench, recorded in report) ────────────────────────

TPS_PROMPT = "Write a short paragraph about computing history."


def probe_tps(n=3):
    """Sequential decode-TPS sweep. Returns (median_tps, median_oh_ms, samples)."""
    tps_samples = []
    oh_samples = []
    for _ in range(n):
        st, wall_ms, hdrs, body = post_chat(TPS_PROMPT, max_tokens=50)
        if st == 200 and body:
            ct = (body.get("usage") or {}).get("completion_tokens", 0)
            if ct > 0 and wall_ms > 0:
                tps_samples.append(ct / (wall_ms / 1000))
            oh = hdrs.get("x-litellm-overhead-duration-ms")
            if oh:
                try: oh_samples.append(float(oh))
                except: pass
    return (
        statistics.median(tps_samples) if tps_samples else 0.0,
        statistics.median(oh_samples)  if oh_samples  else 0.0,
        tps_samples,
    )


def probe_concurrency(target_parallel=16):
    """Light concurrency check — 4 concurrent short requests. Verifies gateway
    accepts parallel connections without 429 or timeout. Does NOT stress-test at
    full target_parallel since local Ollama serialises inference anyway."""
    n_req = 4
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(post_chat, "Reply OK", 4, 60) for _ in range(n_req)]
        for f in as_completed(futs):
            results.append(f.result())
    n_ok  = sum(1 for r in results if r[0] == 200)
    n_429 = sum(1 for r in results if r[0] == 429)
    n_bad = sum(1 for r in results if r[0] not in (200, 429))
    walls = [r[1] for r in results if r[0] == 200]
    walls.sort()
    return {
        "concurrency": 4,
        "n_req": n_req, "n_ok": n_ok, "n_429": n_429, "n_bad": n_bad,
        "wall_p50_ms": (walls[len(walls)//2] if walls else None),
        "wall_p95_ms": (walls[int(0.95 * (len(walls)-1))] if walls else None),
        "healthy": (n_429 == 0 and n_bad == 0),
    }


def gateway_probe(plan):
    """Quick pre-bench probe: TPS only."""
    cfg = plan.get("gateway_probe", {})
    abort_below_tps = cfg.get("abort_below_tps", 4)

    print("[probe] TPS sweep (3 calls @ max_tokens=50) …", flush=True)
    tps, oh, _ = probe_tps()
    print(f"[probe]   tps={tps:.1f} tok/s   oh_p50={oh:.1f}ms", flush=True)

    passed = tps >= abort_below_tps
    return {
        "tps_decode":    round(tps, 1),
        "oh_p50_ms":     round(oh,  1),
        "thresholds":    {"abort_below_tps": abort_below_tps},
        "passed":        passed,
    }


def probe_lite(n=5):
    """Lightweight probe used between batches. TPS-only, no concurrency ramp.

    Returns dict with tps_decode and oh_p50_ms. Cheap enough to run between
    batches without disturbing the run cadence (~15-30s).
    """
    tps, oh, _ = probe_tps(n=n)
    return {
        "ts_utc":     utc_compact(),
        "tps_decode": round(tps, 1),
        "oh_p50_ms":  round(oh,  1),
    }


# ─── plan-level overrides (lock_model + set_total_wall, with restore) ────

def _backup(path):
    """Snapshot <path> to <path>.bench-backup-<ts>, return backup path."""
    ts = utc_compact()
    bak = f"{path}.bench-backup-{ts}"
    shutil.copy2(path, bak)
    return bak


_RANK_ENTRY_RE = re.compile(
    r"^[ \t]*-[ \t]*rank:[ \t]*(-?\d+)[ \t]*\n[ \t]*name:[ \t]*(\S+)",
    re.MULTILINE,
)


def _parse_model_fields(content, model_name):
    """Extract rank + yaml fields for *model_name* from rank.yaml text.

    Searches active entries first, then commented-out entries.  Returns a dict
    with at least {rank, thinkable, budget} and optionally max_thinking_budget
    and max_tokens if present in the original entry.  Raises SystemExit if the
    model is not found at all.
    """
    # --- helper: given a block of consecutive yaml lines for one entry,
    #     extract key: value pairs we care about.
    _FIELD_RE = re.compile(r"^[ \t]*(\w+):[ \t]*(\S+)")

    def _fields_from_lines(lines):
        d = {}
        for ln in lines:
            m = _FIELD_RE.match(ln)
            if m:
                d[m.group(1)] = m.group(2)
        return d

    # Split content into lines for block-oriented scanning.
    lines = content.splitlines()

    # Try active entries first, then commented.
    for commented in (False, True):
        for i, raw in enumerate(lines):
            # Detect "- rank:" line (active or commented)
            if commented:
                m = re.match(r"^[ \t]*#[ \t]*-[ \t]*rank:[ \t]*(-?\d+)", raw)
            else:
                m = re.match(r"^[ \t]*-[ \t]*rank:[ \t]*(-?\d+)", raw)
            if not m:
                continue

            # Collect the continuation lines that belong to this entry
            block = [raw]
            for j in range(i + 1, len(lines)):
                nxt = lines[j]
                if commented:
                    # continuation = commented indented line (not a new "- rank:")
                    if re.match(r"^[ \t]*#[ \t]+\w+:", nxt) and not re.match(r"^[ \t]*#[ \t]*-[ \t]*rank:", nxt):
                        block.append(nxt)
                    else:
                        break
                else:
                    if re.match(r"^[ \t]+\w+:", nxt) and not re.match(r"^[ \t]*-[ \t]*rank:", nxt):
                        block.append(nxt)
                    else:
                        break

            # Strip comment prefixes and list-item dash so field extraction
            # works uniformly (the first line is "- rank:" not "rank:").
            cleaned = []
            for idx, ln in enumerate(block):
                if commented:
                    ln = re.sub(r"^([ \t]*)#[ \t]*", r"\1", ln)
                if idx == 0:
                    # "  - rank: 2" → "    rank: 2"
                    ln = re.sub(r"-\s*", "  ", ln, count=1)
                cleaned.append(ln)

            fields = _fields_from_lines(cleaned)
            entry_name = fields.get("name", "")
            # Strip inline comments / trailing whitespace from name
            entry_name = entry_name.split("#")[0].strip()
            if entry_name != model_name:
                continue

            # Found — build result dict
            result = {
                "rank":      int(fields.get("rank", 0)),
                "budget":    int(fields.get("budget", -1)),
                "thinkable": fields.get("thinkable", "false").split("#")[0].strip(),
            }
            for opt in ("max_thinking_budget", "max_tokens"):
                if opt in fields:
                    result[opt] = int(fields[opt].split("#")[0].strip())
            return result

    return None  # not found


def lock_model(model_name):
    """Rewrite Pam/gateway.rank.yaml to keep only <model_name>.

    No-op if the file already has exactly that one active model. Otherwise:
    backup the original, write a slim auto-generated rank.yaml. Returns the
    backup path (or None if no change). Verbose: prints before/after.
    """
    rank_path = os.path.join(BASEDIR, "Pam", "gateway.rank.yaml")
    if not os.path.isfile(rank_path):
        raise SystemExit(f"ERROR: {rank_path} not found")
    content = open(rank_path).read()

    active = [(int(r), n) for r, n in _RANK_ENTRY_RE.findall(content)]
    print(f"[lock_model] requested: {model_name}")
    print(f"[lock_model] currently active in rank.yaml: {active or '(none)'}")

    if len(active) == 1 and active[0][1] == model_name:
        print(f"[lock_model] already locked — no change.")
        return None

    # Parse full model fields (rank, thinkable, optional max_thinking_budget/max_tokens)
    fields = _parse_model_fields(content, model_name)
    if fields is None:
        raise SystemExit(f"ERROR: model '{model_name}' not found (active or commented) in {rank_path}")

    target_rank = fields["rank"]
    thinkable   = fields["thinkable"]

    bak = _backup(rank_path)
    # Build entry lines preserving the original model's properties
    entry_lines = (
        f"  - rank: {target_rank}\n"
        f"    name: {model_name}\n"
        f"    budget: {fields['budget']}\n"
        f"    thinkable: {thinkable}\n"
    )
    if "max_thinking_budget" in fields:
        entry_lines += f"    max_thinking_budget: {fields['max_thinking_budget']}\n"
    if "max_tokens" in fields:
        entry_lines += f"    max_tokens: {fields['max_tokens']}\n"

    new_content = (
        f"# Auto-generated by tools/bench/bench.py — locked to {model_name} only.\n"
        f"# Original at: {os.path.basename(bak)}\n"
        f"models:\n"
        + entry_lines
        + f"connection_max: 10\n"
    )
    open(rank_path, "w").write(new_content)
    print(f"[lock_model] WROTE: {rank_path}  (rank {target_rank}, thinkable={thinkable}, only {model_name})")
    print(f"[lock_model] backup: {os.path.basename(bak)}")
    return bak


def set_total_wall(seconds, existing_backup=None):
    """Override ENV.sh's TOTAL_WALL_PER_RANK to <seconds> uniform across all 6 ranks.

    No-op if the value already matches. Otherwise: backup ENV.sh (or reuse
    `existing_backup`), rewrite the line. Returns backup path (or None).
    Verbose: prints before/after.
    """
    env_path = os.path.join(BASEDIR, "ENV.sh")
    if not os.path.isfile(env_path):
        raise SystemExit(f"ERROR: {env_path} not found")
    content = open(env_path).read()

    new_value = ",".join([str(int(seconds))] * 6)
    m = re.search(r"^export TOTAL_WALL_PER_RANK=(\S+)", content, re.MULTILINE)
    if not m:
        raise SystemExit("ERROR: 'export TOTAL_WALL_PER_RANK=...' not found in ENV.sh")
    old_value = m.group(1)
    print(f"[total_wall] requested: {seconds}s uniform → {new_value}")
    print(f"[total_wall] currently in ENV.sh: {old_value}")
    if old_value == new_value:
        print(f"[total_wall] already set — no change.")
        return None

    bak = existing_backup or _backup(env_path)
    new_content = re.sub(
        r"^(export TOTAL_WALL_PER_RANK=)\S+",
        rf"\g<1>{new_value}",
        content, count=1, flags=re.MULTILINE,
    )
    open(env_path, "w").write(new_content)
    print(f"[total_wall] WROTE: {env_path}  ({old_value} → {new_value})")
    print(f"[total_wall] backup: {os.path.basename(bak)}")
    return bak


def set_env_knob(name, value, existing_backup=None, expect_export=True):
    """Generic ENV.sh writer. Adds the export line if it doesn't exist (helps
    for knobs that are only commented-out / driver-defaulted)."""
    env_path = os.path.join(BASEDIR, "ENV.sh")
    if not os.path.isfile(env_path):
        raise SystemExit(f"ERROR: {env_path} not found")
    content = open(env_path).read()
    new_value = str(value)
    pat = re.compile(rf"^export {re.escape(name)}=(\S+)", re.MULTILINE)
    m = pat.search(content)
    if m:
        old_value = m.group(1)
        print(f"[{name}] requested: {value}")
        print(f"[{name}] currently in ENV.sh: {old_value}")
        if old_value == new_value:
            print(f"[{name}] already set — no change.")
            return None
        bak = existing_backup or _backup(env_path)
        new_content = pat.sub(f"export {name}={new_value}", content, count=1)
    else:
        if expect_export:
            print(f"[{name}] not in ENV.sh — appending")
        bak = existing_backup or _backup(env_path)
        new_content = content.rstrip() + f"\nexport {name}={new_value}  # bench knob\n"
    open(env_path, "w").write(new_content)
    print(f"[{name}] WROTE: {env_path}  ({m.group(1) if m else '(absent)'} → {new_value})")
    print(f"[{name}] backup: {os.path.basename(bak)}")
    return bak


def set_recap_every(n, existing_backup=None):
    """Override ENV.sh's RECAP_EVERY to <n>. Same backup-share pattern."""
    env_path = os.path.join(BASEDIR, "ENV.sh")
    if not os.path.isfile(env_path):
        raise SystemExit(f"ERROR: {env_path} not found")
    content = open(env_path).read()

    new_value = str(int(n))
    m = re.search(r"^export RECAP_EVERY=(\S+)", content, re.MULTILINE)
    if not m:
        raise SystemExit("ERROR: 'export RECAP_EVERY=...' not found in ENV.sh")
    old_value = m.group(1)
    print(f"[recap_every] requested: {n}")
    print(f"[recap_every] currently in ENV.sh: {old_value}")
    if old_value == new_value:
        print(f"[recap_every] already set — no change.")
        return None

    bak = existing_backup or _backup(env_path)
    new_content = re.sub(
        r"^(export RECAP_EVERY=)\S+",
        rf"\g<1>{new_value}",
        content, count=1, flags=re.MULTILINE,
    )
    open(env_path, "w").write(new_content)
    print(f"[recap_every] WROTE: {env_path}  ({old_value} → {new_value})")
    print(f"[recap_every] backup: {os.path.basename(bak)}")
    return bak


def set_max_iterations_work(n, existing_backup=None):
    """Override ENV.sh's MAX_ITERATIONS_WORK to <n>. Same backup-share pattern."""
    env_path = os.path.join(BASEDIR, "ENV.sh")
    if not os.path.isfile(env_path):
        raise SystemExit(f"ERROR: {env_path} not found")
    content = open(env_path).read()

    new_value = str(int(n))
    m = re.search(r"^export MAX_ITERATIONS_WORK=(\S+)", content, re.MULTILINE)
    if not m:
        raise SystemExit("ERROR: 'export MAX_ITERATIONS_WORK=...' not found in ENV.sh")
    old_value = m.group(1)
    print(f"[max_iterations_work] requested: {n}")
    print(f"[max_iterations_work] currently in ENV.sh: {old_value}")
    if old_value == new_value:
        print(f"[max_iterations_work] already set — no change.")
        return None

    bak = existing_backup or _backup(env_path)
    new_content = re.sub(
        r"^(export MAX_ITERATIONS_WORK=)\S+",
        rf"\g<1>{new_value}",
        content, count=1, flags=re.MULTILINE,
    )
    open(env_path, "w").write(new_content)
    print(f"[max_iterations_work] WROTE: {env_path}  ({old_value} → {new_value})")
    print(f"[max_iterations_work] backup: {os.path.basename(bak)}")
    return bak


def restore_overrides(backups):
    """Restore each (original, backup) pair via mv. Quiet if backup is None."""
    for original, bak in backups.items():
        if bak and os.path.exists(bak):
            shutil.move(bak, original)
            print(f"[restore] {os.path.relpath(original, BASEDIR)}  ←  {os.path.basename(bak)}")


# ─── state ops (cheap: mv + cp -al hardlink) ─────────────────────────────

def _basename(p):
    return os.path.basename(p.rstrip("/"))


# Subdirs within state_paths that persist across fresh/restore operations.
_PRESERVE_DIRS = ("sci_shared",)


def _preserve_save(full, ts):
    """Save preserved subdirs out of full before it gets moved/deleted.
    Returns list of (saved_path, relative_name) for later restore."""
    saved = []
    for name in _PRESERVE_DIRS:
        d = os.path.join(full, name)
        if os.path.isdir(d):
            tmp = os.path.join(os.path.dirname(full), f".{name}._preserve_{ts}")
            os.rename(d, tmp)
            saved.append((tmp, name))
    return saved


def _preserve_restore(full, saved):
    """Put preserved subdirs back into full, overwriting any pin/clone copy."""
    for tmp, name in saved:
        target = os.path.join(full, name)
        if os.path.exists(target):
            shutil.rmtree(target)
        os.rename(tmp, target)


def state_fresh(plan):
    """Move current state_paths aside, recreate empty.
    Preserved dirs (sci_shared) survive the reset."""
    ts = utc_compact()
    for p in plan["state_paths"]:
        full = os.path.join(BASEDIR, p)
        saved = _preserve_save(full, ts)
        if os.path.exists(full):
            os.rename(full, f"{full}.deleted-{ts}")
        os.makedirs(full, exist_ok=True)
        if _basename(p) == "mnt":
            os.makedirs(os.path.join(full, "sci_envs"), exist_ok=True)
            os.makedirs(os.path.join(full, "sci_shared"), exist_ok=True)
        _preserve_restore(full, saved)


def state_pin(plan, pin_name):
    """Snapshot current state under <pin_name> via hardlink-clone (cp -al)."""
    target = os.path.join(STATES_DIR, pin_name)
    if os.path.exists(target):
        os.rename(target, f"{target}.deleted-{utc_compact()}")
    os.makedirs(target, exist_ok=True)
    for p in plan["state_paths"]:
        full = os.path.join(BASEDIR, p)
        if not os.path.exists(full):
            continue
        dest = os.path.join(target, _basename(p))
        subprocess.run(["cp", "-al", full, dest], check=True)


def state_restore(plan, pin_name):
    """Replace live state with hardlink-clone of <pin_name>.
    Preserved dirs from live state always win over the pin's copy."""
    src = os.path.join(STATES_DIR, pin_name)
    if not os.path.isdir(src):
        raise SystemExit(f"ERROR: pin '{pin_name}' not found at {src}")
    ts = utc_compact()
    for p in plan["state_paths"]:
        full = os.path.join(BASEDIR, p)
        saved = _preserve_save(full, ts)
        if os.path.exists(full):
            os.rename(full, f"{full}.deleted-{ts}")
        snap = os.path.join(src, _basename(p))
        if os.path.exists(snap):
            subprocess.run(["cp", "-al", snap, full], check=True)
        else:
            os.makedirs(full, exist_ok=True)
        _preserve_restore(full, saved)


def prepare_state(plan, batch):
    s = batch.get("state", "inherit")
    if s == "fresh":
        print(f"[state] {batch['name']}: fresh → reset {plan['state_paths']}")
        state_fresh(plan)
    elif s == "inherit":
        print(f"[state] {batch['name']}: inherit (using whatever previous batch left)")
    else:
        print(f"[state] {batch['name']}: restore from pin '{s}'")
        state_restore(plan, s)


# ─── one run ──────────────────────────────────────────────────────────────

def run_one(label, idx, task, run_id=None):
    """Launch one SciF run, write minimal meta. Verdict filled by attribute()."""
    t0 = utc_compact()
    launch_s = int(time.time())
    out  = os.path.join(RUNS_DIR, f"{label}_{idx}_{t0}.stdout.log")
    err  = os.path.join(RUNS_DIR, f"{label}_{idx}_{t0}.stderr.log")
    meta = os.path.join(RUNS_DIR, f"{label}_{idx}_{t0}.meta.json")

    cmd = f"source ENV.sh && bash {BASEDIR}/SciF RUN {task}"
    start = time.time()
    with open(out, "w") as fo, open(err, "w") as fe:
        proc = subprocess.run(["bash", "-c", cmd], stdout=fo, stderr=fe, cwd=BASEDIR)
    wall = int(time.time() - start)

    meta_dict = {
        "label":              label,
        "idx":                idx,
        "task":               task,
        "ts_utc":             t0,
        "launch_ts_local_s":  launch_s,
        "wall_s":             wall,
        "exit_code":          proc.returncode,
        "verdict":            "PENDING",
        "cam_log":            "(pending_reassign)",
        "stdout_log":         os.path.relpath(out, BASEDIR),
        "stderr_log":         os.path.relpath(err, BASEDIR),
    }
    if run_id is not None:
        meta_dict["run_id"] = run_id
    json.dump(meta_dict, open(meta, "w"), indent=2)

    print(f"[run]   {label} #{idx} done rc={proc.returncode} wall={wall}s", flush=True)
    return meta


def _local_gpu_count():
    """Number of GPUs visible to nvidia-smi, 0 if unavailable."""
    try:
        out = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                             text=True, timeout=10)
        if out.returncode != 0:
            return 0
        return sum(1 for line in (out.stdout or "").splitlines() if line.startswith("GPU "))
    except Exception:
        return 0


def _have_local_gpu():
    return _local_gpu_count() > 0


def _have_slurm():
    """True if sbatch is on PATH."""
    return shutil.which("sbatch") is not None


def _task_skip_reason(task):
    """Return string explaining why this task should be skipped on this host,
    or None if it can run. Reads task metadata; capability-based."""
    task_dir = os.path.join(BASEDIR, "Sam", "tasks", task)
    top = os.path.join(task_dir, "top.md")
    if not os.path.isfile(top):
        return f"task .md not found: {top}"
    # Cheap frontmatter parse: GPU and Slurm keys.
    meta = {}
    with open(top) as f:
        in_fm = False
        for line in f:
            if line.strip() == "---":
                if in_fm: break
                in_fm = True
                continue
            if in_fm and ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    gpu = meta.get("GPU", "no").lower()
    slurm = meta.get("Slurm", "off").lower()
    if gpu == "slurm":
        slurm = "on"
    if gpu == "local" and not _have_local_gpu():
        return "GPU: local but no nvidia-smi"
    if gpu in ("1", "2", "3", "4", "all") and not _have_local_gpu():
        return f"GPU: {gpu} but no nvidia-smi"
    min_gpu = meta.get("MinGPU", "")
    if min_gpu.isdigit() and int(min_gpu) > _local_gpu_count():
        return f"MinGPU: {min_gpu} required but only {_local_gpu_count()} available"
    if slurm == "on" and not _have_slurm():
        return "Slurm: on but no sbatch on PATH"
    return None


def launch_batch(batch, run_id=None):
    """Run N copies (parallel or sequential, with stagger between launches).
    Skip the batch if the task requires hardware (GPU/SLURM) not available
    on this host. Returns True if runs were launched, False if skipped."""
    label    = batch["name"]
    n        = int(batch.get("n", 1))
    parallel = int(batch.get("parallel", 1))
    task     = batch["task"]
    skip = _task_skip_reason(task)
    if skip:
        print(f"[batch] {label}: SKIP — {skip}")
        return False
    print(f"[batch] {label}: launching n={n} parallel={parallel} task={task}")

    if parallel <= 1:
        for i in range(1, n + 1):
            run_one(label, i, task, run_id=run_id)
        return True

    pids = []  # list of submitted Future objects
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        for i in range(1, n + 1):
            pids.append(ex.submit(run_one, label, i, task, run_id=run_id))
            time.sleep(STAGGER_S)
        for p in as_completed(pids):
            p.result()
    return True


# ─── orchestrator ─────────────────────────────────────────────────────────

def validate_plan(plan):
    if "name"    not in plan: raise SystemExit("plan missing 'name'")
    if "batches" not in plan or not plan["batches"]:
        raise SystemExit("plan missing 'batches' or empty")
    plan.setdefault("state_paths", ["F/mnt"])
    plan.setdefault("gateway_probe", {})
    if "lock_model" in plan and not isinstance(plan["lock_model"], str):
        raise SystemExit("'lock_model' must be a string (model name)")
    if "total_wall_s" in plan:
        if not isinstance(plan["total_wall_s"], int) or plan["total_wall_s"] < 60:
            raise SystemExit("'total_wall_s' must be an int >= 60")
    if "max_iterations_work" in plan:
        if not isinstance(plan["max_iterations_work"], int) or plan["max_iterations_work"] < 1:
            raise SystemExit("'max_iterations_work' must be a positive int")
    if "recap_every" in plan:
        if not isinstance(plan["recap_every"], int) or plan["recap_every"] < 1:
            raise SystemExit("'recap_every' must be a positive int")
    for knob in ("tool_result_cap",
                  "max_iterations_review_done", "max_iterations_review_fail",
                  "max_iterations_reflect",
                  "max_retries_rejected", "max_retries_exhausted",
                  "error_limit", "nudge_limit"):
        if knob in plan:
            if not isinstance(plan[knob], int) or plan[knob] < 1:
                raise SystemExit(f"'{knob}' must be a positive int")
    # Pins from prior bench runs (cp -al snapshots in STATES_DIR) are also
    # accepted — lets a plan reuse a warm pin without redoing bootstrap.
    existing_pins = set(os.listdir(STATES_DIR)) if os.path.isdir(STATES_DIR) else set()
    seen_names = set()
    pins = set()
    for b in plan["batches"]:
        for k in ("name", "task"):
            if k not in b: raise SystemExit(f"batch missing '{k}': {b}")
        if b["name"] in seen_names:
            raise SystemExit(f"duplicate batch name: {b['name']}")
        seen_names.add(b["name"])
        s = b.get("state", "inherit")
        if s not in ("fresh", "inherit") and s not in pins and s not in existing_pins:
            raise SystemExit(f"batch '{b['name']}': state '{s}' references undefined pin")
        if "pin" in b and b["pin"]:
            pins.add(b["pin"])
        b.setdefault("n", 1)
        b.setdefault("parallel", 1)


def _check_orphaned_backups():
    """Detect orphaned .bench-backup-* files from a prior SIGKILL'd bench run.

    If found, warn the user and offer to restore them before proceeding.
    """
    targets = [
        os.path.join(BASEDIR, "ENV.sh"),
        os.path.join(BASEDIR, "Pam", "gateway.rank.yaml"),
    ]
    orphans = {}  # original_path → list of backup paths
    for orig in targets:
        parent = os.path.dirname(orig)
        base = os.path.basename(orig)
        if not os.path.isdir(parent):
            continue
        for f in sorted(os.listdir(parent)):
            if f.startswith(f"{base}.bench-backup-"):
                bak = os.path.join(parent, f)
                orphans.setdefault(orig, []).append(bak)

    if not orphans:
        return

    print("=" * 60)
    print("WARNING: Orphaned bench-backup files detected!")
    print("A previous bench run may have been killed before it could")
    print("restore the original files.")
    print()
    for orig, baks in orphans.items():
        rel = os.path.relpath(orig, BASEDIR)
        for bak in baks:
            print(f"  {os.path.basename(bak)}  →  {rel}")
    print()
    try:
        ans = input("Restore the most recent backup for each file? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"
        print()
    if ans == "y":
        for orig, baks in orphans.items():
            latest = baks[-1]  # sorted alphabetically, latest timestamp last
            shutil.move(latest, orig)
            print(f"[restore] {os.path.relpath(orig, BASEDIR)}  ←  {os.path.basename(latest)}")
            # Clean up remaining older backups
            for bak in baks[:-1]:
                os.remove(bak)
                print(f"[cleanup] removed older backup: {os.path.basename(bak)}")
        print()
    else:
        print("Skipping restore. Backups left in place.")
        print("=" * 60)


def main():
    ap = argparse.ArgumentParser(description="Run a bench plan end-to-end.")
    ap.add_argument("plan", help="path to JSON plan")
    ap.add_argument("--skip-probe", action="store_true",
                    help="skip the pre-bench gateway probe (use only when gateway is known good)")
    ap.add_argument("--probe-between", action="store_true",
                    help="run a lightweight TPS probe after each batch and record the deltas vs initial probe")
    args = ap.parse_args()

    # Bug 5: detect orphaned backups from a SIGKILL'd previous run
    _check_orphaned_backups()

    plan = json.load(open(args.plan))
    validate_plan(plan)

    for d in (RUNS_DIR, STATES_DIR, REPORTS_DIR):
        os.makedirs(d, exist_ok=True)

    print(f"=== bench plan: {plan['name']} ===", flush=True)
    print(f"    batches: {len(plan['batches'])}", flush=True)
    print(f"    state_paths: {plan['state_paths']}", flush=True)

    # Apply plan-level overrides (mutate gateway.rank.yaml / ENV.sh in place,
    # backup originals; restored in finally).
    backups = {}
    if "lock_model" in plan:
        b = lock_model(plan["lock_model"])
        if b:
            backups[os.path.join(BASEDIR, "Pam", "gateway.rank.yaml")] = b
        # Make probes hit the locked model, not always gemma4. Each plan's
        # initial + inter-batch probes then reflect the actual model under test.
        os.environ["BENCH_PROBE_MODEL"] = plan["lock_model"]
        print(f"[probe-model] probes will use: {plan['lock_model']}")
    # ENV.sh may be modified by multiple knobs. Share one backup so a second
    # override doesn't shadow the first.
    env_bak = None
    if "lock_model" in plan:
        env_bak = set_env_knob("WORKER_MODEL", plan["lock_model"], env_bak) or env_bak
    if "review_model" in plan:
        env_bak = set_env_knob("REVIEW_MODEL", plan["review_model"], env_bak) or env_bak
    if "total_wall_s" in plan:
        env_bak = set_total_wall(plan["total_wall_s"], env_bak) or env_bak
    if "max_iterations_work" in plan:
        env_bak = set_max_iterations_work(plan["max_iterations_work"], env_bak) or env_bak
    if "recap_every" in plan:
        env_bak = set_recap_every(plan["recap_every"], env_bak) or env_bak
    for knob_name, env_name in [
            ("max_iterations_review_done", "MAX_ITERATIONS_REVIEW_DONE"),
            ("max_iterations_review_fail", "MAX_ITERATIONS_REVIEW_FAIL"),
            ("max_iterations_reflect",     "MAX_ITERATIONS_REFLECT"),
            ("max_retries_rejected",       "MAX_RETRIES_REJECTED"),
            ("max_retries_exhausted",      "MAX_RETRIES_EXHAUSTED"),
            ("tool_result_cap",            "TOOL_RESULT_CAP"),
            ("error_limit",                "ERROR_LIMIT"),
            ("nudge_limit",                "NUDGE_LIMIT"),
    ]:
        if knob_name in plan:
            env_bak = set_env_knob(env_name, plan[knob_name], env_bak) or env_bak
    if env_bak:
        backups[os.path.join(BASEDIR, "ENV.sh")] = env_bak

    try:
        # 1. Probe
        if args.skip_probe:
            print("[probe] skipped (--skip-probe)")
            probe = {"skipped": True}
        else:
            probe = gateway_probe(plan)
            if not probe["passed"]:
                raise SystemExit(
                    f"[probe] FAILED thresholds: tps={probe['tps_decode']} oh={probe['oh_p50_ms']}ms "
                    f"ceiling={probe.get('conc_ceiling', '?')}. Fix the gateway or use --skip-probe.")
            print("[probe] passed thresholds.")

        # 2. Batches
        run_id = utc_compact()
        print(f"    run_id: {run_id}", flush=True)
        batch_results = []
        inter_probes  = []  # one entry per batch boundary (post-batch)
        baseline_tps  = probe.get("tps_decode") if isinstance(probe, dict) else None
        for batch in plan["batches"]:
            prepare_state(plan, batch)
            launched = launch_batch(batch, run_id=run_id)
            if not launched:
                print(f"[batch] {batch['name']}: skipped — skipping attribute/summarize")
                continue
            print(f"[batch] {batch['name']}: attributing cam logs …")
            time.sleep(2)  # tiny grace for kernel flush
            attribute.attribute(batch["name"], verbose=True, run_id=run_id)
            summary = attribute.summarize(batch, run_id=run_id)
            batch_results.append(summary)
            # Early-stop: if this batch declares abort_if_no_pass and produced
            # zero PASSes, skip remaining batches in the plan. Honors the
            # principle "draw conclusion in the time scale" — wave 2 of a
            # model that just went 0/N is unlikely to be discriminating.
            if batch.get("abort_if_no_pass") and summary.get("n_pass", 0) == 0 \
                    and summary.get("n_runs", 0) > 0:
                print(f"[abort] '{batch['name']}' produced 0/{summary['n_runs']} PASS "
                      f"and abort_if_no_pass=true — skipping remaining batches",
                      flush=True)
                break
            if batch.get("pin"):
                print(f"[state] pinning current state as '{batch['pin']}' (hardlink-clone)")
                state_pin(plan, batch["pin"])
            if args.probe_between:
                print(f"[probe-lite] post-batch '{batch['name']}' TPS sweep …")
                lp = probe_lite()
                lp["after_batch"] = batch["name"]
                if baseline_tps:
                    lp["delta_tps_pct"] = round(100 * (lp["tps_decode"] - baseline_tps) / baseline_tps, 1)
                print(f"[probe-lite]   tps={lp['tps_decode']} tok/s   "
                      f"oh={lp['oh_p50_ms']}ms"
                      + (f"   Δ={lp.get('delta_tps_pct')}% vs initial" if baseline_tps else ""))
                inter_probes.append(lp)
    finally:
        if backups:
            print("[restore] reverting plan-level overrides …")
            restore_overrides(backups)

    # 3. Report
    ts = utc_compact()
    report = {
        "plan":          plan["name"],
        "ts_utc":        ts,
        "state_paths":   plan["state_paths"],
        "gateway_probe": probe,
        "inter_probes":  inter_probes,
        "batches":       batch_results,
    }
    report_path = os.path.join(REPORTS_DIR, f"{plan['name']}_{ts}.json")
    json.dump(report, open(report_path, "w"), indent=2)

    # Concise terminal summary
    print()
    print("=== bench summary ===")
    print(f"plan: {plan['name']}   ts: {ts}")
    if not args.skip_probe:
        print(f"gateway: tps={probe['tps_decode']} tok/s   oh={probe['oh_p50_ms']}ms   conc_ceiling={probe.get('conc_ceiling', '?')}")
    print(f"{'batch':<20} {'n':>3} {'P/F/E':>8} {'pass_rate':>9} {'iters_p50':>9} {'wall_p50':>9} {'bash%_p50':>9}")
    for b in batch_results:
        pfe = f"{b['n_pass']}/{b['n_fail']}/{b['n_err']}"
        pr  = f"{b['pass_rate']:.0%}"  if b['pass_rate']    is not None else " - "
        ip  = f"{b['iters_p50']}"      if b['iters_p50']    is not None else " - "
        wp  = f"{b['wall_p50']}s"      if b['wall_p50']     is not None else " - "
        bp  = f"{b['bash_pct_p50']:.1%}" if b['bash_pct_p50'] is not None else " - "
        print(f"{b['name']:<20} {b['n_runs']:>3} {pfe:>8} {pr:>9} {ip:>9} {wp:>9} {bp:>9}")
    if inter_probes:
        print()
        print(f"{'after_batch':<20} {'tps':>8} {'oh_ms':>8} {'Δ_tps%':>8}")
        for lp in inter_probes:
            d = lp.get("delta_tps_pct")
            d_str = f"{d:+.1f}" if d is not None else " - "
            print(f"{lp['after_batch']:<20} {lp['tps_decode']:>8} {lp['oh_p50_ms']:>8} {d_str:>8}")
    print(f"\nreport: {report_path}")

    # exit non-zero if any batch had no PASS — useful in CI / loops
    sys.exit(0 if all(b["n_pass"] > 0 for b in batch_results) else 2)


if __name__ == "__main__":
    main()
