#!/usr/bin/env python3
"""bilevel_ana helper: deterministic metric digest of a finished bilevel run.

Reads the inner-loop outputs under <run>/results/ (summary.json, landscape
npz files, plus ../sim_outputs/manifest.json for the event count) and prints
a SHORT, fixed-format digest the agent can interpret. The agent must NOT
parse summary.json / npz files itself -- it runs this script once and reads
the digest.

Output protocol (stdout):
    ANA_DIGEST_BEGIN
    ... fixed-format digest lines ...
    ANA_DIGEST_END
    ANA_OK geometries=<N> best_score=<S>      on success
or
    ANA_FAIL <reason>                          on failure (exit 1)

What the digest contains:
  * run metadata (algorithm, score function, optimizer, events/geometry)
  * score statistics + statistical-noise estimate. Two estimates are shown:
      - model_sigma ~ 0.30/sqrt(events) (matches a naive Poisson-like scaling:
        100 ev -> 0.030, 500 -> 0.013, 1000 -> 0.010)
      - empirical_floor: scatter measured from the run's OWN flattest swept
        axis. Each geometry has a deterministic per-geometry seed, so the
        model_sigma is ~6x too conservative in practice (near-identical
        geometries scatter by ~0.002-0.005, not ~0.030). The empirical floor
        captures this. The significance line / marginal thresholds use
        sigma_eff = empirical_floor when it is available (>=3 usable adjacent
        differences), else model_sigma.
  * global best geometry + reco params, top-3 ranking, best-vs-second gap
  * per-reco-param bound-pinning check against the brute grid
    (PINNED_LOW / PINNED_HIGH / INTERIOR)
  * per-swept-geometry-parameter marginal mean scores + trend classification
    (FLAT / RISES / FALLS / PEAKED, threshold = 2 * sigma_eff / sqrt(n_per_value))
  * count of -inf landscape cells (param combos where reconstruction failed)
"""
from __future__ import print_function

import argparse
import glob
import json
import math
import os
import re
import sys

try:
    import numpy as np
except ImportError:  # degrade: no grid/pinning/failed-cell info
    np = None

# Measured score std vs events/geometry (driver/README.md table) ~ 0.30/sqrt(N)
NOISE_COEFF = 0.30
# Minimum number of usable adjacent score differences for an empirical floor.
MIN_EMP_POINTS = 3


def fail(reason):
    print("ANA_FAIL %s" % reason)
    sys.exit(1)


def fmt(x):
    """Compact number: 15.0 -> 15, 0.8782412 -> 0.8782."""
    if isinstance(x, float) and x == int(x) and abs(x) < 1e6:
        return "%d" % int(x)
    return "%.4g" % x


def load_summary(results_dir):
    path = os.path.join(results_dir, "summary.json")
    if not os.path.isfile(path):
        fail("no summary.json in %s (inner stage not run?)" % results_dir)
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception as exc:
        fail("cannot parse summary.json: %s" % exc)


def find_events(results_dir, override):
    """Events per geometry: --events flag, else parse the ddsim manifest."""
    if override:
        return override
    manifest = os.path.join(os.path.dirname(os.path.abspath(results_dir)),
                            "sim_outputs", "manifest.json")
    if not os.path.isfile(manifest):
        return None
    try:
        with open(manifest) as fh:
            entry = json.load(fh)[0]
    except Exception:
        return None
    m = re.search(r"-N\s+(\d+)", entry.get("ddsim_cmd", ""))
    if m:
        return int(m.group(1))
    m = re.search(r"_N(\d+)\b", entry.get("description", ""))
    return int(m.group(1)) if m else None


def load_grids(results_dir):
    """Brute-search grids per reco param, from any landscape_*.npz."""
    if np is None:
        return {}
    files = sorted(glob.glob(os.path.join(results_dir, "landscape_*.npz")))
    if not files:
        return {}
    try:
        data = np.load(files[0])
    except Exception:
        return {}
    return {k[len("grid_"):]: data[k] for k in data.files if k.startswith("grid_")}


