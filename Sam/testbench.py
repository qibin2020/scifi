#!/usr/bin/env python3
"""testbench.py — scifi benchmark runner with dep graph, retries, and comparison.

Modes:
    testbench.py run   [--groups G1,...] [--parallel 4] [--retry 3] [--resume]
                       [--no-retry-on-slow] [--slow-wall-mult 3.0]
    testbench.py plan                 # dry-run scheduler, print phases
    testbench.py clean                # mv runtime env to .deleted/
    testbench.py report               # print comparison table from testing.csv

Outputs:
    Sam/logs/testing.csv              # rolling per-attempt CSV
    Sam/logs/<group>/<task>_try_N.log # per-attempt stdout
    Sam/logs/testbench_<ts>.log       # master log (when launched w/ nohup)
"""

import argparse
import csv
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple

# ============================================================================
# Constants
# ============================================================================

ROOT = Path(__file__).resolve().parent.parent
SAM_TASKS = ROOT / "Sam" / "tasks"
F_TASKS = ROOT / "F" / "tasks"
F_MNT = ROOT / "F" / "mnt"
F_HOME = ROOT / "F" / "home"
F_RUN = ROOT / "F" / "run"
LOGS_DIR = ROOT / "Sam" / "logs"
DELETED = ROOT / ".deleted"
TESTING_CSV = LOGS_DIR / "testing.csv"
SCIF = ROOT / "SciF"
GATEWAY_SH = ROOT / "Pam" / "gateway.sh"

GROUPS = ["system", "sci_bench", "sci_bench_task_maker", "sci_study"]

# benchmark.csv column names differ between groups
BENCH_COLS = {
    "sci_bench":            ("new_iters_max", "new_wall_max", "new_pass"),
    "sci_bench_task_maker": ("new_iters_max", "new_wall_max", "new_pass"),
    "sci_study":            ("new_cum_iters", "new_wall_max", "new_pass_rate"),
}

DEPS: Dict[str, List[str]] = {
    'system/env_warm':                              ['system/env_cold_pip'],
    'system/env_common':                            ['system/env_cold_pip'],
    'sci_bench/sci_root_gauss_fit':                 ['sci_bench/sci_root_install'],
    'sci_bench/sci_chain_root_pipeline':            ['sci_bench/sci_root_install'],
    'sci_bench/sci_skill_invoke':                   ['sci_bench/sci_skill_install'],
    'sci_bench/sci_skill_reuse':                    ['sci_bench/sci_skill_install'],
    'sci_bench_task_maker/sci_root_gauss_fit':      ['sci_bench_task_maker/sci_root_install'],
    'sci_bench_task_maker/sci_chain_root_pipeline': ['sci_bench_task_maker/sci_root_install'],
    'sci_bench_task_maker/sci_skill_invoke':        ['sci_bench_task_maker/sci_skill_install'],
    'sci_bench_task_maker/sci_skill_reuse':         ['sci_bench_task_maker/sci_skill_install'],
    'sci_bench_task_maker/sci_skill_gauss':         ['sci_bench_task_maker/sci_skill_install'],
    'sci_study/fw_debug':                           ['sci_study/fw_bootstrap'],
    'sci_study/fw_complete1':                       ['sci_study/fw_bootstrap'],
    'sci_study/fw_complete1_detailed':              ['sci_study/fw_bootstrap'],
    'sci_study/fw_complete2':                       ['sci_study/fw_bootstrap'],
    'sci_study/fw_complete2_detailed':              ['sci_study/fw_bootstrap'],
    'sci_study/fw_complete3':                       ['sci_study/fw_bootstrap'],
    'sci_study/fw_complete3_detailed':              ['sci_study/fw_bootstrap'],
    'sci_study/fw_complete3_tiny':                  ['sci_study/fw_bootstrap'],
}

CSV_HEADERS = [
    "group", "task", "attempt", "status", "iters", "wall_s",
    "iter_max", "wall_max", "bench_pass_rate", "verdict",
    "caps_tripped", "run_dir", "timestamp",
]

# Tasks known to be memory-heavy — capped at 2 concurrent
MEMHEAVY_PATTERNS = [
    r'mnist', r'torch', r'train', r'chain_mnist', r'paper_to_code', r'CWoLa', r'calo',
]

# ============================================================================
# Shutdown coordination
# ============================================================================

