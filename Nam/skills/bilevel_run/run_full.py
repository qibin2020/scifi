#!/usr/bin/env python3
"""bilevel_run skill — ONE-command FULL runner: submit -> wait -> verify.

Collapses the whole FULL workflow into a single blocking call so the agent
makes zero operational decisions: config staging, SLURM sizing, submission,
polling, and output verification all happen here. Talks to the host-side
SLURM broker over the /slurm channel (same protocol as the driver's
slurm_submit/slurm_status tools).

Usage:
    python3 run_full.py <CFG> <RUN_NAME> <G> [TIME_MINUTES]

<CFG>   config path; a file in the task dir (shipped config) is staged into
        the campaign area automatically; a bare filename is looked up there.
<G>     geometry count — sets cpus = min(32, max(4, G)) and the verify target.

CAMPAIGN AREA. All runs live under /srv/runs/<CAMPAIGN>/ where
CAMPAIGN = $SCIF_CAMPAIGN (the task's `Campaign:` key — stable name shared by
chained tasks) or else $SCIF_SESSION (this task invocation's unique id — so
repeated invocations of self-contained tasks never collide). Every terminal
result is appended to the discovery ledger /srv/runs/LEDGER.csv.

Prints `SUBMITTED job=<id>` once, then ONE final line:
    RUN_VERIFIED run=<NAME> roots=<N> job=<id>     success
    RUN_FAIL <reason>                              failure (exit 1)
"""
from __future__ import print_function

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_cmd  # noqa: E402

CHANNEL = os.environ.get("SCIF_SLURM_CHANNEL", "/slurm")    # env override for tests
RUNS_ROOT = "/srv/runs"
CAMPAIGN = (os.environ.get("SCIF_CAMPAIGN") or
            os.environ.get("SCIF_SESSION") or "").strip()
SESSION = (os.environ.get("SCIF_SESSION") or "").strip() or "adhoc"
# Campaign area: explicit test override > campaign subdir > legacy flat root.
if os.environ.get("SCIF_RUNS_DIR"):
    BASE = os.environ["SCIF_RUNS_DIR"]
elif CAMPAIGN:
    BASE = os.path.join(RUNS_ROOT, CAMPAIGN)
else:
    BASE = RUNS_ROOT
LEDGER = os.environ.get("SCIF_LEDGER", os.path.join(RUNS_ROOT, "LEDGER.csv"))


def fail(reason):
    print("RUN_FAIL %s" % reason)
    sys.exit(1)


def ledger(status, run, geoms, job, path):
    """Append one discovery line to the ledger (atomic single-line write)."""
    try:
        line = ",".join([time.strftime("%Y-%m-%dT%H:%M:%S"),
                         CAMPAIGN or "-", SESSION, run, str(geoms),
                         str(job), status, path]) + "\n"
        new = not os.path.isfile(LEDGER)
        with open(LEDGER, "a") as fh:
            if new:
                fh.write("date,campaign,session,run,geometries,job,status,path\n")
            fh.write(line)
    except (IOError, OSError):
        pass  # the ledger is advisory; never fail a run over it


def config_runs_dir(cfg):
    """runs_dir from the config file (where the SLURM job writes outputs)."""
    try:
        with open(cfg) as fh:
            m = re.search(r"^\s*runs_dir:\s*(\S+)", fh.read(), re.M)
        if m:
            return m.group(1).strip().strip("'\"")
    except (IOError, OSError):
        pass
    return BASE


def rpc(op, payload, timeout=180):
    """File-based RPC with the host broker (atomic write, poll response)."""
    rid = uuid.uuid4().hex[:12]
    req = dict(payload)
    req["op"] = op
    req["id"] = rid
    req_dir = os.path.join(CHANNEL, "requests")
    resp = os.path.join(CHANNEL, "responses", "%s.json" % rid)
    tmp = os.path.join(req_dir, ".%s.tmp" % rid)
    with open(tmp, "w") as fh:
        json.dump(req, fh)
    os.rename(tmp, os.path.join(req_dir, "%s.json" % rid))
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(resp):
            try:
                with open(resp) as fh:
                    r = json.load(fh)
            except ValueError:
                time.sleep(0.2)
                continue  # mid-write
            try:
                os.remove(resp)
            except OSError:
                pass
            return r
        time.sleep(0.3)
    return {"ok": False, "error": "broker did not respond in %ds" % timeout}


def verify(name, geoms, runs_dir):
    """Run the bundled read-only verifier. Returns (passed, last_line)."""
    out = subprocess.run(["bash", os.path.join(HERE, "verify.sh"),
                          name, str(geoms), runs_dir],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True)
    lines = (out.stdout or "").strip().splitlines()
    line = lines[-1] if lines else "RUN_FAIL verify produced no output"
    return out.returncode == 0 and line.startswith("RUN_VERIFIED"), line


