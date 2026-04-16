#!/usr/bin/env python3
"""Unified container launcher for SciF.

Replaces driver.sh, evolution.sh, ask.sh with a single
Python module that computes Apptainer binds/env from task metadata
and profile definitions.

Usage (called by SciF after sourcing ENV.sh):
    python3 F/portal.py driver <task_name> [extra_args...]
    python3 F/portal.py evolution <mode> [task_dirs...]
    python3 F/portal.py ask [model]

Python 3.6 compatible (runs on host outside container).
"""

from __future__ import print_function
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_parser import parse_task, TaskFormatError

# ============================================================
# Environment (read from os.environ, set by SciF via ENV.sh)
# ============================================================

def _env(name, default=None):
    v = os.environ.get(name, default)
    if v is None:
        print("ERROR: %s not set. Source ENV.sh first." % name, file=sys.stderr)
        sys.exit(1)
    return v


def _env_opt(name, default=""):
    return os.environ.get(name, default)


# Lazy-loaded paths (resolved on first use)
_BASEDIR = None
_FDIR = None

def basedir():
    global _BASEDIR
    if _BASEDIR is None:
        _BASEDIR = _env("BASEDIR")
    return _BASEDIR

def fdir():
    global _FDIR
    if _FDIR is None:
        _FDIR = _env("FDIR")
    return _FDIR


# ============================================================
# GPU Resolution
# ============================================================