def count_failed_cells(results_dir):
    """(-inf cells, total cells) in the full loss-landscape tensor."""
    if np is None:
        return None
    path = os.path.join(results_dir, "loss_landscape_tensor.npz")
    if not os.path.isfile(path):
        return None
    try:
        score = np.load(path)["score"]
    except Exception:
        return None
    return int(np.isneginf(score).sum()), int(score.size)


def _median(xs):
    """Median of a non-empty list (stdlib, py3.6 safe)."""
    s = sorted(xs)
    m = len(s)
    mid = m // 2
    if m % 2:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])


def empirical_floor(geoms, scores, swept):
    """Empirical noise floor from the flattest swept axis.

    For each swept geometry parameter (axis), group geometries by the OTHER
    swept parameters so each group is a 1-D scan along that axis. Within each
    group, take the absolute score difference between adjacent values along
    the axis (sorted). Pool these |delta| over all groups for the axis: their
    median / sqrt(2) estimates the per-geometry score scatter if the axis were
    physically flat (a single-step difference of two independent same-noise
    measurements has std sigma*sqrt(2)).

    The chosen floor is the SMALLEST such estimate across axes (the flattest
    axis is the one least contaminated by real physics), provided that axis
    has >= MIN_EMP_POINTS pooled differences. Returns
        (axis_name, floor, n_diffs)  or  None  when no axis qualifies.
    """
    best = None
    for axis in sorted(swept):
        others = [k for k in swept if k != axis]
        groups = {}
        for g, s in zip(geoms, scores):
            if math.isinf(s):
                continue
            key = tuple(round(float(g["geom_values"][k]), 9) for k in others)
            groups.setdefault(key, []).append((float(g["geom_values"][axis]), s))
        diffs = []
        for pts in groups.values():
            pts.sort()
            for (_a, sa), (_b, sb) in zip(pts, pts[1:]):
                diffs.append(abs(sb - sa))
        if len(diffs) < MIN_EMP_POINTS:
            continue
        floor = _median(diffs) / math.sqrt(2.0)
        if best is None or floor < best[1]:
            best = (axis, floor, len(diffs))
    return best


def pinning(values, grid):
    """Classify best-param values against the search grid bounds."""
    n = len(values)
    if grid is None or len(grid) == 0:
        return "bounds unknown (no landscape npz)", "UNKNOWN", None, None
    lo, hi = float(grid[0]), float(grid[-1])
    tol = 1e-9 + 1e-6 * max(abs(lo), abs(hi))
    n_lo = sum(1 for v in values if abs(v - lo) <= tol)
    n_hi = sum(1 for v in values if abs(v - hi) <= tol)
    detail = "bounds[%s,%s] grid%d | %d/%d at min, %d/%d at max" % (
        fmt(lo), fmt(hi), len(grid), n_lo, n, n_hi, n)
    if n_lo == n:
        tag = "PINNED_LOW"
    elif n_hi == n:
        tag = "PINNED_HIGH"
    elif n_lo >= 0.75 * n:
        tag = "MOSTLY_PINNED_LOW"
    elif n_hi >= 0.75 * n:
        tag = "MOSTLY_PINNED_HIGH"
    else:
        tag = "INTERIOR"
    return detail, tag, lo, hi


def pinning_note(name, tag, lo):
    """Deterministic next-iteration recommendation for a pinned parameter.

    The agent copies these into its Conclusion — encoding the domain decision
    here keeps weak models from recommending the wrong fix (e.g. lowering the
    R bound when the small-cluster degeneracy is the real cause)."""
    if tag in ("UNKNOWN", "INTERIOR") or lo is None:
        return None
    low = tag.endswith("PINNED_LOW")
    if name == "R_cluster_mm" and low:
        if lo < 10.0:
            return ("known snr_energy small-cluster degeneracy -> next iteration "
                    "constrain R to a physical range (e.g. 20-150 mm); R value not "
                    "physically meaningful, geometry ranking still usable")
        return ("degeneracy persists at the physical bound -> do NOT lower the R "
                "bound; next iteration switch to a containment-aware score; R value "
                "not physically meaningful, geometry ranking still usable")
    return ("optimum sits at the search bound -> widen the %s bound next iteration"
            % ("lower" if low else "upper"))