def main():
    if len(sys.argv) < 4:
        fail("usage: run_full.py <CFG> <RUN_NAME> <G> [TIME_MINUTES]")
    cfg, name = sys.argv[1], sys.argv[2]
    try:
        geoms = int(sys.argv[3])
    except ValueError:
        fail("G (geometry count) must be an integer, got %r" % sys.argv[3])
    tmin = int(sys.argv[4]) if len(sys.argv) > 4 else (30 if geoms <= 2 else 60)

    # Resolve the config within the campaign area: a bare or missing path is
    # looked up there (where build.sh placed it this session).
    if not os.path.isfile(cfg):
        cand = os.path.join(BASE, os.path.basename(cfg))
        if os.path.isfile(cand):
            cfg = cand

    # Stage a task-shipped config into the campaign area so the SLURM job
    # container (project -> /srv) can read it.
    if os.path.isfile(cfg) and not os.path.abspath(cfg).startswith(BASE + os.sep):
        if not os.path.isdir(BASE):
            try:
                os.makedirs(BASE)
            except OSError as exc:
                fail("cannot create campaign dir %s: %s" % (BASE, exc))
        staged = os.path.join(BASE, "%s.yaml" % name)
        try:
            shutil.copyfile(cfg, staged)
        except (IOError, OSError) as exc:
            fail("cannot stage config to %s (need %s rw): %s" % (staged, BASE, exc))
        cfg = staged

    runs_dir = config_runs_dir(cfg)

    # Idempotent: a run this script already completed AND verified is done —
    # repeat calls (reviewer re-execution, worker retries) return the cached
    # result instead of submitting a duplicate SLURM job. FORCE=1 overrides.
    marker = os.path.join(runs_dir, name, ".run_full_verified")
    if os.path.isfile(marker) and os.environ.get("FORCE") != "1":
        ok, line = verify(name, geoms, runs_dir)
        if ok:
            with open(marker) as fh:
                job = fh.read().strip() or "unknown"
            print("%s job=%s (cached — already completed; FORCE=1 to rerun)"
                  % (line, job))
            sys.exit(0)
        # marker present but outputs no longer verify -> fall through to rerun

    if not os.path.isdir(os.path.join(CHANNEL, "requests")):
        fail("no %s channel — the task must set 'SlurmTool: on'" % CHANNEL)

    # A fresh submission invalidates any previous completion marker.
    try:
        os.remove(marker)
    except OSError:
        pass

    # 32 physical cores (= 64 logical, quarter node) is the empirical largest
    # request that still backfills quickly on Perlmutter shared; 64-core
    # (half-node) requests sat >2.5 h with no ETA (measured 2026-06-04).
    cpus = min(32, max(4, geoms))
    command, _ = run_cmd.build(cfg, name, "full", None, runs_dir=runs_dir)

    r = rpc("submit", {"command": command, "time_minutes": tmin,
                       "cpus": cpus, "gpus": 0, "name": name})
    if not r.get("ok"):
        fail("submit: %s" % r.get("error", "unknown"))
    job = r["job_id"]
    print("SUBMITTED job=%s (cpus=%d time=%dm)" % (job, cpus, tmin))
    sys.stdout.flush()

    # Wait for the job. Poll gently; cap well above the wall time (queue wait).
    deadline = time.time() + (tmin + 240) * 60
    while time.time() < deadline:
        r = rpc("status", {"job_id": job})
        if not r.get("ok"):
            fail("status: %s (job %s may still be running)" % (r.get("error"), job))
        state = r.get("state", "UNKNOWN")
        if state == "DONE":
            if str(r.get("exit", "0")) not in ("0", "0:0"):
                ledger("RUN_FAIL", name, geoms, job, os.path.join(runs_dir, name))
                fail("job=%s finished with exit %s" % (job, r.get("exit")))
            break
        if state == "FAILED":
            ledger("RUN_FAIL", name, geoms, job, os.path.join(runs_dir, name))
            fail("job=%s FAILED exit=%s reason=%s" % (
                job, r.get("exit", "?"), r.get("reason", "unknown")))
        time.sleep(30)
    else:
        fail("job=%s still not finished after %dm — check later" % (job, tmin + 240))

    ok, line = verify(name, geoms, runs_dir)
    if ok:
        try:
            with open(marker, "w") as fh:
                fh.write("%s\n" % job)
        except (IOError, OSError):
            pass  # marker is an optimization; the result line is the contract
    ledger("RUN_VERIFIED" if ok else "RUN_FAIL", name, geoms, job,
           os.path.join(runs_dir, name))
    print("%s job=%s" % (line, job))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