def _have_nvidia_smi():
    try:
        subprocess.check_output(["nvidia-smi", "--query-gpu=index",
                                 "--format=csv,noheader,nounits"],
                                stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _gpu_indices():
    """Return list of all physical GPU indices."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL).decode().strip()
        return [s.strip() for s in out.split("\n") if s.strip()]
    except (OSError, subprocess.CalledProcessError):
        return []


def _free_gpus(usable):
    """From usable indices, return those with no compute processes."""
    free = []
    for idx in usable:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-compute-apps=pid",
                 "--format=csv,noheader,nounits", "-i", str(idx)],
                stderr=subprocess.DEVNULL).decode().strip()
            pids = [l for l in out.split("\n") if l.strip() and l.strip() != "[N/A]"]
            if not pids:
                free.append(idx)
        except (OSError, subprocess.CalledProcessError):
            pass
    return free


def _select_gpus(need):
    """Select N free GPUs. Returns comma-separated string or None."""
    cvd = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if cvd:
        usable = [s.strip() for s in cvd.split(",") if s.strip()]
    else:
        usable = _gpu_indices()
    if not usable:
        return None
    free = _free_gpus(usable)
    if len(free) >= need:
        return ",".join(free[:need])
    print("WARNING: need %d free GPUs, found %d free out of %d usable"
          % (need, len(free), len(usable)), file=sys.stderr)
    return None


def resolve_gpu(meta):
    """Resolve GPU metadata into (use_nv, cuda_devices).

    Returns:
        use_nv: bool — whether to pass --nv to apptainer
        cuda_devices: str or None — CUDA_VISIBLE_DEVICES value
    """
    gpu_raw = meta.get("GPU", "no")
    gpu = gpu_raw.lower()
    gpu_n = 0

    # Env overrides
    gpu_force = os.environ.get("GPU_FORCE", "")
    if gpu_force:
        gpu_raw = gpu_force
        gpu = gpu_force.lower()

    # Normalize numeric: 1-9 → local with count
    if len(gpu) == 1 and gpu.isdigit() and gpu != "0":
        gpu_n = int(gpu)
        gpu = "local"

    have_gpu = _have_nvidia_smi()

    if gpu == "no":
        return False, None

    if gpu in ("local", "all"):
        if not have_gpu:
            print("ERROR: task declares 'GPU: %s' but no nvidia-smi on host" % gpu_raw,
                  file=sys.stderr)
            sys.exit(1)

    # GPU: ALL (case-sensitive) — all physical, ignore host CUDA_VISIBLE_DEVICES
    if gpu_raw == "ALL":
        all_phys = ",".join(_gpu_indices())
        print("WARNING: GPU: ALL — exposing ALL physical GPUs (%s). DEBUG ONLY!" % all_phys,
              file=sys.stderr)
        return True, all_phys

    if gpu == "all":
        cvd = os.environ.get("CUDA_VISIBLE_DEVICES", "")
        if cvd:
            print("[gpu] all host-visible: CUDA_VISIBLE_DEVICES=%s" % cvd, file=sys.stderr)
            return True, cvd
        else:
            all_vis = ",".join(_gpu_indices())
            print("[gpu] all: CUDA_VISIBLE_DEVICES=%s" % all_vis, file=sys.stderr)
            return True, all_vis

    if gpu == "local":
        n = gpu_n if gpu_n > 0 else 1
        # Skip if already pinned to the right count
        cvd = os.environ.get("CUDA_VISIBLE_DEVICES", "")
        if cvd:
            pinned = [s for s in cvd.split(",") if s.strip()]
            if len(pinned) == n:
                print("[gpu] already pinned: CUDA_VISIBLE_DEVICES=%s" % cvd,
                      file=sys.stderr)
                return True, cvd
        picked = _select_gpus(n)
        if picked:
            print("[gpu] auto-pin %d GPU(s): CUDA_VISIBLE_DEVICES=%s" % (n, picked),
                  file=sys.stderr)
            return True, picked
        # Not enough free
        allow_overuse = os.environ.get("GPU_ALLOW_OVERUSE", "false").lower() == "true"
        if allow_overuse:
            fallback = cvd or ",".join(_gpu_indices())
            print("WARNING: GPU_ALLOW_OVERUSE=true, passing all usable GPUs (%s)" % fallback,
                  file=sys.stderr)
            return True, fallback
        else:
            print("ERROR: requested %d GPU(s) but not enough free. "
                  "Set GPU_ALLOW_OVERUSE=true to override." % n, file=sys.stderr)
            sys.exit(1)

    if gpu in ("slurm", "on"):
        if have_gpu:
            n = gpu_n if gpu_n > 0 else 1
            picked = _select_gpus(n)
            if picked:
                print("[gpu] auto-pin %d GPU(s): CUDA_VISIBLE_DEVICES=%s" % (n, picked),
                      file=sys.stderr)
                return True, picked
            # No free GPUs available, but that's ok for slurm/on mode
            print("[gpu] no free local GPU (GPU=%s)" % gpu_raw, file=sys.stderr)
            return True, os.environ.get("CUDA_VISIBLE_DEVICES")
        else:
            print("[gpu] no local GPU available (GPU=%s)" % gpu_raw, file=sys.stderr)
            return False, None

    # Invalid value
    print("ERROR: invalid GPU value '%s' (expected: no|local|1-4|all|ALL|slurm|on)"
          % gpu_raw, file=sys.stderr)
    sys.exit(1)


# ============================================================
# SLURM Resolution
# ============================================================

def resolve_slurm(meta):
    """Returns list of bind tuples for SLURM tools, or empty list."""
    slurm = meta.get("Slurm", "off").lower()

    slurm_force = os.environ.get("SLURM_FORCE", "")
    if slurm_force:
        slurm = slurm_force.lower()

    # GPU: slurm implies Slurm: on
    gpu = meta.get("GPU", "no").lower()
    if gpu == "slurm":
        slurm = "on"

    if slurm == "on":
        binds = []
        for cmd in ("sbatch", "squeue", "scancel", "srun", "sacct", "scontrol"):
            binds.append(("/usr/bin/%s" % cmd, "/usr/bin/%s" % cmd, "ro"))
        binds.append(("/usr/lib64/slurm", "/usr/lib64/slurm", "ro"))
        print("[slurm] sbatch mapped into container", file=sys.stderr)
        return binds

    print("[slurm] sbatch NOT mapped (Slurm: off)", file=sys.stderr)
    return []


# ============================================================
# Run Directory Management
# ============================================================

_run_counter = [0]  # mutable for closure in Python 3.6

def create_run_dir(task_name, profile_name):
    """Create timestamped run directory, copy task source. Returns (run_dir, bind_run)."""
    tasks_src = _env("TASKS_SRC")
    src_dir = os.path.join(tasks_src, task_name)
    if not os.path.isdir(src_dir):
        print("ERROR: task '%s' not found in %s/" % (task_name, tasks_src),
              file=sys.stderr)
        sys.exit(1)

    _run_counter[0] += 1
    timestamp = "%s_%d_%d" % (time.strftime("%Y%m%d%H%M%S"), os.getpid(), _run_counter[0])
    isolation = os.environ.get("ISOLATION_MODE", "0") == "1"

    if isolation:
        iso_id = os.environ.get("BENCH_RUN_ID", "%d_%s" % (os.getpid(), timestamp))
        tmpdir = os.environ.get("TMPDIR", "/tmp")
        iso_dir = os.path.join(tmpdir, "iso_runs", iso_id)
        run_dir = os.path.join(iso_dir, "tasks", "%s_%s" % (task_name, timestamp))
        bind_run = os.path.join(iso_dir, "run")
    else:
        f = fdir()
        run_dir = os.path.join(f, "tasks", "%s_%s" % (task_name, timestamp))
        bind_run = os.path.join(f, "run")

    os.makedirs(os.path.dirname(run_dir), exist_ok=True)
    os.makedirs(bind_run, exist_ok=True)
    # Touch global state files
    for fname in (".global_memory.md", ".global_history.md"):
        p = os.path.join(bind_run, fname)
        if not os.path.exists(p):
            open(p, "a").close()
    shutil.copytree(src_dir, run_dir)
    print("[run] %s -> %s" % (task_name, run_dir))
    return run_dir, bind_run


# ============================================================
# Profile Definitions
# ============================================================

_created_tmp_dirs = []

def _host_tmp_bind():
    """Fresh per-run host dir for container /tmp (prevents cross-task collisions).

    Tracked in _created_tmp_dirs for cleanup after the container exits.
    """
    base = os.environ.get("TMPDIR", "/tmp")
    d = tempfile.mkdtemp(prefix="scif_tmp_", dir=base)
    _created_tmp_dirs.append(d)
    return d


def _cleanup_tmp_dirs():
    """Remove ONLY the per-run tmp dirs we created. Multiple safety gates."""
    base_real = os.path.realpath(os.environ.get("TMPDIR", "/tmp"))
    for d in _created_tmp_dirs:
        # All gates must pass — err on the side of leaving the dir behind.
        if not d or not isinstance(d, str):
            continue
        if not os.path.basename(d).startswith("scif_tmp_"):
            continue
        if os.path.islink(d) or not os.path.isdir(d):
            continue
        real = os.path.realpath(d)
        if os.path.dirname(real) != base_real:
            continue
        try:
            shutil.rmtree(real)
        except OSError as e:
            print("[portal] warn: failed to remove %s: %s" % (real, e),
                  file=sys.stderr)


def _mamba_init(env_name):
    """Shell snippet to activate micromamba env inside container."""
    return (
        'export MAMBA_ROOT_PREFIX=/F/mamba\n'
        'eval "$(/usr/local/bin/micromamba shell hook -s bash)"\n'
        'micromamba activate %s\n' % env_name
    )


def build_driver_cmd(task_name, extra_args):
    """Build and return full apptainer command for the driver profile."""
    tasks_src = _env("TASKS_SRC")
    src_topmd = os.path.join(tasks_src, task_name, "top.md")

    # Parse metadata from source top.md
    meta = {}
    if os.path.isfile(src_topmd):
        try:
            with open(src_topmd) as fh:
                parsed = parse_task(fh.read())
            meta = parsed["meta"]
        except TaskFormatError as e:
            print("ERROR: %s: %s" % (src_topmd, e), file=sys.stderr)
            sys.exit(1)

    # Resolve CommonHome / CommonStorage
    common_home = meta.get("CommonHome", "rw").lower()
    common_storage = meta.get("CommonStorage", "rw").lower()

    # Skill-triggered CommonStorage escalation
    if "CommonStorage" not in meta:
        skills = meta.get("Skills", "")
        if "env" in skills.lower():
            common_storage = "rw"

    # Isolation mode overrides
    isolation = os.environ.get("ISOLATION_MODE", "0") == "1"
    if isolation:
        common_home = "ro"
        common_storage = "ro"
        print("[isolation] forced CommonHome=ro, CommonStorage=ro", file=sys.stderr)

    # Validate GPU/Slurm
    gpu_val = meta.get("GPU", "no").lower()
    slurm_val = meta.get("Slurm", "off").lower()
    slurm_force = os.environ.get("SLURM_FORCE", "")
    if slurm_force:
        slurm_val = slurm_force.lower()
    if gpu_val == "slurm":
        slurm_val = "on"

    # Contradiction check
    slurm_explicit = "Slurm" in meta or slurm_force
    if gpu_val == "slurm" and slurm_explicit and slurm_val == "off":
        print("ERROR: task declares 'GPU: slurm' but explicit 'Slurm: off' — contradiction.",
              file=sys.stderr)
        sys.exit(1)

    # Slurm: on implies BashTime: -1
    bashtime = meta.get("BashTime", "")
    if slurm_val == "on" and bashtime != "-1":
        print("[slurm] Slurm: on implies BashTime: -1 (was '%s')"
              % (bashtime or "default"), file=sys.stderr)

    # GPU resolution
    use_nv, cuda_devices = resolve_gpu(meta)

    # SLURM tool binds
    slurm_binds = resolve_slurm(meta)

    # Create run directory
    run_dir, bind_run = create_run_dir(task_name, "driver")

    # Build bind mounts
    f = fdir()
    b = basedir()
    binds = [
        (os.path.join(f, "driver.py"), "/srv/driver.py", "ro"),
        (os.path.join(f, "task_parser.py"), "/srv/task_parser.py", "ro"),
        (os.path.join(b, "Pam", "pam.py"), "/srv/pam.py", "ro"),
        (bind_run, "/srv/run", None),  # None = default (rw)
        (run_dir, "/srv/%s" % task_name, None),
        (_env("RANK_SRC"), "/srv/gateway.rank.yaml", "ro"),
        (_env("SKILLS_SRC"), "/srv/skills", "ro"),
    ]

    # Conditional binds
    cam_dir = _env_opt("CAM_DIR")
    if cam_dir:
        binds.append((cam_dir, "/cam", "rw"))

    binds.append((_host_tmp_bind(), "/tmp", "rw"))

    # Home mount
    passwd_home = os.path.expanduser("~")
    home_dir = os.path.join(f, "home")
    if os.path.isdir(home_dir):
        binds.append((home_dir, passwd_home, "ro"))
        if common_home != "disable":
            binds.append((home_dir, "/home", common_home))

    # Mnt mount
    mnt_dir = os.path.join(f, "mnt")
    if common_storage != "disable" and os.path.isdir(mnt_dir):
        binds.append((mnt_dir, "/mnt", common_storage))

    # SLURM binds
    binds.extend(slurm_binds)

    # Build env vars
    env = {
        "GATEWAY_URL": "http://localhost:%s" % _env("GATEWAY_PORT"),
        "FALLBACK_HIGHEST": _env("FALLBACK_HIGHEST"),
        "FALLBACK_WORKING": _env("FALLBACK_WORKING"),
        "MAX_ITERATIONS": _env("MAX_ITERATIONS"),
        "CHECKPOINT_EVERY": _env("CHECKPOINT_EVERY"),
        "MAX_CONTEXT": _env("MAX_CONTEXT"),
        "MAX_DEPTH": _env("MAX_DEPTH"),
        "MAX_REVIEW_ITER": _env("MAX_REVIEW_ITER"),
        "MAX_REFLECT_ITER": _env("MAX_REFLECT_ITER"),
        "MAX_RETRIES": _env("MAX_RETRIES"),
        "MAX_PARALLEL_AGENTS": _env("MAX_PARALLEL_AGENTS"),
        "MAX_BASH_TIME": _env("MAX_BASH_TIME"),
        "WALL_LIMIT_PER_RANK": _env("WALL_LIMIT_PER_RANK"),
        "ITER_LIMIT_PER_RANK": _env("ITER_LIMIT_PER_RANK"),
        "TOTAL_WALL_PER_RANK": _env("TOTAL_WALL_PER_RANK"),
        "SKILLS_DIR": "/srv/skills",
        "EFFECTIVE_COMMON_STORAGE": common_storage,
        "EFFECTIVE_COMMON_HOME": common_home,
    }
    if cam_dir:
        env["CAM_DIR"] = "/cam"
    if cuda_devices:
        env["CUDA_VISIBLE_DEVICES"] = cuda_devices
    nvd = os.environ.get("NVIDIA_VISIBLE_DEVICES", "")
    if nvd:
        env["NVIDIA_VISIBLE_DEVICES"] = nvd

    # Build shell command
    # HOME=/home (mapped from F/home/, writable).
    # Symlink ~/.local and ~/.cache to /tmp so pip --user and caches
    # don't pollute the persistent home across runs.
    shell_cmd = (
        'export HOME=/home\n'
        'ln -sfn /tmp/.local /home/.local 2>/dev/null\n'
        'ln -sfn /tmp/.cache /home/.cache 2>/dev/null\n'
        + _mamba_init("driver")
        + 'python /srv/driver.py %s "$@"\n' % task_name
    )

    return _build_cmd(
        overlay=_env("OVERLAY"),
        sif=_env("SIF"),
        binds=binds,
        env=env,
        shell_cmd=shell_cmd,
        use_nv=use_nv,
        no_home=True,
        extra_args=extra_args,
    )


def build_evolution_cmd(extra_args):
    """Build apptainer command for the evolution profile."""
    f = fdir()
    b = basedir()

    # Convert args: task dirs → /srv/tasks/<basename>
    converted = []
    for arg in extra_args:
        if os.path.isdir(arg):
            converted.append("/srv/tasks/%s" % os.path.basename(arg))
        else:
            converted.append(arg)

    binds = [
        (os.path.join(f, "evolution.py"), "/srv/evolution.py", "ro"),
        (os.path.join(f, "driver.py"), "/srv/driver.py", None),  # rw (evolution may update)
        (os.path.join(f, "task_parser.py"), "/srv/task_parser.py", "ro"),
        (os.path.join(b, "Pam", "pam.py"), "/srv/pam.py", "ro"),
        (os.path.join(f, "tasks"), "/srv/tasks", "ro"),
        (os.path.join(f, "run"), "/srv/run", None),
        (_env("RANK_SRC"), "/srv/gateway.rank.yaml", None),  # rw (model mode updates)
        (_env("SKILLS_SRC"), "/srv/skills", "ro"),
    ]
    cam_dir = _env_opt("CAM_DIR")
    if cam_dir:
        binds.append((cam_dir, "/cam", "rw"))
    binds.append((_host_tmp_bind(), "/tmp", "rw"))

    env = {
        "GATEWAY_URL": "http://localhost:%s" % _env("GATEWAY_PORT"),
        "FALLBACK_HIGHEST": _env("FALLBACK_HIGHEST"),
        "MAX_EVOLVE_ITER": _env("MAX_EVOLVE_ITER"),
    }
    if cam_dir:
        env["CAM_DIR"] = "/cam"

    shell_cmd = _mamba_init("driver") + "python /srv/evolution.py %s\n" % " ".join(converted)

    return _build_cmd(
        overlay=_env("OVERLAY"),
        sif=_env("SIF"),
        binds=binds,
        env=env,
        shell_cmd=shell_cmd,
    )


def build_ask_cmd(extra_args):
    """Build apptainer command for the ask profile."""
    f = fdir()
    b = basedir()
    model = extra_args[0] if extra_args else _env("FALLBACK_HIGHEST")

    # Ensure run/ exists
    os.makedirs(os.path.join(f, "run"), exist_ok=True)

    binds = [
        (os.path.join(f, "ask.py"), "/srv/ask.py", "ro"),
        (os.path.join(f, "F.design.md"), "/srv/F.design.md", "ro"),
        (os.path.join(f, "F.usage.md"), "/srv/F.usage.md", "ro"),
        (os.path.join(f, "driver.py"), "/srv/driver.py", "ro"),
        (os.path.join(b, "Pam", "pam.py"), "/srv/pam.py", "ro"),
        (os.path.join(f, "evolution.py"), "/srv/evolution.py", "ro"),
        (_env("RANK_SRC"), "/srv/gateway.rank.yaml", "ro"),
        (os.path.join(b, "ENV.sh"), "/srv/ENV.sh", "ro"),
        (os.path.join(f, "run"), "/srv/run", "ro"),
        (os.path.join(f, "tasks"), "/srv/tasks", "ro"),
        (_env("SKILLS_SRC"), "/srv/skills", "ro"),
        (_env("TASKS_SRC"), "/srv/task_defs", "ro"),
    ]
    cam_dir = _env_opt("CAM_DIR")
    if cam_dir:
        binds.append((cam_dir, "/cam", "rw"))
    binds.append((_host_tmp_bind(), "/tmp", "rw"))

    env = {
        "GATEWAY_URL": "http://localhost:%s" % _env("GATEWAY_PORT"),
        "MODEL": model,
    }
    if cam_dir:
        env["CAM_DIR"] = "/cam"

    shell_cmd = _mamba_init("driver") + 'python /srv/ask.py "%s"\n' % model

    return _build_cmd(
        overlay=_env("OVERLAY"),
        sif=_env("SIF"),
        binds=binds,
        env=env,
        shell_cmd=shell_cmd,
        interactive=True,
    )


# ============================================================
# Apptainer Command Builder
# ============================================================

def _build_cmd(overlay, sif, binds, env, shell_cmd,
               use_nv=False, no_home=False, interactive=False,
               extra_args=None):
    """Build the full apptainer exec command list."""
    apptainer = _env("APPTAINER")
    cmd = [apptainer, "exec"]

    if interactive:
        cmd.extend(["-it"])

    if use_nv:
        cmd.append("--nv")

    # Env vars
    for k, v in sorted(env.items()):
        cmd.extend(["--env", "%s=%s" % (k, v)])

    # Overlay
    cmd.extend(["--overlay", "%s:ro" % overlay])

    if no_home:
        cmd.append("--no-home")

    cmd.append("--writable-tmpfs")

    # Bind mounts
    for bind in binds:
        host, container = bind[0], bind[1]
        mode = bind[2] if len(bind) > 2 else None
        if mode:
            cmd.extend(["--bind", "%s:%s:%s" % (host, container, mode)])
        else:
            cmd.extend(["--bind", "%s:%s" % (host, container)])

    cmd.extend(["--cleanenv", "--contain", "--pwd", "/srv"])
    cmd.append(sif)

    # Shell command
    cmd.extend(["bash", "-c", shell_cmd])

    # Extra args for the inner script
    if extra_args:
        cmd.append("_")  # $0 placeholder
        cmd.extend(extra_args)

    return cmd


# ============================================================
# CLI Entry Point
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: portal.py <driver|evolution|ask> [args...]", file=sys.stderr)
        sys.exit(1)

    profile = sys.argv[1]
    args = sys.argv[2:]

    if profile == "driver":
        if not args:
            tasks_src = _env("TASKS_SRC")
            print("Usage: portal.py driver <task_name>")
            print("  Tasks available in %s:" % tasks_src)
            for d in sorted(os.listdir(tasks_src)):
                if os.path.isdir(os.path.join(tasks_src, d)):
                    print("    %s" % d)
            sys.exit(1)
        task_name = args[0]
        extra = args[1:]
        cmd = build_driver_cmd(task_name, extra)

    elif profile == "evolution":
        cmd = build_evolution_cmd(args)

    elif profile == "ask":
        cmd = build_ask_cmd(args)

    else:
        print("ERROR: unknown profile '%s'. Use: driver, evolution, ask" % profile,
              file=sys.stderr)
        sys.exit(1)

    # Execute (subprocess, not execvp, so we can clean up our host tmp dirs).
    try:
        rc = subprocess.call(cmd)
    finally:
        _cleanup_tmp_dirs()
    sys.exit(rc)


if __name__ == "__main__":
    main()