def trend(means_by_value, thresh):
    """FLAT / RISES / FALLS / PEAKED@v for marginal mean scores."""
    vals = sorted(means_by_value)
    means = [means_by_value[v] for v in vals]
    rng = max(means) - min(means)
    if rng < thresh:
        return "FLAT", rng
    nondec = all(b >= a for a, b in zip(means, means[1:]))
    noninc = all(b <= a for a, b in zip(means, means[1:]))
    if nondec:
        return "RISES", rng
    if noninc:
        return "FALLS", rng
    peak = vals[means.index(max(means))]
    return "PEAKED@%s" % fmt(peak), rng


def main():
    ap = argparse.ArgumentParser(description="Digest a bilevel run's results.")
    ap.add_argument("--results", required=True,
                    help="results dir, e.g. /srv/runs/<NAME>/results "
                         "(the run dir itself is also accepted)")
    ap.add_argument("--events", type=int, default=None,
                    help="events per geometry (default: parsed from manifest)")
    args = ap.parse_args()

    results_dir = args.results.rstrip("/")
    if not os.path.isfile(os.path.join(results_dir, "summary.json")) and \
            os.path.isfile(os.path.join(results_dir, "results", "summary.json")):
        results_dir = os.path.join(results_dir, "results")

    summary = load_summary(results_dir)
    meta = summary.get("meta", {})
    geoms = summary.get("per_geometry", [])
    gbest = summary.get("global_best", {})
    if not geoms:
        fail("summary.json has no per_geometry entries")
    n = len(geoms)
    opt_names = meta.get("optimize_params", [])

    # swept vs fixed geometry parameters
    geom_vals = {}
    for g in geoms:
        for k, v in g.get("geom_values", {}).items():
            geom_vals.setdefault(k, []).append(float(v))
    swept = {k: sorted(set(v)) for k, v in geom_vals.items() if len(set(v)) > 1}
    fixed = {k: v[0] for k, v in geom_vals.items() if len(set(v)) == 1}

    # score statistics
    scores = [float(g["best_score"]) for g in geoms]
    finite = [s for s in scores if not math.isinf(s)]
    if not finite:
        fail("all %d best_score values are non-finite" % n)
    mean = sum(finite) / len(finite)
    std = math.sqrt(sum((s - mean) ** 2 for s in finite) / len(finite))
    order = sorted(range(n), key=lambda i: scores[i], reverse=True)
    best, worst = scores[order[0]], scores[order[-1]]
    second = scores[order[1]] if n > 1 else best
    spread = best - worst

    events = find_events(results_dir, args.events)
    model_sigma = NOISE_COEFF / math.sqrt(events) if events else None

    # empirical noise floor from the run's own flattest swept axis
    emp = empirical_floor(geoms, scores, swept)

    # effective sigma used for significance + marginal thresholds: prefer the
    # empirical floor when defensible, else fall back to the model.
    if emp is not None:
        sigma_eff = emp[1]
        sigma_src = "empirical"
    elif model_sigma is not None:
        sigma_eff = model_sigma
        sigma_src = "model"
    else:
        sigma_eff = None
        sigma_src = "none"

    grids = load_grids(results_dir)
    failed = count_failed_cells(results_dir)

    run_name = os.path.basename(os.path.dirname(os.path.abspath(results_dir)))

    def swept_str(g):
        return " ".join("%s=%s" % (k, fmt(float(g["geom_values"][k])))
                        for k in sorted(swept))

    lines = []
    lines.append("run: %s   algo: %s   score_fn: %s   method: %s" % (
        run_name, meta.get("algo", "?"), meta.get("score", "?"),
        meta.get("optimize_method", "?")))
    lines.append("geometries: %d   events_per_geom: %s   noise_sigma: %s" % (
        n, events if events else "unknown",
        "%.4f" % sigma_eff if sigma_eff else "unknown"))
    if fixed:
        lines.append("fixed_geometry: " + " ".join(
            "%s=%s" % (k, fmt(v)) for k, v in sorted(fixed.items())))
    if swept:
        lines.append("swept_geometry: " + " ".join(
            "%s=[%s]" % (k, ",".join(fmt(x) for x in v))
            for k, v in sorted(swept.items())))
    lines.append("score: best=%.4f second=%.4f worst=%.4f mean=%.4f "
                 "std=%.4f spread=%.4f" % (best, second, worst, mean, std, spread))
    # explicit noise line: always show both estimates and which one is used
    model_str = "%.4f" % model_sigma if model_sigma is not None else "unknown"
    if emp is not None:
        emp_str = ("empirical_floor=%.4f (flattest-axis scatter on %s, n=%d)"
                   % (emp[1], emp[0], emp[2]))
    else:
        emp_str = ("empirical_floor=unavailable (<%d usable points)"
                   % MIN_EMP_POINTS)
    lines.append("noise: model_sigma=%s | %s -> using %s sigma_eff=%s" % (
        model_str, emp_str, sigma_src,
        "%.4f" % sigma_eff if sigma_eff is not None else "unknown"))
    if sigma_eff:
        gap_sig = (best - second) / (sigma_eff * math.sqrt(2)) if n > 1 else 0.0
        lines.append("significance: spread=%.1f sigma | best_vs_second=%.1f sigma"
                     " -> %s" % (spread / sigma_eff, gap_sig,
                                 "SIGNIFICANT" if gap_sig >= 2 else "NOT significant"))
    bp = gbest.get("best_params", {})
    lines.append("global_best: %s | %s | score=%.4f" % (
        " ".join("%s=%s" % (k, fmt(float(v)))
                 for k, v in sorted(gbest.get("geom_values", {}).items())
                 if k in swept) or "(single geometry)",
        " ".join("%s=%s" % (k, fmt(float(bp[k]))) for k in opt_names if k in bp),
        float(gbest.get("best_score", best))))
    lines.append("top3:")
    for r, i in enumerate(order[:3], 1):
        g = geoms[i]
        lines.append("  %d. %s | %s | score=%.4f" % (
            r, swept_str(g) or "(single geometry)",
            " ".join("%s=%s" % (k, fmt(float(g["best_params"][k])))
                     for k in opt_names if k in g.get("best_params", {})),
            scores[i]))
    lines.append("reco_params:")
    for name in opt_names:
        vals = [float(g["best_params"][name]) for g in geoms
                if name in g.get("best_params", {})]
        counts = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        val_str = " ".join("%s:%d/%d" % (fmt(v), c, n)
                           for v, c in sorted(counts.items()))
        detail, tag, lo, _hi = pinning(vals, grids.get(name))
        lines.append("  %s: %s | best values {%s} | %s" % (name, detail, val_str, tag))
        note = pinning_note(name, tag, lo)
        if note:
            lines.append("    note: %s" % note)
    if swept:
        lines.append("marginals (mean score per swept value):")
        for name, values in sorted(swept.items()):
            by_val = {}
            for g, s in zip(geoms, scores):
                if math.isinf(s):
                    continue
                by_val.setdefault(float(g["geom_values"][name]), []).append(s)
            means = {v: sum(ss) / len(ss) for v, ss in by_val.items()}
            n_min = min(len(ss) for ss in by_val.values())
            thresh = 2 * sigma_eff / math.sqrt(n_min) if sigma_eff else 0.01
            tag, rng = trend(means, thresh)
            lines.append("  %s: %s | range=%.4f thresh=%.4f | %s" % (
                name,
                " ".join("%s=%.4f" % (fmt(v), means[v]) for v in sorted(means)),
                rng, thresh, tag))
    if failed:
        ninf, total = failed
        lines.append("failed_cells: %d/%d landscape grid points are -inf "
                     "(reconstruction kept no events there)" % (ninf, total))

    print("ANA_DIGEST_BEGIN")
    for ln in lines:
        print(ln)
    print("ANA_DIGEST_END")
    print("ANA_OK geometries=%d best_score=%.4f" % (n, best))
    return 0


if __name__ == "__main__":
    sys.exit(main())
