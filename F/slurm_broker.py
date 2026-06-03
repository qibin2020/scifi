#!/usr/bin/env python3
"""Host-side SLURM broker for the SciFi agent.

Runs on the login node (where native `sbatch` works — the agent's Rocky9
container has an older glibc and cannot run the host sbatch binary). Watches a
request directory shared with the agent container and turns high-level submit
requests into real SLURM jobs.

The agent only states WHAT to run and high-level resources (cpus/gpus/time).
All NERSC specifics (account, -C cpu/gpu, QOS, -c 32 GPU rule, SLURM_CPU_BIND)
live HERE and are never visible to the agent. The job command is wrapped through
the project's container wrapper (e.g. driver/enter_scifi_container.sh) so /srv
paths resolve transparently on the compute node.

Invoked by portal.py:   python slurm_broker.py <broker_config.json>

broker_config.json (written by portal.py, host-only — NOT bound into the
container) keys:
    account           NERSC compute account (from ENV.sh SLURM_ACCOUNT); "" => SLURM default
    channel_dir       host dir bound into the container at /slurm (requests/responses live here)
    log_dir           host dir for generated scripts + slurm logs
    submitted_record  host file; one job id per line (for finding orphans)
    workdir           project root to cd into before submit (maps to /srv); null => bare
    wrapper           wrapper script relative to workdir (e.g. driver/enter_scifi_container.sh); null => bare
"""
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time

_STOP = False


def _on_term(signum, frame):
    global _STOP
    _STOP = True


def _load_config(path):
    with open(path) as fh:
        return json.load(fh)


