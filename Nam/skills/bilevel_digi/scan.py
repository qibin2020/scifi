#!/usr/bin/env python3
"""bilevel_digi helper: (Sa x N) readout scan + deterministic digest.

Scans a grid of sampling rates (Sa, GHz) and ADC bit depths (N) on the cached
ROOT outputs of a COMPLETED bilevel run (no new simulation), then prints a
SHORT fixed-format digest. The agent must NOT parse digi_scan.csv itself --
it runs this script once and reads the digest.

Output protocol (stdout):
    DIGI_DIGEST_BEGIN
    ... fixed-format digest lines ...
    DIGI_DIGEST_END
    DIGI_VERIFIED run=<RUN> points=<P> best_serr=<x>      on success
or
    DIGI_FAIL <reason>                                     on failure (exit 1)

Idempotent: a completed scan writes <rundir>/results/.digi_scan_verified with
the grid signature; re-running with the same grid re-prints the digest from
the existing CSV without recomputing (FORCE=1 recomputes). The scan itself is
deterministic (per-(geometry,Sa) seeds), so recomputation is bit-identical.

What the digest contains:
  * the grid and unit caps used
  * global_best_cell: the (Sa,N) cell with the lowest MEAN s_error over all
    geometries (pooling removes per-geometry noise), with its mean ADC power
  * best_single: the single best (geometry, Sa, N) row, for reference
  * compliance: how many cells meet the campaign requirement s_err <= 2%
  * operating_point: lowest-power compliant cell -- THE recommended readout
  * geometry_coupling: whether the best (Sa,N) depends on geometry
  * trend_vs_Sa / trend_vs_N marginal tags (FLAT / RISES / FALLS / PEAKED@v)
  * deterministic `note:` recommendation lines the agent copies verbatim
"""
from __future__ import print_function

import argparse
import csv
import json
import math
import os
import sys

# Campaign requirement (constrained-Pareto objective): s_error <= 2%.
S_ERR_REQUIREMENT = 0.02
# FLAT threshold for marginal trends (absolute, on the s_error fraction).
TREND_THRESH = 0.005
# Combined metric (scale-free in the inner score, so it works for snr_energy,
# energy_resolution, or any future score without recalibration):
#     J = score * (1 - s_err) * (1 W / power)^LAMBDA_P
# A multiplicative power-law penalty -> the power term is a FRACTION of the
# score regardless of its absolute scale. LAMBDA_P=0.02 ~ 4.7% discount per
# power decade; tune against the first epoch's real numbers if needed.
LAMBDA_P = 0.02
POWER_REF_MW = 1000.0  # 1 W reference
# FLAT threshold for J trends (J is on the snr scale; plateau noise ~0.002-6).
J_TREND_THRESH = 0.005

METRIC_COLS = ("sa_GHz", "adc_bits", "channel", "s_error", "c_error",
               "power_mw", "n_crystals", "n_units_fit", "chi2_reject_frac",
               "seed")


def fail(reason):
    print("DIGI_FAIL %s" % reason)
    sys.exit(1)


def fmt(x):
    if isinstance(x, float) and x == int(x) and abs(x) < 1e6:
        return "%d" % int(x)
    return "%.4g" % x


def fmt_pct(frac):
    return "inf" if math.isinf(frac) else "%.2f%%" % (100.0 * frac)


def fmt_w(mw):
    return "%.3g W" % (mw / 1000.0)


def trend(means_by_value, thresh):
    """FLAT / RISES / FALLS / PEAKED@v for marginal mean s_error (lower=better).

    RISES/FALLS describe s_error vs the increasing parameter value."""
    vals = sorted(means_by_value)
    means = [means_by_value[v] for v in vals]
    finite = [m for m in means if not math.isinf(m)]
    if not finite:
        return "ALL_FAILED", 0.0
    rng = max(finite) - min(finite)
    if rng < thresh and len(finite) == len(means):
        return "FLAT", rng
    nondec = all(b >= a for a, b in zip(means, means[1:]))
    noninc = all(b <= a for a, b in zip(means, means[1:]))
    if nondec:
        return "RISES", rng
    if noninc:
        return "FALLS", rng
    best_v = vals[means.index(min(means))]
    return "PEAKED@%s" % fmt(best_v), rng


