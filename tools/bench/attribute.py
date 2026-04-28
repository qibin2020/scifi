#!/usr/bin/env python3
"""attribute.py — pair run metas to cam logs, compute per-run time breakdown.

Two roles:
  1. attribute(label) — for every meta belonging to <label>, find its true cam
     log (by launch-time proximity), then compute verdict + iters + time
     breakdown and write back into the meta. Idempotent.
  2. summarize(batch) — collect already-attributed metas for <batch>, return
     the dict that goes into the bench report.

The 3 key metrics reported per batch are: pass_rate, iters_p50, bash_pct_p50.

Why proximity-based pairing:
  cam.py names its log driver_<task>_<YYYYMMDDHHMMSS>.jsonl with 1-second
  precision. Parallel runs that all want to identify "their" cam log in real
  time race with siblings whose logs are still being written. We defer to a
  single post-batch pass: each meta (sorted by launch_ts_local_s) greedily
  claims the earliest unclaimed cam log whose filename TS lies in
  [launch-2s, launch+30s]. Robust to gaps, race-free.
"""
import argparse, glob, json, os, re, statistics
from datetime import datetime, timezone

BASEDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAM_DIR = os.path.join(BASEDIR, "Cam")
RUNS_DIR = os.path.join(BASEDIR, "tools", "bench", "runs")

# Driver startup grace: cam log appears within ~30s of run.sh forking SciF.
STARTUP_GRACE = 30


# ─── timestamp helpers ────────────────────────────────────────────────────

def _filename_ts_s(path):
    """Cam log filename TS → local epoch seconds, or None."""
    m = re.search(r"_(\d{14})\.jsonl$", os.path.basename(path))
    if not m:
        return None
    s = m.group(1)
    try:
        dt = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]),
                      int(s[8:10]), int(s[10:12]), int(s[12:14]))
        return int(dt.timestamp())
    except Exception:
        return None


