#!/usr/bin/env python3
"""Summarise a bench phase from its per-plan JSON reports.

Usage:
    summarize_phase.py <prefix> [<prefix2> ...]

Examples:
    summarize_phase.py fw_phase2_
    summarize_phase.py fw_phase2_ fw_phase2x_         # cross-phase comparison

Reads tools/bench/results/*.json (written by bench.py at end of each plan run).
For each plan matching <prefix>, aggregates per-batch n_pass / n_runs / wall.
Writes a markdown report to tools/bench/results/<prefix>summary.md and prints to stdout.

The cam-derived verdicts are trusted: SAM_VERIFIED in-container is the same as
running verify_golden.py from outside (the reviewer ran it already). Any cam-PASS
that looks anomalous can be spot-verified by re-running sim/verify_golden.py in
the task dir manually — but for aggregate stats we use the cam verdicts.
"""
import sys, os, json, glob, statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")


def load_phase(prefix):
    """Return list of bench reports whose plan name starts with <prefix>."""
    out = []
    for path in sorted(glob.glob(os.path.join(RESULTS, "*.json"))):
        try:
            r = json.load(open(path))
        except Exception:
            continue
        if r.get("plan", "").startswith(prefix):
            r["_path"] = path
            out.append(r)
    return out


def fmt_pct(n, d):
    return f"{n}/{d} ({100*n/d:.0f}%)" if d else "n/a"


def fmt_min(s):
    if s is None:
        return "n/a"
    return f"{s/60:.1f}m"


def summarise_phase(prefix):
    reports = load_phase(prefix)
    if not reports:
        return f"## {prefix}: no reports found in {RESULTS}\n"
    lines = [f"## Phase: `{prefix}` — {len(reports)} plans"]
    total_pass = total_runs = 0
    plan_rows = []
    for r in reports:
        plan = r["plan"]
        for b in r.get("batches", []):
            if not b.get("name", "").startswith("c1_"):
                continue
            n_runs = b.get("n_runs", 0)
            n_pass = b.get("n_pass", 0)
            iters_p50 = b.get("iters_p50")
            wall_p50 = b.get("wall_p50")
            plan_rows.append({
                "plan": plan, "batch": b["name"],
                "n_runs": n_runs, "n_pass": n_pass,
                "iters_p50": iters_p50, "wall_p50": wall_p50,
            })
            total_pass += n_pass
            total_runs += n_runs
    lines.append("")
    lines.append("| plan | batch | n_runs | n_pass | iters_p50 | wall_p50 |")
    lines.append("|---|---|---|---|---|---|")
    for row in plan_rows:
        lines.append(f"| {row['plan']} | {row['batch']} | {row['n_runs']} "
                     f"| {row['n_pass']} | {row['iters_p50']} | {fmt_min(row['wall_p50'])} |")
    lines.append("")
    lines.append(f"**Aggregate (c1 batches only): {fmt_pct(total_pass, total_runs)} PASS**")
    # Per-model aggregate
    by_model = defaultdict(lambda: {"runs": 0, "pass": 0})
    for row in plan_rows:
        # plan name format: fw_phaseN[xt]_<model>
        model = row["plan"].split("_", 2)[-1]  # rough
        by_model[model]["runs"] += row["n_runs"]
        by_model[model]["pass"] += row["n_pass"]
    lines.append("")
    lines.append("**By model:**")
    for m, d in by_model.items():
        lines.append(f"- {m}: {fmt_pct(d['pass'], d['runs'])}")
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)
    prefixes = sys.argv[1:]
    body = "# Phase Summary\n\n"
    for p in prefixes:
        body += summarise_phase(p) + "\n"

    # If two prefixes, write a side-by-side row count delta
    if len(prefixes) == 2:
        a, b = [load_phase(p) for p in prefixes]
        if a and b:
            body += "\n## Cross-phase delta\n\n"
            def total(reports):
                tp = tr = 0
                for r in reports:
                    for ba in r.get("batches", []):
                        if ba.get("name", "").startswith("c1_"):
                            tp += ba.get("n_pass", 0)
                            tr += ba.get("n_runs", 0)
                return tp, tr
            ap, ar = total(a)
            bp, br = total(b)
            body += f"- {prefixes[0]}: {fmt_pct(ap, ar)}\n"
            body += f"- {prefixes[1]}: {fmt_pct(bp, br)}\n"
            if ar and br:
                delta = (bp/br - ap/ar) * 100
                body += f"- delta (B - A): {delta:+.1f} pp\n"

    out_path = os.path.join(RESULTS, prefixes[0].rstrip("_") + "_summary.md")
    open(out_path, "w").write(body)
    print(body)
    print(f"\n[written] {out_path}")


if __name__ == "__main__":
    main()