def trend_hi(means_by_value, thresh):
    """FLAT / RISES / FALLS / PEAKED@v for a higher-is-better quantity (J)."""
    vals = sorted(means_by_value)
    means = [means_by_value[v] for v in vals]
    finite = [m for m in means if not math.isinf(m)]
    if not finite:
        return "ALL_FAILED", 0.0
    rng = max(finite) - min(finite)
    if rng < thresh and len(finite) == len(means):
        return "FLAT", rng
    nondec = all(b >= a for a, b in zip(means, means[1:]))
    noninc = all(b <= a for a, b in zip(means, means[1:]))
    if nondec:
        return "RISES", rng
    if noninc:
        return "FALLS", rng
    best_v = vals[means.index(max(means))]
    return "PEAKED@%s" % fmt(best_v), rng


def load_snr_map(rundir, geom_keys):
    """Per-geometry best inner-loop score from the sibling summary.json.

    Returns (map, score_name) where map is
    {tuple(str(geom value) for geom_keys): best_score}, or (None, None).
    Works for any score (snr_energy, energy_resolution, ...) — J is scale-free."""
    path = os.path.join(rundir, "results", "summary.json")
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path) as fh:
            summary = json.load(fh)
        score_name = summary.get("meta", {}).get("score", "score")
        out = {}
        for g in summary.get("per_geometry", []):
            gv = g.get("geom_values", {})
            key = tuple("%g" % float(gv[k]) for k in geom_keys)
            out[key] = float(g["best_score"])
        return (out, score_name) if out else (None, None)
    except (ValueError, KeyError, TypeError, IOError, OSError):
        return None, None


def combined_digest(rows, snr_map, geom_keys, score_name="score", results_dir=None):
    """Scale-free combined metric J = score*(1-s_err)*(1W/power)^LAMBDA_P.

    `score` is the inner-loop best_score (snr_energy or energy_resolution).
    The penalty is multiplicative so J does not depend on the score's scale:
    geometry quality x readout fidelity x a fractional power discount."""
    jrows = []
    for r in rows:
        key = tuple("%g" % float(r[k]) for k in geom_keys)
        score = snr_map.get(key)
        if score is None or math.isinf(r["s_error"]):
            continue
        fidelity = max(0.0, 1.0 - r["s_error"])
        pen = (POWER_REF_MW / max(r["power_mw"], 1e-9)) ** LAMBDA_P
        j = score * fidelity * pen
        jrows.append((j, score, r))
    if not jrows:
        return ["combined: no J computable (no matching summary.json rows)"], None

    j_best, score_best, r_best = max(jrows, key=lambda t: t[0])
    geom_str = " ".join("%s=%s" % (k, fmt(float(r_best[k]))) for k in geom_keys)

    # Per-geometry J* (max over the readout grid) -> geometry-axis marginals,
    # keeping the full best row so we can record the per-geometry best readout.
    jbest_row = {}
    for j, sc, r in jrows:
        key = tuple(float(r[k]) for k in geom_keys)
        if key not in jbest_row or j > jbest_row[key][0]:
            jbest_row[key] = (j, sc, r)
    jstar = {k: v[0] for k, v in jbest_row.items()}

    # Per-geometry J table (for external optimizers / HPO drivers that need
    # J for each proposed geometry, plus the readout that achieved it).
    if results_dir:
        try:
            jpath = os.path.join(results_dir, "J_by_geom.csv")
            with open(jpath, "w") as fh:
                fh.write(",".join(geom_keys
                         + ["best_J", "best_Sa_GHz", "best_N", "score",
                            "s_error", "power_mw"]) + "\n")
            with open(jpath, "a") as fh:
                for key in sorted(jbest_row):
                    j, sc, r = jbest_row[key]
                    fh.write(",".join(
                        ["%g" % v for v in key]
                        + ["%.6g" % j, "%g" % r["sa_GHz"], "%d" % r["adc_bits"],
                           "%.6g" % sc, "%.6g" % r["s_error"],
                           "%.6g" % r["power_mw"]]) + "\n")
        except (IOError, OSError):
            pass

    lines = []
    lines.append("combined metric: J = %s*(1-s_err)*(1W/P)^%.3g"
                 % (score_name, LAMBDA_P))
    lines.append("J_best: %s | Sa=%s N=%d | J=%.4f (%s=%.4f s_err=%s "
                 "power=%s)" % (geom_str, fmt(r_best["sa_GHz"]),
                                r_best["adc_bits"], j_best, score_name,
                                score_best, fmt_pct(r_best["s_error"]),
                                fmt_w(r_best["power_mw"])))
    for ax, name in enumerate(geom_keys):
        by_val = {}
        for key, j in jstar.items():
            by_val.setdefault(key[ax], []).append(j)
        if len(by_val) < 2:
            continue
        means = {v: sum(js) / len(js) for v, js in by_val.items()}
        tag, _rng = trend_hi(means, J_TREND_THRESH)
        lines.append("J_marginal %s: %s | %s" % (
            name, " ".join("%s=%.4f" % (fmt(v), means[v])
                           for v in sorted(means)), tag))
    for col, label in (("sa_GHz", "Sa"), ("adc_bits", "N")):
        by_val = {}
        for j, _snr, r in jrows:
            by_val.setdefault(r[col], []).append(j)
        means = {v: sum(js) / len(js) for v, js in by_val.items()}
        tag, _rng = trend_hi(means, J_TREND_THRESH)
        lines.append("J_trend_vs_%s (mean J pooled): %s | %s" % (
            label, " ".join("%s=%.4f" % (fmt(v), means[v])
                            for v in sorted(means)), tag))
    lines.append("  note: J_best is THE recommended overall operating point "
                 "(geometry + readout together) -- copy it into the report")
    sa_grid = sorted(set(r["sa_GHz"] for r in rows))
    n_grid = sorted(set(r["adc_bits"] for r in rows))
    if r_best["sa_GHz"] in (sa_grid[0], sa_grid[-1]) and len(sa_grid) > 1:
        edge = "LOW" if r_best["sa_GHz"] == sa_grid[0] else "HIGH"
        lines.append("  note: J_best Sa sits at the %s grid edge (Sa=%s) -> "
                     "extend the Sa grid %s next epoch"
                     % (edge, fmt(r_best["sa_GHz"]),
                        "lower" if edge == "LOW" else "higher"))
    if r_best["adc_bits"] == n_grid[-1] and len(n_grid) > 1:
        lines.append("  note: J_best N sits at the HIGH grid edge (N=%d) -> "
                     "extend the bit grid higher next epoch"
                     % r_best["adc_bits"])
    return lines, j_best