_shutdown = threading.Event()
_active_procs: Set[subprocess.Popen] = set()
_active_lock = threading.Lock()
_sigint_count = 0


def _sigint_handler(signum, frame):
    global _sigint_count
    _sigint_count += 1
    if _sigint_count == 1:
        print("\n[testbench] SIGINT received — finishing in-flight tasks and exiting…", flush=True)
        _shutdown.set()
        with _active_lock:
            for p in _active_procs:
                try:
                    p.terminate()
                except Exception:
                    pass
    else:
        print("\n[testbench] second SIGINT — killing now.", flush=True)
        with _active_lock:
            for p in _active_procs:
                try:
                    p.kill()
                except Exception:
                    pass
        os._exit(130)


signal.signal(signal.SIGINT, _sigint_handler)
signal.signal(signal.SIGTERM, _sigint_handler)


# ============================================================================
# Task model
# ============================================================================

@dataclass
class Task:
    group: str
    name: str                     # e.g. "sci_root_install"
    full: str                     # e.g. "sci_bench/sci_root_install"
    rank: int = 0
    gpu: str = ""                 # "", "no", "local", "on", "1".."4", "all", "ALL", "slurm"
    slurm: str = ""
    bash_time: str = ""
    skills: str = ""
    top_md: Path = field(default_factory=lambda: Path())


@dataclass
class BenchRow:
    iter_max: Optional[int]
    wall_max: Optional[float]
    pass_rate: str


@dataclass
class RunResult:
    status: str                   # "PASS" | "FAIL" | "UNKNOWN"
    iters: Optional[int]
    wall_s: Optional[float]
    caps: Dict[str, int]
    run_dir: str


# ============================================================================
# Parsing helpers
# ============================================================================

_FRONTMATTER_RE = re.compile(r'^\s*---\s*\n(.*?)\n---\s*\n', re.DOTALL)


def parse_frontmatter(path: Path) -> Dict[str, str]:
    try:
        text = path.read_text()
    except Exception:
        return {}
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        out[k.strip()] = v.strip()
    return out


def _int_or(val, default=0):
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return default


# ============================================================================
# Discovery
# ============================================================================

def discover_tasks(groups: List[str]) -> List[Task]:
    """Walk Sam/tasks/<group>/*/top.md and return Task list."""
    out: List[Task] = []
    for g in groups:
        gd = SAM_TASKS / g
        if not gd.is_dir():
            continue
        for td in sorted(gd.iterdir()):
            if not td.is_dir():
                continue
            top = td / "top.md"
            if not top.is_file():
                continue
            fm = parse_frontmatter(top)
            t = Task(
                group=g,
                name=td.name,
                full=f"{g}/{td.name}",
                rank=_int_or(fm.get('Rank'), 0),
                gpu=fm.get('GPU', '').lower(),
                slurm=fm.get('Slurm', '').lower(),
                bash_time=fm.get('BashTime', ''),
                skills=fm.get('Skills', ''),
                top_md=top,
            )
            out.append(t)
    return out


def load_benchmark(group: str) -> Dict[str, BenchRow]:
    """Read benchmark.csv for a group → {task_name: BenchRow}."""
    cols = BENCH_COLS.get(group)
    if cols is None:
        return {}
    f = SAM_TASKS / group / "benchmark.csv"
    if not f.is_file():
        return {}
    iter_col, wall_col, pass_col = cols
    out: Dict[str, BenchRow] = {}
    with f.open() as fh:
        rdr = csv.DictReader(fh)
        for row in rdr:
            tname = (row.get("task") or "").strip()
            if not tname:
                continue
            try:
                iter_max = int((row.get(iter_col) or "").strip())
            except ValueError:
                iter_max = None
            try:
                wall_max = float((row.get(wall_col) or "").strip())
            except ValueError:
                wall_max = None
            out[tname] = BenchRow(iter_max=iter_max, wall_max=wall_max,
                                  pass_rate=(row.get(pass_col) or "").strip())
    return out


# ============================================================================
# Host capabilities
# ============================================================================

def gpu_count() -> int:
    try:
        r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return 0
        return len([ln for ln in r.stdout.splitlines() if ln.strip()])
    except Exception:
        return 0


def has_slurm() -> bool:
    return shutil.which("sbatch") is not None