def _atomic_write(path, obj):
    d = os.path.dirname(path)
    base = os.path.basename(path)
    tmp = os.path.join(d, "." + base + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(obj, fh)
    os.rename(tmp, path)


def _sbatch_directives(cfg, req):
    """Map high-level resources -> (list of #SBATCH lines, body-prefix string).
    All NERSC policy is encoded here; the agent never sees any of it."""
    try:
        cpus = max(1, int(req.get("cpus", 4)))
    except (TypeError, ValueError):
        cpus = 4
    try:
        gpus = max(0, int(req.get("gpus", 0)))
    except (TypeError, ValueError):
        gpus = 0
    try:
        tmin = int(req.get("time_minutes", 30))
    except (TypeError, ValueError):
        tmin = 30
    tmin = max(1, min(tmin, 48 * 60))  # clamp to 48h
    name = re.sub(r"[^A-Za-z0-9_-]", "_", str(req.get("name", "scifjob")))[:32] or "scifjob"

    hh, mm = tmin // 60, tmin % 60
    # Account from ENV (cfg). NERSC requires the GPU account variant (<acct>_g)
    # for GPU jobs; derive it automatically. Empty account => omit the directive
    # and let SLURM use the user's default.
    acct = (cfg.get("account") or "").strip()
    if gpus >= 1 and acct and not acct.endswith("_g"):
        acct = acct + "_g"

    lines = []
    if acct:
        lines.append("#SBATCH --account=%s" % acct)
    lines += [
        "#SBATCH --job-name=%s" % name,
        "#SBATCH --time=%d:%02d:00" % (hh, mm),
        "#SBATCH --output=%s/slurm_%%x_%%j.out" % cfg["log_dir"],
        "#SBATCH --error=%s/slurm_%%x_%%j.err" % cfg["log_dir"],
        "#SBATCH --nodes=1",
    ]
    body_pre = ""
    if gpus >= 1:
        qos = "shared" if gpus <= 2 else "regular"
        lines += [
            "#SBATCH --constraint=gpu",
            "#SBATCH --qos=%s" % qos,
            "#SBATCH --ntasks=%d" % gpus,
            "#SBATCH --cpus-per-task=32",      # NERSC hard rule: 32 CPUs/GPU
            "#SBATCH --gpus-per-task=1",
        ]
        body_pre = 'export SLURM_CPU_BIND="cores"\n'
    else:
        # `cpus` is PHYSICAL cores. A Perlmutter CPU node has 128 physical cores
        # = 256 logical CPUs (2 hardware threads/core), and SLURM's -c is in
        # LOGICAL CPUs, so -c = 2 * physical cores. The shared QOS covers up to
        # half a node (64 physical cores); above that use regular (full node).
        if cpus <= 64:
            lines += [
                "#SBATCH --constraint=cpu",
                "#SBATCH --qos=shared",
                "#SBATCH --ntasks=1",
                "#SBATCH --cpus-per-task=%d" % (2 * cpus),
            ]
        else:
            lines += [
                "#SBATCH --constraint=cpu",
                "#SBATCH --qos=regular",
                "#SBATCH --ntasks=1",
                "#SBATCH --cpus-per-task=256",   # full node (128 physical cores)
            ]
    return lines, body_pre


def _build_script(cfg, req):
    directives, body_pre = _sbatch_directives(cfg, req)
    cmd = req.get("command", "")
    wd = cfg.get("workdir")
    wr = cfg.get("wrapper")
    if wd and wr:
        # Wrapped: run inside the project's container (project root -> /srv),
        # transparent for commands authored against /srv paths.
        body = "cd %s\nbash %s -c %s\n" % (shlex.quote(wd), shlex.quote(wr), shlex.quote(cmd))
    else:
        # Bare: run the command directly on the compute node (e.g. smoke tests).
        body = cmd + "\n"
    return "#!/bin/bash\n" + "\n".join(directives) + "\n\n" + body_pre + body


def _do_submit(cfg, req):
    script = _build_script(cfg, req)
    sf = os.path.join(cfg["log_dir"], "job_%s.slurm" % req["id"])
    with open(sf, "w") as fh:
        fh.write(script)
    cwd = cfg.get("workdir") or cfg["log_dir"]
    try:
        out = subprocess.check_output(
            ["sbatch", "--parsable", sf], cwd=cwd,
            stderr=subprocess.STDOUT, universal_newlines=True, timeout=120)
    except subprocess.CalledProcessError as e:
        last = (e.output or "sbatch failed").strip().splitlines()
        return {"ok": False, "error": (last[-1] if last else "sbatch failed")[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    jid = out.strip().split(";")[0].strip()
    if not jid.isdigit():
        return {"ok": False, "error": ("sbatch: " + out.strip())[:200]}
    try:
        with open(cfg["submitted_record"], "a") as fh:
            fh.write(jid + "\n")
    except OSError:
        pass
    return {"ok": True, "job_id": jid}


_FAIL_STATES = ("FAILED", "TIMEOUT", "CANCELLED", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL")


def _do_status(req):
    jid = str(req.get("job_id", "")).strip()
    if not jid.isdigit():
        return {"ok": False, "error": "bad job_id"}
    # In-queue check first (covers PENDING/RUNNING/COMPLETING).
    q = ""
    try:
        q = subprocess.check_output(
            ["squeue", "-j", jid, "-h", "-o", "%T"],
            stderr=subprocess.DEVNULL, universal_newlines=True, timeout=30).strip()
    except Exception:
        q = ""
    if q:
        st = q.splitlines()[0].split()[0] if q.split() else ""
        if st in ("PENDING", "CONFIGURING"):
            return {"ok": True, "state": "PENDING"}
        return {"ok": True, "state": "RUNNING"}
    # Not in queue -> final state from sacct.
    s = ""
    try:
        s = subprocess.check_output(
            ["sacct", "-j", jid, "-n", "-P", "-o", "State,ExitCode"],
            stderr=subprocess.DEVNULL, universal_newlines=True, timeout=30).strip()
    except Exception:
        s = ""
    state, exitc = "UNKNOWN", "0"
    for line in s.splitlines():
        parts = line.split("|")
        if len(parts) >= 2 and parts[0].strip():
            state = parts[0].split()[0]
            exitc = parts[1].split(":")[0] if parts[1] else "0"
            break
    if state.startswith("COMPLETED"):
        return {"ok": True, "state": "DONE", "exit": exitc}
    if state in _FAIL_STATES:
        return {"ok": True, "state": "FAILED", "exit": exitc or "1"}
    if state == "UNKNOWN":
        return {"ok": True, "state": "UNKNOWN"}
    return {"ok": True, "state": "RUNNING"}


def _do_cancel(req):
    jid = str(req.get("job_id", "")).strip()
    if not jid.isdigit():
        return {"ok": False, "error": "bad job_id"}
    try:
        subprocess.check_call(["scancel", jid], timeout=30)
        return {"ok": True, "state": "CANCELLED"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: slurm_broker.py <config.json>\n")
        sys.exit(2)
    cfg = _load_config(sys.argv[1])
    chan = cfg["channel_dir"]
    req_dir = os.path.join(chan, "requests")
    resp_dir = os.path.join(chan, "responses")
    for d in (req_dir, resp_dir, cfg["log_dir"]):
        os.makedirs(d, exist_ok=True)
    # Fresh channel for this run.
    for d in (req_dir, resp_dir):
        for fn in os.listdir(d):
            try:
                os.remove(os.path.join(d, fn))
            except OSError:
                pass

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    start_ppid = os.getppid()
    sys.stderr.write("[slurm_broker] watching %s (account=%s, workdir=%s)\n"
                     % (chan, cfg.get("account"), cfg.get("workdir")))
    sys.stderr.flush()

    while not _STOP:
        # Exit if portal (parent) died -> reparented to init (pid 1).
        if os.getppid() != start_ppid and os.getppid() == 1:
            break
        handled = False
        try:
            names = sorted(os.listdir(req_dir))
        except OSError:
            names = []
        for fn in names:
            if not fn.endswith(".json") or fn.startswith("."):
                continue
            rp = os.path.join(req_dir, fn)
            try:
                with open(rp) as fh:
                    req = json.load(fh)
            except Exception:
                continue  # mid-write or garbage; retry next loop
            op = req.get("op")
            if op == "submit":
                resp = _do_submit(cfg, req)
            elif op == "status":
                resp = _do_status(req)
            elif op == "cancel":
                resp = _do_cancel(req)
            else:
                resp = {"ok": False, "error": "unknown op %r" % op}
            resp["id"] = req.get("id")
            _atomic_write(os.path.join(resp_dir, "%s.json" % req.get("id")), resp)
            try:
                os.remove(rp)
            except OSError:
                pass
            handled = True
        if not handled:
            time.sleep(0.3)

    sys.stderr.write("[slurm_broker] stopping\n")
    sys.stderr.flush()


if __name__ == "__main__":
    main()