def read_rows(csv_path):
    rows = []
    with open(csv_path) as fh:
        for r in csv.DictReader(fh):
            r["sa_GHz"] = float(r["sa_GHz"])
            r["adc_bits"] = int(r["adc_bits"])
            r["s_error"] = float(r["s_error"])
            r["power_mw"] = float(r["power_mw"])
            rows.append(r)
    return rows


def digest(rows, run_name, meta):
    sa_grid = sorted(set(r["sa_GHz"] for r in rows))
    n_grid = sorted(set(r["adc_bits"] for r in rows))
    geom_keys = sorted(k for k in rows[0] if k not in METRIC_COLS)
    geoms = sorted(set(tuple(r[k] for k in geom_keys) for r in rows))

    # Pool over geometries: per-(Sa,N) cell mean s_error and mean power.
    cells = {}
    for r in rows:
        cells.setdefault((r["sa_GHz"], r["adc_bits"]), []).append(r)
    cell_stats = {}
    for key, rs in sorted(cells.items()):
        finite = [r["s_error"] for r in rs if not math.isinf(r["s_error"])]
        mean_err = sum(finite) / len(finite) if finite else float("inf")
        mean_pw = sum(r["power_mw"] for r in rs) / len(rs)
        cell_stats[key] = (mean_err, mean_pw)

    best_cell = min(cell_stats, key=lambda k: (cell_stats[k][0], k))
    best_cell_err, best_cell_pw = cell_stats[best_cell]

    finite_rows = [r for r in rows if not math.isinf(r["s_error"])]
    if not finite_rows:
        fail("all %d scan points have non-finite s_error" % len(rows))
    best_row = min(finite_rows, key=lambda r: r["s_error"])

    compliant = {k: v for k, v in cell_stats.items()
                 if v[0] <= S_ERR_REQUIREMENT}
    op = (min(compliant, key=lambda k: (compliant[k][1], k))
          if compliant else None)

    # Geometry coupling: the per-geometry best cell.
    per_geom_best = {}
    for g in geoms:
        rs = [r for r in rows
              if tuple(r[k] for k in geom_keys) == g
              and not math.isinf(r["s_error"])]
        if rs:
            b = min(rs, key=lambda r: (r["s_error"], r["sa_GHz"], r["adc_bits"]))
            per_geom_best[g] = (b["sa_GHz"], b["adc_bits"])
    distinct = {}
    for cell in per_geom_best.values():
        distinct[cell] = distinct.get(cell, 0) + 1
    top_cells = sorted(distinct.items(), key=lambda kv: (-kv[1], kv[0]))[:2]

    # Marginal trends from the pooled cell means.
    sa_means = {}
    n_means = {}
    for (sa, nb), (err, _pw) in cell_stats.items():
        sa_means.setdefault(sa, []).append(err)
        n_means.setdefault(nb, []).append(err)
    sa_means = {k: sum(v) / len(v) for k, v in sa_means.items()}
    n_means = {k: sum(v) / len(v) for k, v in n_means.items()}
    sa_tag, _ = trend(sa_means, TREND_THRESH)
    n_tag, _ = trend(n_means, TREND_THRESH)

    lines = []
    lines.append("run: %s   channel: %s   geometries: %d   grid: Sa[%s] x N[%s]"
                 "   points: %d   units<=%s" % (
                     run_name, meta.get("channel", "?"), len(geoms),
                     ",".join(fmt(s) for s in sa_grid),
                     ",".join(str(n) for n in n_grid),
                     len(rows), meta.get("max_units", "all")))
    lines.append("global_best_cell: Sa=%s N=%d | mean_s_err=%s mean_power=%s" % (
        fmt(best_cell[0]), best_cell[1], fmt_pct(best_cell_err),
        fmt_w(best_cell_pw)))
    geom_str = " ".join("%s=%s" % (k, fmt(float(best_row[k])))
                        for k in geom_keys) or "(single geometry)"
    lines.append("best_single: %s | Sa=%s N=%d | s_err=%s power=%s" % (
        geom_str, fmt(best_row["sa_GHz"]), best_row["adc_bits"],
        fmt_pct(best_row["s_error"]), fmt_w(best_row["power_mw"])))
    lines.append("compliance: %d/%d grid cells meet s_err<=%s (mean over geometries)"
                 % (len(compliant), len(cell_stats), fmt_pct(S_ERR_REQUIREMENT)))
    if op is not None:
        lines.append("operating_point: Sa=%s N=%d | mean_s_err=%s power=%s" % (
            fmt(op[0]), op[1], fmt_pct(compliant[op][0]), fmt_w(compliant[op][1])))
        lines.append("  note: recommended readout operating point Sa=%s GHz, "
                     "N=%d bits (lowest power among cells with s_err<=2%%) -- "
                     "copy this into the report" % (fmt(op[0]), op[1]))
    else:
        lines.append("operating_point: NONE")
        lines.append("  note: no grid cell reaches s_err<=2%% -> widen the "
                     "Sa/N grid (or raise --max-units) next epoch; "
                     "digitization currently limits accuracy")
    if len(distinct) <= 1:
        lines.append("geometry_coupling: best (Sa,N) identical for all %d "
                     "geometries -> readout choice is geometry-independent"
                     % len(per_geom_best))
    else:
        lines.append("geometry_coupling: %d distinct per-geometry best cells "
                     "over %d geometries | most common: %s" % (
                         len(distinct), len(per_geom_best),
                         "; ".join("Sa=%s N=%d (%d geoms)"
                                   % (fmt(c[0]), c[1], n)
                                   for c, n in top_cells)))
    lines.append("trend_vs_Sa (mean s_err per Sa, pooled): %s | %s" % (
        " ".join("%s=%s" % (fmt(v), fmt_pct(sa_means[v]))
                 for v in sorted(sa_means)), sa_tag))
    lines.append("trend_vs_N  (mean s_err per N,  pooled): %s | %s" % (
        " ".join("%d=%s" % (v, fmt_pct(n_means[v]))
                 for v in sorted(n_means)), n_tag))

    # Deterministic recommendation notes (the agent copies these verbatim).
    if best_cell[0] == sa_grid[0] and sa_tag != "FLAT":
        lines.append("  note: best Sa sits at the LOW grid edge (Sa=%s) -> "
                     "extend the Sa grid lower next epoch" % fmt(sa_grid[0]))
    if best_cell[0] == sa_grid[-1] and sa_tag != "FLAT":
        lines.append("  note: best Sa sits at the HIGH grid edge (Sa=%s) -> "
                     "extend the Sa grid higher next epoch" % fmt(sa_grid[-1]))
    if sa_tag.startswith("PEAKED"):
        lines.append("  note: s_err is PEAKED at an interior Sa -> the grid "
                     "brackets the optimum; refine Sa spacing near the best "
                     "cell only if a finer choice is needed")
    if sa_tag == "FLAT":
        lines.append("  note: s_err FLAT vs Sa over the scanned range -> "
                     "sampling rate does not limit accuracy here; choose the "
                     "lowest Sa for power")
    if n_tag == "FLAT":
        lines.append("  note: s_err FLAT vs N over [%d,%d] bits -> ADC depth "
                     "does not limit S accuracy; choose the smallest N for "
                     "power" % (n_grid[0], n_grid[-1]))
    elif best_cell[1] == n_grid[-1]:
        lines.append("  note: best N sits at the HIGH grid edge (N=%d) -> "
                     "extend the bit grid higher next epoch" % n_grid[-1])

    return lines, len(rows), best_row["s_error"]