def gpu_required(task: Task) -> int:
    """0 = none. 1 = single. 2+ = multi. -1 = slurm-managed (not local)."""
    g = task.gpu
    if not g or g == "no":
        return 0
    if g == "local" or g == "1":
        return 1
    if g in ("2", "3", "4"):
        return int(g)
    if g in ("all", "on"):
        # "all" / "on" — conservatively require 2+
        return 2
    if g == "slurm":
        return -1
    # unknown value → treat as needing 1
    return 1


def skip_reason(task: Task, gpus: int, slurm_ok: bool) -> Optional[str]:
    # SLURM gate — either explicit Slurm: on or the NERSC_slurm skill
    needs_slurm = (task.slurm == "on") or ("NERSC_slurm" in task.skills)
    if needs_slurm and not slurm_ok:
        return "skipped_slurm"
    # GPU gate
    need = gpu_required(task)
    if need == -1:
        # SLURM-GPU managed — handled by the SLURM branch
        if not slurm_ok:
            return "skipped_slurm"
    elif need > gpus:
        return "skipped_multigpu" if need >= 2 else "skipped_no_gpu"
    # Missing-data guard for lhco (if task hasn't yet been patched to self-download)
    if task.full == "sci_study/lhco_CWoLa_VAE_detailed":
        # If data exists OR task has "download" in its Todo we let it run
        try:
            txt = task.top_md.read_text()
        except Exception:
            txt = ""
        has_data = (F_MNT / "lhco" / "data" / "features" / "features.npy").exists() and \
                   (F_MNT / "lhco" / "data" / "features" / "labels.npy").exists()
        describes_download = re.search(r'download|huggingface_hub|snapshot_download|curl|wget', txt, re.I)
        if not has_data and not describes_download:
            return "skipped_missing_data"
    return None


# ============================================================================
# Scheduler
# ============================================================================

def build_phases(tasks: List[Task]) -> List[List[Task]]:
    """Kahn's algorithm → list of phases (tasks in a phase can run concurrently)."""
    by_full = {t.full: t for t in tasks}
    # Only use deps where both endpoints are in our set
    indeg: Dict[str, int] = {t.full: 0 for t in tasks}
    children: Dict[str, List[str]] = {t.full: [] for t in tasks}
    for node, preds in DEPS.items():
        if node not in by_full:
            continue
        for p in preds:
            if p in by_full:
                indeg[node] += 1
                children[p].append(node)

    phases: List[List[Task]] = []
    ready = [f for f, d in indeg.items() if d == 0]
    done: Set[str] = set()
    while ready:
        phase = sorted(ready)
        phases.append([by_full[f] for f in phase])
        done.update(phase)
        next_ready = []
        for f in phase:
            for c in children[f]:
                indeg[c] -= 1
                if indeg[c] == 0:
                    next_ready.append(c)
        ready = next_ready
    # Detect cycle
    remaining = set(indeg) - done
    if remaining:
        raise RuntimeError(f"Dependency cycle involving: {sorted(remaining)}")
    return phases


def resource_class(task: Task) -> str:
    need = gpu_required(task)
    if need != 0:
        return "gpu"
    for pat in MEMHEAVY_PATTERNS:
        if re.search(pat, task.full, re.I):
            return "memheavy_cpu"
    return "cpu"


# ============================================================================
# CSV persistence
# ============================================================================

def _csv_init():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if not TESTING_CSV.exists():
        with TESTING_CSV.open("w", newline='') as f:
            csv.writer(f).writerow(CSV_HEADERS)


_csv_lock = threading.Lock()


def csv_append(row: Dict[str, object]):
    _csv_init()
    with _csv_lock:
        with TESTING_CSV.open("a", newline='') as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            w.writerow({k: row.get(k, "") for k in CSV_HEADERS})


def csv_load() -> List[Dict[str, str]]:
    if not TESTING_CSV.exists():
        return []
    with TESTING_CSV.open() as f:
        return list(csv.DictReader(f))


def last_verdict_for(task_full: str) -> Optional[str]:
    """Return verdict of most recent attempt for a task, or None."""
    rows = csv_load()
    latest = None
    for r in rows:
        if f"{r['group']}/{r['task']}" == task_full:
            latest = r
    return latest["verdict"] if latest else None


# ============================================================================
# SciF invocation + log parsing
# ============================================================================