def _ts_utc_s(s):
    """ts_utc string '20260427T134406Z' → epoch seconds, or None."""
    try:
        dt = datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _event_ts_s(ts):
    """Cam event ts '2026-04-27T13:44:06' → epoch seconds, or None."""
    try:
        return int(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").timestamp())
    except Exception:
        return None


def _meta_launch_s(meta):
    """Best-available launch time for a meta."""
    if meta.get("launch_ts_local_s"):
        return int(meta["launch_ts_local_s"])
    return _ts_utc_s(meta.get("ts_utc", "")) or 0


# ─── cam log analysis ─────────────────────────────────────────────────────

def analyze_cam(path):
    """Return verdict + counts + time breakdown from a cam JSONL.

    Time breakdown:
      cam_wall  = last_event.ts − first_event.ts
      bash_wall = Σ (TOOL_RESULT.ts − TOOL_CALL.ts) where tool=bash
      llm_wall  = Σ (api_request.ts − prev_event.ts)
      other     = max(0, cam_wall − bash_wall − llm_wall)
    """
    out = {
        "iters": 0, "pass_n": 0, "fail_n": 0, "sams": 0, "retries": 0,
        "cam_wall": 0, "bash_wall": 0, "llm_wall": 0, "other_wall": 0, "n_bash": 0,
    }
    if not path or not os.path.isfile(path):
        return out
    events = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        ts = d.get("ts")
        if ts:
            d["_s"] = _event_ts_s(ts)
        events.append(d)
    if not events:
        return out

    # counts
    for d in events:
        e = d.get("event")
        if   e == "ITERATION":           out["iters"] += 1
        elif e == "SAM_START":           out["sams"]  += 1
        elif e == "RETRY":               out["retries"] += 1
        elif e == "SAM_VERIFIED":        out["pass_n"] += 1
        elif e == "REVIEW_VERDICT_PASS": out["pass_n"] += 1
        elif e == "REVIEW_VERDICT_FAIL": out["fail_n"] += 1
        elif e == "REVIEW_REJECTED":     out["fail_n"] += 1

    # time breakdown
    first_s = next((d["_s"] for d in events if d.get("_s")), None)
    last_s  = next((d["_s"] for d in reversed(events) if d.get("_s")), None)
    if first_s and last_s:
        out["cam_wall"] = last_s - first_s

    pending_bash = None
    for d in events:
        if d.get("_s") is None:
            continue
        if d.get("event") == "TOOL_CALL" and d.get("tool") == "bash":
            pending_bash = d["_s"]
        elif d.get("event") == "TOOL_RESULT" and d.get("tool") == "bash" and pending_bash is not None:
            out["bash_wall"] += d["_s"] - pending_bash
            out["n_bash"] += 1
            pending_bash = None

    prev_s = None
    for d in events:
        if d.get("event") == "api_request" and prev_s is not None and d.get("_s"):
            out["llm_wall"] += d["_s"] - prev_s
        if d.get("_s") is not None:
            prev_s = d["_s"]

    out["other_wall"] = max(0, out["cam_wall"] - out["bash_wall"] - out["llm_wall"])
    return out


# ─── pairing ──────────────────────────────────────────────────────────────

def attribute(label, dry_run=False, verbose=True):
    """Pair every meta for <label> with its cam log; update meta in-place."""
    metas = []
    for p in glob.glob(f"{RUNS_DIR}/{label}_[0-9]*_*.meta.json"):
        try:
            metas.append((p, json.load(open(p))))
        except Exception:
            pass
    if not metas:
        if verbose:
            print(f"[attribute] no metas for label '{label}'")
        return []
    metas.sort(key=lambda x: (_meta_launch_s(x[1]), x[1].get("idx", 0)))

    # Cam-log search window: just this batch's task + this batch's launch span.
    task_basenames = {os.path.basename(m.get("task", "")) for _, m in metas if m.get("task")} or {None}
    earliest = min(_meta_launch_s(m) for _, m in metas) - 5
    latest   = max(_meta_launch_s(m) for _, m in metas) + 60   # cam log appears ≤ ~30s of launch

    cam_logs = []
    for tb in task_basenames:
        patt = f"{CAM_DIR}/driver_*.jsonl" if tb is None else f"{CAM_DIR}/driver_{tb}_*.jsonl"
        for f in glob.glob(patt):
            ts = _filename_ts_s(f)
            if ts is None or ts < earliest or ts > latest:
                continue
            cam_logs.append((ts, f))
    cam_logs = sorted(set(cam_logs))

    # Greedy proximity pairing
    claimed = set()
    pairs = []
    for meta_path, meta in metas:
        ls = _meta_launch_s(meta)
        chosen = None
        for cam_ts, cam_path in cam_logs:
            if cam_path in claimed:
                continue
            d = cam_ts - ls
            if d < -2 or d > STARTUP_GRACE:
                continue
            chosen = cam_path
            claimed.add(cam_path)
            break
        pairs.append((meta_path, meta, chosen))

    # Update metas
    for meta_path, meta, cam_path in pairs:
        new = dict(meta)
        new["reassigned"] = True
        if cam_path is None:
            new["cam_log"] = "(no_cam_log_found)"
            new["verdict"] = "ERROR" if meta.get("exit_code", 0) != 0 else "NO_CAM"
            new["iters"] = 0
            new["bash_s"] = 0
            new["llm_s"] = 0
        else:
            a = analyze_cam(cam_path)
            if   a["pass_n"] >= 1:                       v = "PASS"
            elif a["fail_n"] >= 1:                       v = "FAIL"
            elif meta.get("exit_code", 0) != 0:          v = "ERROR"
            else:                                        v = "UNKNOWN"
            new["cam_log"]     = cam_path
            new["verdict"]     = v
            new["iters"]       = a["iters"]
            new["pass_events"] = a["pass_n"]
            new["fail_events"] = a["fail_n"]
            new["sams"]        = a["sams"]
            new["retries"]     = a["retries"]
            new["cam_wall_s"]  = a["cam_wall"]
            new["bash_s"]      = a["bash_wall"]
            new["llm_s"]       = a["llm_wall"]
            new["other_s"]     = a["other_wall"]
            new["n_bash"]      = a["n_bash"]
        if verbose:
            print(f"  #{new.get('idx')}  {new['verdict']:<7}  "
                  f"iters={new.get('iters',0):<4} wall={new.get('wall_s',0)}s  "
                  f"cam={os.path.basename(new['cam_log']) if new['cam_log'].endswith('.jsonl') else new['cam_log']}")
        if not dry_run:
            json.dump(new, open(meta_path, "w"), indent=2)
    return [m for _, m, _ in pairs]


# ─── batch summary (post-attribute) ───────────────────────────────────────

def _p50(xs):
    return statistics.median(xs) if xs else None


def summarize(batch):
    """Read attributed metas for batch.name and produce the report dict.

    Returns the per-batch entry that goes into the final report.
    """
    label = batch["name"]
    metas = []
    for p in sorted(glob.glob(f"{RUNS_DIR}/{label}_[0-9]*_*.meta.json")):
        try:
            metas.append(json.load(open(p)))
        except Exception:
            pass

    runs = []
    for m in metas:
        runs.append({
            "idx":      m.get("idx"),
            "verdict":  m.get("verdict", "PENDING"),
            "iters":    m.get("iters", 0),
            "wall_s":   m.get("wall_s", 0),
            "bash_s":   m.get("bash_s", 0),
            "llm_s":    m.get("llm_s", 0),
            "other_s":  m.get("other_s", 0),
            "n_bash":   m.get("n_bash", 0),
            "exit_code": m.get("exit_code"),
        })
    runs.sort(key=lambda r: (r["idx"] is None, r["idx"]))

    n = len(runs)
    n_pass = sum(1 for r in runs if r["verdict"] == "PASS")
    n_fail = sum(1 for r in runs if r["verdict"] == "FAIL")
    n_err  = sum(1 for r in runs if r["verdict"] in ("ERROR", "NO_CAM", "UNKNOWN"))

    pass_runs = [r for r in runs if r["verdict"] == "PASS" and r["wall_s"]]
    iters_p50 = _p50([r["iters"]  for r in pass_runs])
    wall_p50  = _p50([r["wall_s"] for r in pass_runs])
    bash_pcts = [r["bash_s"] / r["wall_s"] for r in pass_runs if r["wall_s"]]
    bash_pct_p50 = _p50(bash_pcts)

    return {
        "name":         batch["name"],
        "task":         batch.get("task"),
        "n":            batch.get("n", 1),
        "parallel":     batch.get("parallel", 1),
        "state":        batch.get("state", "inherit"),
        "pin":          batch.get("pin"),
        "n_runs":       n,
        "n_pass":       n_pass,
        "n_fail":       n_fail,
        "n_err":        n_err,
        "pass_rate":    round(n_pass / n, 3) if n else None,
        "iters_p50":    iters_p50,
        "wall_p50":     wall_p50,
        "bash_pct_p50": round(bash_pct_p50, 3) if bash_pct_p50 is not None else None,
        "runs":         runs,
    }


# ─── CLI (for ad-hoc reattribution / inspection) ─────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Attribute cam logs to bench metas + print summary.")
    ap.add_argument("--label",   required=True, help="batch label (== batch.name)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summary", action="store_true", help="also print the batch summary JSON")
    args = ap.parse_args()

    attribute(args.label, dry_run=args.dry_run)
    if args.summary:
        s = summarize({"name": args.label})
        print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