def main():
    ap = argparse.ArgumentParser(description="(Sa x N) digi scan + digest.")
    ap.add_argument("--rundir", required=True,
                    help="run directory, e.g. /srv/runs/<campaign>/<RUN>")
    ap.add_argument("--name", required=True, help="run name for the token")
    ap.add_argument("--sa", default="0.005,0.01,0.02,0.05,0.1",
                    help="comma list of sampling rates [GHz]")
    ap.add_argument("--bits", default="6,8,10,12",
                    help="comma list of ADC bit depths")
    ap.add_argument("--channel", default="combined",
                    choices=["combined", "cherenkov", "scintillation"])
    ap.add_argument("--max-units", type=int, default=1500,
                    help="per-geometry waveform cap for the fit (0 = no cap)")
    ap.add_argument("--max-events", type=int, default=None,
                    help="ROOT events per geometry cap (default: all)")
    ap.add_argument("--workers", type=int, default=0,
                    help="parallel fit processes (0 = min(8, cpus))")
    ap.add_argument("--seed-base", type=int, default=1234)
    args = ap.parse_args()

    rundir = args.rundir.rstrip("/")
    manifest = os.path.join(rundir, "sim_outputs", "manifest.json")
    results = os.path.join(rundir, "results")
    csv_path = os.path.join(results, "digi_scan.csv")
    meta_path = os.path.join(results, "digi_scan.json")
    marker = os.path.join(results, ".digi_scan_verified")

    if not os.path.isfile(manifest):
        fail("no manifest at %s (run not completed/verified?)" % manifest)

    sa_list = [float(x) for x in args.sa.split(",") if x.strip()]
    bits_list = [int(x) for x in args.bits.split(",") if x.strip()]
    if not sa_list or not bits_list:
        fail("empty --sa or --bits grid")

    signature = {
        "sa_GHz": sa_list, "adc_bits": bits_list, "channel": args.channel,
        "max_units": args.max_units or None, "max_events": args.max_events,
        "seed_base": args.seed_base,
    }

    cached = False
    if (os.path.isfile(marker) and os.path.isfile(csv_path)
            and os.environ.get("FORCE") != "1"):
        try:
            with open(marker) as fh:
                if json.load(fh) == signature:
                    cached = True
        except (ValueError, IOError, OSError):
            cached = False

    if not cached:
        from bilevel_opt.digi_scan import run_digi_scan
        workers = args.workers
        if workers <= 0:
            try:
                workers = min(8, len(os.sched_getaffinity(0)))
            except AttributeError:
                workers = min(8, os.cpu_count() or 4)
        try:
            run_digi_scan(
                manifest_file=manifest,
                sa_list=sa_list,
                bits_list=bits_list,
                outdir=results,
                channel=args.channel,
                max_events=args.max_events,
                max_units=args.max_units or None,
                seed_base=args.seed_base,
                n_workers=workers,
            )
        except Exception as exc:
            fail("scan error: %s" % exc)

    if not os.path.isfile(csv_path):
        fail("scan produced no %s" % csv_path)
    rows = read_rows(csv_path)
    if not rows:
        fail("digi_scan.csv is empty")
    try:
        with open(meta_path) as fh:
            meta = json.load(fh)
    except (ValueError, IOError, OSError):
        meta = dict(signature)

    lines, n_points, best_serr = digest(rows, args.name, meta)

    # Combined metric J (round 2b): joins the run's inner-loop snr_energy
    # (results/summary.json) with the readout grid. Skipped gracefully when
    # the inner stage has not run.
    geom_keys = sorted(k for k in rows[0] if k not in METRIC_COLS)
    snr_map, score_name = load_snr_map(rundir, geom_keys)
    best_j = None
    if snr_map:
        jlines, best_j = combined_digest(rows, snr_map, geom_keys, score_name,
                                         results_dir=results)
        lines.extend(jlines)

    print("DIGI_DIGEST_BEGIN")
    for ln in lines:
        print(ln)
    print("DIGI_DIGEST_END")

    if not cached:
        try:
            with open(marker, "w") as fh:
                json.dump(signature, fh)
        except (IOError, OSError):
            pass  # marker is an optimization; the token is the contract

    suffix = " (cached -- already scanned; FORCE=1 to rescan)" if cached else ""
    jpart = (" best_J=%.4f" % best_j) if best_j is not None else ""
    print("DIGI_VERIFIED run=%s points=%d best_serr=%.4f%s%s"
          % (args.name, n_points, best_serr, jpart, suffix))
    return 0


if __name__ == "__main__":
    sys.exit(main())