def _log_path(task: Task, attempt: int) -> Path:
    d = LOGS_DIR / task.group
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{task.name}_try_{attempt}.log"


def _find_latest_run_dir(task: Task) -> str:
    base = F_TASKS / task.group
    if not base.is_dir():
        return ""
    cand = sorted(base.glob(f"{task.name}_*"))
    return cand[-1].name if cand else ""


def parse_log(log: Path) -> RunResult:
    run_dir = ""
    try:
        text = log.read_text(errors='ignore')
    except Exception:
        return RunResult("UNKNOWN", None, None, {}, run_dir)

    # Extract latest Result line
    iters = None
    wall = None
    m = re.search(r'=== Result \(([\d.]+)s, (\d+) iters', text)
    if m:
        wall = float(m.group(1))
        iters = int(m.group(2))

    # Determine status — robust to "trivial post skipped" case
    status = "UNKNOWN"
    if re.search(r'^DONE:', text, re.M) or re.search(r'^\[review\] PASS:', text, re.M):
        status = "PASS"
    elif re.search(r'^NOT DONE:|MAX_REVIEW_FAILURES', text, re.M):
        status = "FAIL"
    elif iters is not None:
        # Have Result line; check for fail markers
        fail_markers = re.search(r'failed|REJECT|NOT DONE|MAX_REVIEW_FAILURES', text)
        status = "FAIL" if fail_markers else "PASS"

    # Cap trips
    caps = {
        "WALL": len(re.findall(r'\[wall limit\] exceeded|WALL_LIMIT', text)),
        "ITER": len(re.findall(r'MAX_ITERATIONS \(\d+\) reached|LOOP_EXHAUSTED', text)),
        "TOTAL": len(re.findall(r'\[total wall limit\]|TOTAL_WALL_LIMIT', text)),
    }

    # run_dir from "[run] ... -> /path/..."
    rm = re.search(r'\[run\] \S+ -> \S*?/(\S+)', text)
    if rm:
        run_dir = rm.group(1)
    return RunResult(status, iters, wall, caps, run_dir)


def run_scif(task: Task, attempt: int, timeout_s: int) -> RunResult:
    log = _log_path(task, attempt)
    with log.open("w") as lf:
        proc = subprocess.Popen(
            [str(SCIF), "RUN", task.full],
            stdout=lf, stderr=subprocess.STDOUT,
            cwd=str(ROOT),
        )
        with _active_lock:
            _active_procs.add(proc)
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            print(f"[testbench] TIMEOUT {task.full} try={attempt} after {timeout_s}s — killing",
                  flush=True)
            proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        finally:
            with _active_lock:
                _active_procs.discard(proc)
    return parse_log(log)


# ============================================================================
# Classification + retry
# ============================================================================

def classify(res: RunResult, bench: Optional[BenchRow], slow_wall_mult: float,
             attempts_left: int, retry_on_slow: bool) -> str:
    if res.status == "FAIL":
        return "retry" if attempts_left > 0 else "fail_persistent"
    if res.status != "PASS":
        return "retry" if attempts_left > 0 else "fail_persistent"
    if bench is None:
        return "accepted"

    iter_bad = (bench.iter_max is not None and res.iters is not None
                and res.iters > bench.iter_max)
    wall_bad = (bench.wall_max is not None and res.wall_s is not None
                and res.wall_s > bench.wall_max * slow_wall_mult)

    if retry_on_slow and (iter_bad or wall_bad):
        return "retry" if attempts_left > 0 else "accepted_inflated"
    if iter_bad or wall_bad:
        return "accepted_inflated"
    return "accepted"


# ============================================================================
# Status reporter
# ============================================================================

class Monitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.running: Dict[str, float] = {}   # task_full -> start_time
        self.done = 0
        self.skipped = 0
        self.total_planned = 0
        self.phase_idx = 0
        self.phase_total = 0
        self.observed_walls: List[float] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, name="monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def set_phase(self, idx: int, total: int):
        with self.lock:
            self.phase_idx = idx
            self.phase_total = total

    def task_start(self, task_full: str):
        with self.lock:
            self.running[task_full] = time.time()

    def task_end(self, task_full: str, wall_s: Optional[float]):
        with self.lock:
            self.running.pop(task_full, None)
            self.done += 1
            if wall_s is not None:
                self.observed_walls.append(wall_s)

    def task_skip(self):
        with self.lock:
            self.skipped += 1

    def _eta(self) -> str:
        with self.lock:
            remaining = self.total_planned - self.done - self.skipped - len(self.running)
            if remaining < 0:
                remaining = 0
            walls = list(self.observed_walls)
        if not walls:
            return "?"
        walls.sort()
        median = walls[len(walls) // 2]
        # Effective parallelism ≈ 4 / 2 by class (rough)
        eff = max(1, 3)
        eta_s = int(remaining * median / eff)
        return f"~{eta_s // 3600}h{(eta_s % 3600) // 60:02d}m"

    def _run(self):
        start = time.time()
        while not self._stop.wait(60):
            with self.lock:
                running = dict(self.running)
                done = self.done
                skipped = self.skipped
                total = self.total_planned
                phase_idx = self.phase_idx
                phase_total = self.phase_total
            ts = datetime.now().strftime("%H:%M:%S")
            elapsed = int(time.time() - start)
            line = (f"[{ts}] done {done}/{total} | running {len(running)} | "
                    f"skipped {skipped} | phase {phase_idx}/{phase_total} | "
                    f"elapsed {elapsed // 3600}h{(elapsed % 3600) // 60:02d}m | "
                    f"ETA {self._eta()}")
            print(line, flush=True)
            for t, t0 in running.items():
                print(f"    running: {t} ({int(time.time() - t0)}s)", flush=True)


# ============================================================================
# Runner
# ============================================================================

class Runner:
    def __init__(self, args):
        self.args = args
        self.parallel = args.parallel
        self.max_retry = args.retry
        self.slow_mult = args.slow_wall_mult
        self.retry_on_slow = not args.no_retry_on_slow
        self.resume = args.resume
        self.monitor = Monitor()

    def _accepted_already(self, task_full: str) -> bool:
        if not self.resume:
            return False
        v = last_verdict_for(task_full)
        return v in ("accepted", "accepted_inflated")

    def _attempt_timeout(self, task: Task, bench: Optional[BenchRow]) -> int:
        # Use max(bench_wall_max × 5, 1800 + 600) as a watchdog
        base = 1800 + 600
        if bench and bench.wall_max:
            base = max(base, int(bench.wall_max * 5))
        return base

    def run_task(self, task: Task, bench: Optional[BenchRow]) -> str:
        if _shutdown.is_set():
            csv_append(dict(
                group=task.group, task=task.name, attempt=0, status="",
                iters="", wall_s="", iter_max=bench.iter_max if bench else "",
                wall_max=bench.wall_max if bench else "",
                bench_pass_rate=bench.pass_rate if bench else "",
                verdict="interrupted", caps_tripped="", run_dir="",
                timestamp=datetime.now().isoformat(timespec="seconds"),
            ))
            return "interrupted"

        if self._accepted_already(task.full):
            print(f"[skip] {task.full} — already accepted in testing.csv", flush=True)
            self.monitor.task_skip()
            return "accepted"

        self.monitor.task_start(task.full)
        timeout_s = self._attempt_timeout(task, bench)
        final_verdict = "fail_persistent"
        for attempt in range(1, self.max_retry + 1):
            if _shutdown.is_set():
                final_verdict = "interrupted"
                break
            print(f"[run] {task.full} try={attempt}/{self.max_retry}", flush=True)
            t0 = time.time()
            res = run_scif(task, attempt, timeout_s)
            attempt_wall = time.time() - t0

            if not res.run_dir:
                res.run_dir = _find_latest_run_dir(task)

            attempts_left = self.max_retry - attempt
            verdict = classify(res, bench, self.slow_mult, attempts_left, self.retry_on_slow)
            caps_str = ",".join(f"{k}={v}" for k, v in res.caps.items() if v) or ""
            csv_append(dict(
                group=task.group, task=task.name, attempt=attempt, status=res.status,
                iters=res.iters if res.iters is not None else "",
                wall_s=f"{res.wall_s:.1f}" if res.wall_s is not None else f"{attempt_wall:.1f}",
                iter_max=bench.iter_max if bench and bench.iter_max is not None else "",
                wall_max=bench.wall_max if bench and bench.wall_max is not None else "",
                bench_pass_rate=bench.pass_rate if bench else "",
                verdict=verdict, caps_tripped=caps_str, run_dir=res.run_dir,
                timestamp=datetime.now().isoformat(timespec="seconds"),
            ))
            final_verdict = verdict
            if verdict in ("accepted", "accepted_inflated", "fail_persistent", "interrupted"):
                break
            # else: retry
        self.monitor.task_end(task.full, None)
        print(f"[done] {task.full} -> {final_verdict}", flush=True)
        return final_verdict

    def run_phase(self, phase: List[Task], bench_by_group: Dict[str, Dict[str, BenchRow]]):
        """Tasks in the phase split by resource class; each class has its own semaphore."""
        classes: Dict[str, List[Task]] = {"gpu": [], "memheavy_cpu": [], "cpu": []}
        for t in phase:
            classes[resource_class(t)].append(t)

        # Caps per class
        caps = {"gpu": 1, "memheavy_cpu": 2, "cpu": self.parallel}

        def _run_one(t: Task) -> None:
            bench = bench_by_group.get(t.group, {}).get(t.name)
            self.run_task(t, bench)

        pools = []
        for cls, ts in classes.items():
            if not ts:
                continue
            pool = ThreadPoolExecutor(max_workers=caps[cls], thread_name_prefix=cls)
            futs = [pool.submit(_run_one, t) for t in ts]
            pools.append((pool, futs))

        # Wait all
        try:
            for _, futs in pools:
                for fut in futs:
                    fut.result()
        finally:
            for pool, _ in pools:
                pool.shutdown(wait=False, cancel_futures=False)

    def run(self, groups: List[str]):
        tasks_all = discover_tasks(groups)

        # Skip decisions
        gc = gpu_count()
        sl = has_slurm()
        print(f"[testbench] host caps: gpu_count={gc}, sbatch={sl}", flush=True)

        runnable: List[Task] = []
        for t in tasks_all:
            r = skip_reason(t, gc, sl)
            if r:
                bench_by_group = load_benchmark(t.group)
                b = bench_by_group.get(t.name)
                csv_append(dict(
                    group=t.group, task=t.name, attempt=0, status="",
                    iters="", wall_s="",
                    iter_max=b.iter_max if b and b.iter_max is not None else "",
                    wall_max=b.wall_max if b and b.wall_max is not None else "",
                    bench_pass_rate=b.pass_rate if b else "",
                    verdict=r, caps_tripped="", run_dir="",
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                ))
                self.monitor.task_skip()
                print(f"[skip] {t.full} -> {r}", flush=True)
            else:
                runnable.append(t)

        phases = build_phases(runnable)
        bench_by_group = {g: load_benchmark(g) for g in GROUPS}

        total = sum(len(p) for p in phases)
        self.monitor.total_planned = total
        self.monitor.start()

        try:
            for i, phase in enumerate(phases, 1):
                self.monitor.set_phase(i, len(phases))
                print(f"\n[phase {i}/{len(phases)}] {len(phase)} tasks: "
                      f"{', '.join(t.full for t in phase)}", flush=True)
                self.run_phase(phase, bench_by_group)
                if _shutdown.is_set():
                    print("[testbench] shutdown requested — stopping after this phase", flush=True)
                    break
        finally:
            self.monitor.stop()
        print("[testbench] run complete.", flush=True)


# ============================================================================
# plan / clean / report
# ============================================================================

def cmd_plan(args):
    tasks = discover_tasks(args.groups)
    gc = gpu_count()
    sl = has_slurm()
    print(f"host caps: gpu_count={gc}, sbatch={sl}")
    runnable = []
    for t in tasks:
        r = skip_reason(t, gc, sl)
        if r:
            print(f"  SKIP {t.full:50s} -> {r}")
        else:
            runnable.append(t)
    phases = build_phases(runnable)
    print(f"\nphases: {len(phases)}")
    for i, p in enumerate(phases, 1):
        tags = []
        for t in p:
            tags.append(f"{t.full} [{resource_class(t)}, rank={t.rank}]")
        print(f"  phase {i} ({len(p)}):")
        for tag in tags:
            print(f"    {tag}")


def cmd_clean(args):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    trash = DELETED / f"env_{ts}"
    (trash / "mnt").mkdir(parents=True, exist_ok=True)
    (trash / "home").mkdir(parents=True, exist_ok=True)
    # F/mnt — keep sci_shared/seed.txt
    if F_MNT.is_dir():
        for item in list(F_MNT.iterdir()):
            if item.name == "sci_shared":
                (trash / "mnt" / "sci_shared").mkdir(parents=True, exist_ok=True)
                for sub in list(item.iterdir()):
                    if sub.name != "seed.txt":
                        shutil.move(str(sub), str(trash / "mnt" / "sci_shared" / sub.name))
            else:
                shutil.move(str(item), str(trash / "mnt" / item.name))
    # F/home — keep .ssh + .gitkeep
    if F_HOME.is_dir():
        for item in list(F_HOME.iterdir()):
            if item.name in (".ssh", ".gitkeep"):
                continue
            shutil.move(str(item), str(trash / "home" / item.name))
    # Ensure .deleted is gitignored
    gi = ROOT / ".gitignore"
    if gi.is_file():
        txt = gi.read_text()
        if ".deleted/" not in txt and ".deleted" not in txt.splitlines():
            with gi.open("a") as f:
                f.write("\n# testbench cleanup trash\n.deleted/\n")
    print(f"[clean] moved runtime env to {trash}")
    print(f"[clean] F/mnt/:", list(F_MNT.iterdir()) if F_MNT.is_dir() else "(missing)")
    print(f"[clean] F/home/:", [p.name for p in F_HOME.iterdir()] if F_HOME.is_dir() else "(missing)")


def cmd_report(args):
    rows = csv_load()
    if not rows:
        print("no testing.csv rows yet.")
        return
    # Most recent row per task
    latest: Dict[str, Dict[str, str]] = {}
    for r in rows:
        key = f"{r['group']}/{r['task']}"
        latest[key] = r
    fail_count = 0
    for g in GROUPS:
        rows_g = [(k, v) for k, v in latest.items() if v['group'] == g]
        if not rows_g:
            continue
        print(f"\n=== {g} ({len(rows_g)} tasks) ===")
        print(f"  {'task':40s} {'verdict':22s} {'iters':>6s}/{'max':>6s}  {'wall':>6s}/{'max':>6s}  caps")
        for key, v in sorted(rows_g):
            verdict = v['verdict']
            if verdict == 'fail_persistent':
                fail_count += 1
            iters = v.get('iters') or ''
            iter_max = v.get('iter_max') or ''
            wall = v.get('wall_s') or ''
            wall_max = v.get('wall_max') or ''
            caps = v.get('caps_tripped') or ''
            name = v['task']
            print(f"  {name:40s} {verdict:22s} {iters:>6s}/{iter_max:>6s}  {wall:>6s}/{wall_max:>6s}  {caps}")
    print(f"\n[summary] fail_persistent={fail_count}")
    sys.exit(1 if fail_count else 0)


# ============================================================================
# Entrypoint
# ============================================================================

def check_gateway() -> bool:
    try:
        env = os.environ.copy()
        # Need BASEDIR etc. — source ENV.sh for the check
        cmd = f"source {ROOT}/ENV.sh && bash {GATEWAY_SH} status"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
        return ("Gateway running" in r.stdout) or ("Health: OK" in r.stdout)
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(prog="testbench.py")
    sub = ap.add_subparsers(dest="mode", required=True)

    run = sub.add_parser("run", help="execute the sweep")
    run.add_argument("--groups", default=",".join(GROUPS),
                     help="comma-separated group list (default: all)")
    run.add_argument("--parallel", type=int, default=4)
    run.add_argument("--retry", type=int, default=3)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--no-retry-on-slow", action="store_true")
    run.add_argument("--slow-wall-mult", type=float, default=3.0)

    plan = sub.add_parser("plan", help="print the schedule without running")
    plan.add_argument("--groups", default=",".join(GROUPS))

    sub.add_parser("clean", help="mv runtime env to .deleted/")
    sub.add_parser("report", help="print comparison table from testing.csv")

    args = ap.parse_args()
    if args.mode in ("run", "plan"):
        args.groups = [g.strip() for g in args.groups.split(",") if g.strip()]

    if args.mode == "run":
        if not check_gateway():
            print("[testbench] WARNING: gateway not running or unhealthy. Start with:")
            print("  source ENV.sh && bash Pam/gateway.sh start")
            sys.exit(2)
        Runner(args).run(args.groups)
    elif args.mode == "plan":
        cmd_plan(args)
    elif args.mode == "clean":
        cmd_clean(args)
    elif args.mode == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
