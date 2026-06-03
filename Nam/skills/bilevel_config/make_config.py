#!/usr/bin/env python3
"""
make_config.py — emit a VALID bilevel-optimization YAML config from a handful of
high-level CLI flags. Designed so a weak agent never hand-writes YAML: it just
maps a natural-language scan into one short invocation of this script.

The emitted config matches the schema parsed by bilevel_opt
(pipeline.py / outerloop.py / innerloop.py). It is validated by running
`bilevel_opt --stage outer --run-mode generate` on the output.

Example
-------
    python make_config.py \
        --out /srv/runs/cfg/scan.yaml \
        --name myscan --runs-dir /srv/runs --scheme srv \
        --geom scepcal_xtal_theta_width:5,6,7,8:cm \
        --geom scepcal_xtal_length_f:6,8,10:cm \
        --geom scepcal_projective_offset_r:10:cm \
        --geom scepcal_xtal_length_r:15:cm \
        --events 5 --particle e- --momentum 1 \
        --optimize-method brute \
        --opt R_cluster_mm:5:200:15 \
        --opt E_threshold_GeV:0:0.5:5 \
        --score snr_energy

Each --geom is  PARAM:VALUESPEC[:UNIT]  where VALUESPEC is either
  - a comma list of values:  5,6,7,8
  - a range start..stop..step: 5..10..1   (inclusive)
Each --opt is   NAME:LO:HI:GRID   (bounds [LO,HI], plot_grid_points GRID).
"""

from __future__ import annotations

import argparse
import sys

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    sys.exit(f"PyYAML is required ({exc})")


# ---------------------------------------------------------------------------
# Known-good vocabulary (kept in sync with the detector XML + registries).
# ---------------------------------------------------------------------------
# Scannable SCEPCal geometry constants (names must exist in
# DectDimensions_IDEA_o2_v01.xml). These four are the commonly-swept ones.
KNOWN_GEOM_PARAMS = {
    "scepcal_xtal_theta_width",     # crystal angular/transverse width
    "scepcal_projective_offset_r",  # projective offset (radial)
    "scepcal_projective_offset_x",
    "scepcal_xtal_length_f",        # front crystal length
    "scepcal_xtal_length_r",        # rear crystal length
    "scepcal_mainlayer_reargap",
    "scepcal_timinglayer_gap",
    "scepcal_timing_xtal_depth",
    "scepcal_timing_xtal_length",
}

# Friendly aliases the agent might pass from natural language.
GEOM_ALIASES = {
    "crystal_width": "scepcal_xtal_theta_width",
    "xtal_width": "scepcal_xtal_theta_width",
    "width": "scepcal_xtal_theta_width",
    "front_length": "scepcal_xtal_length_f",
    "front": "scepcal_xtal_length_f",
    "rear_length": "scepcal_xtal_length_r",
    "rear": "scepcal_xtal_length_r",
    "offset": "scepcal_projective_offset_r",
    "projective_offset": "scepcal_projective_offset_r",
}

OPTIMIZE_METHODS = {
    "bounded", "L-BFGS-B",
    "differential_evolution", "dual_annealing", "shgo", "brute",
}

SCORES = {"snr_energy"}
ALGORITHMS = {"seeded_radius_cog"}

# Nice axis labels for known params (for plots / geometry_labels).
GEOM_LABELS = {
    "scepcal_xtal_theta_width": "Crystal width [cm]",
    "scepcal_projective_offset_r": "Projective offset [cm]",
    "scepcal_projective_offset_x": "Projective offset x [cm]",
    "scepcal_xtal_length_f": "Front length [cm]",
    "scepcal_xtal_length_r": "Rear length [cm]",
    "scepcal_mainlayer_reargap": "Mainlayer rear gap [cm]",
    "scepcal_timinglayer_gap": "Timing layer gap [cm]",
    "scepcal_timing_xtal_depth": "Timing xtal depth",
    "scepcal_timing_xtal_length": "Timing xtal length",
}

OPT_LABELS = {
    "R_cluster_mm": "Cluster radius R [mm]",
    "E_threshold_GeV": "Energy threshold [GeV]",
}


# ---------------------------------------------------------------------------
# Path schemes
# ---------------------------------------------------------------------------
def detector_block(scheme: str, base: str | None) -> dict:
    """Return the detectors.scepcal block for the chosen container path scheme.

    scheme=srv      -> project mounted at /srv      (SLURM / wrapper runs).
    scheme=bilevel  -> project mounted at /srv/bilevel (local agent-mount runs).
    --base overrides the detector-config prefix entirely.
    """
    if base is not None:
        prefix = base.rstrip("/")
    elif scheme == "bilevel":
        prefix = "/srv/bilevel"
    else:  # srv (default)
        prefix = "/srv"
    dc = f"{prefix}/detector_config/IDEA_o2_v01"
    return {
        "repo_root": "/srv/k4geo",
        "source_script": "/srv/k4geo/install/bin/thisk4geo.sh",
        "steering_file": f"{dc}/SteeringFile_IDEA_o2_v01.py",
        "compact_xml": f"{dc}/IDEA_o2_v01.xml",
        "dimensions_xml": f"{dc}/DectDimensions_IDEA_o2_v01.xml",
    }


# ---------------------------------------------------------------------------
# Parsers for the compact CLI mini-languages
# ---------------------------------------------------------------------------
def _num(s: str) -> float:
    return float(s)


def parse_geom(spec: str) -> dict:
    """PARAM:VALUESPEC[:UNIT] -> a geometry sweep dict (values: or start/stop/step)."""
    parts = spec.split(":")
    if len(parts) < 2:
        sys.exit(f"--geom needs PARAM:VALUESPEC[:UNIT], got '{spec}'")
    param_raw, valuespec = parts[0], parts[1]
    unit = parts[2] if len(parts) >= 3 and parts[2] != "" else "cm"

    param = GEOM_ALIASES.get(param_raw, param_raw)
    if param not in KNOWN_GEOM_PARAMS:
        sys.exit(
            f"Unknown geometry parameter '{param_raw}' (-> '{param}').\n"
            f"Valid: {sorted(KNOWN_GEOM_PARAMS)}\n"
            f"Aliases: {sorted(GEOM_ALIASES)}"
        )

    out: dict = {"parameter": param}
    if ".." in valuespec:
        try:
            start, stop, step = (_num(x) for x in valuespec.split(".."))
        except ValueError:
            sys.exit(f"--geom range must be start..stop..step, got '{valuespec}'")
        out.update({"start": start, "stop": stop, "step": step})
    else:
        vals = [_num(x) for x in valuespec.split(",") if x != ""]
        if not vals:
            sys.exit(f"--geom value list is empty in '{spec}'")
        out["values"] = vals
    out["unit"] = unit
    return out


def parse_opt(spec: str) -> dict:
    """NAME:LO:HI:GRID -> an optimize_params entry."""
    parts = spec.split(":")
    if len(parts) != 4:
        sys.exit(f"--opt needs NAME:LO:HI:GRID, got '{spec}'")
    name, lo, hi, grid = parts
    return {
        "name": name,
        "label": OPT_LABELS.get(name, name),
        "bounds": [_num(lo), _num(hi)],
        "plot_grid_points": int(grid),
    }


def geom_npoints(g: dict) -> int:
    if "values" in g:
        return len(g["values"])
    start, stop, step = g["start"], g["stop"], g["step"]
    n = 0
    cur = start
    while cur <= stop + 1e-9:
        n += 1
        cur += step
    return n


# ---------------------------------------------------------------------------
# Build the config dict
# ---------------------------------------------------------------------------
def build_config(args: argparse.Namespace) -> dict:
    if args.optimize_method not in OPTIMIZE_METHODS:
        sys.exit(f"Unknown --optimize-method '{args.optimize_method}'. "
                 f"Valid: {sorted(OPTIMIZE_METHODS)}")
    if args.score not in SCORES:
        sys.exit(f"Unknown --score '{args.score}'. Valid: {sorted(SCORES)}")
    if args.algorithm not in ALGORITHMS:
        sys.exit(f"Unknown --algorithm '{args.algorithm}'. Valid: {sorted(ALGORITHMS)}")

    geoms = [parse_geom(s) for s in args.geom]
    if not geoms:
        sys.exit("At least one --geom is required.")
    opts = [parse_opt(s) for s in args.opt]
    if not opts:
        sys.exit("At least one --opt is required.")

    # brute needs one grid size per optimized parameter.
    algo_block: dict = {
        "name": args.algorithm,
        "params": {"branch": args.branch},
        "optimize_method": args.optimize_method,
        "optimize_params": opts,
    }
    if args.optimize_method == "brute":
        algo_block["brute_grid_sizes"] = [o["plot_grid_points"] for o in opts]

    # geometry_labels for every swept param.
    geom_labels = {g["parameter"]: GEOM_LABELS.get(g["parameter"], g["parameter"])
                   for g in geoms}

    inner: dict = {
        "tree_name": "events",
        "branches": [{"name": args.branch, "hit_type": args.hit_type}],
        "geometry_labels": geom_labels,
        "algorithm": algo_block,
        "score": {"name": args.score, "params": {"sigma0": args.sigma0}},
        "max_events": None,
    }

    # heatmap: pick the multi-valued geom params as axes (up to 2); fix the
    # single-valued ones at their value. Mirrors opt_iterA.yaml.
    multi = [g for g in geoms if geom_npoints(g) > 1]
    single = [g for g in geoms if geom_npoints(g) == 1]
    axes = [g["parameter"] for g in multi[:2]]
    if not axes:
        axes = [geoms[0]["parameter"]]
    fixed = {}
    for g in single:
        fixed[g["parameter"]] = (g["values"][0] if "values" in g else g["start"])
    heatmap = {"axes": axes}
    if fixed:
        heatmap["fixed"] = fixed
    inner["heatmap"] = heatmap

    run_setup = (args.run_mode != "generate")
    config = {
        "run_mode": args.run_mode,
        "key4hep": {
            "run_setup": run_setup,
            "setup_script": ("export detector_db=/srv/detector_config"
                             if run_setup else "true"),
        },
        "detectors": {"scepcal": detector_block(args.scheme, args.base)},
        "runtime": {
            "runs_dir": args.runs_dir,
            "ddsim_executable": "ddsim",
            "scheduler": {"slurm": {
                "cpus_per_task": args.cpus,
                "mem": args.mem,
                "time": args.time,
            }},
        },
        "runs": [{
            "name": args.name,
            "outer_loop": {
                "detector_label": "scepcal",
                "seeds": {"start": args.seed_start, "end": args.seed_end},
                "geometry": geoms,
                "sim": {
                    "particles": [args.particle],
                    "events": args.events,
                    "momentum_GeV": args.momentum,
                    "plusminus_percent": args.plusminus_percent,
                    "theta_min": args.theta_min,
                    "theta_max": args.theta_max,
                },
            },
            "inner_loop": inner,
        }],
    }
    return config


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, help="Path to write the YAML config.")
    p.add_argument("--name", required=True, help="Run name (runs/<name>/...).")
    p.add_argument("--runs-dir", default="/srv/runs", help="runtime.runs_dir.")
    p.add_argument("--scheme", choices=["srv", "bilevel"], default="srv",
                   help="Container path scheme: srv (SLURM, default) or bilevel "
                        "(local agent-mount, project at /srv/bilevel).")
    p.add_argument("--base", default=None,
                   help="Override detector-config prefix (else derived from --scheme).")

    p.add_argument("--geom", action="append", default=[], metavar="PARAM:VALS[:UNIT]",
                   help="Geometry sweep. Repeatable. VALS = comma list or start..stop..step.")
    p.add_argument("--opt", action="append", default=[], metavar="NAME:LO:HI:GRID",
                   help="Optimized inner param with bounds [LO,HI] and grid GRID. Repeatable.")

    p.add_argument("--events", type=int, default=100)
    p.add_argument("--particle", default="e-")
    p.add_argument("--momentum", type=float, default=1.0, help="momentum in GeV.")
    p.add_argument("--plusminus-percent", type=float, default=0.0)
    p.add_argument("--theta-min", type=float, default=60.0)
    p.add_argument("--theta-max", type=float, default=120.0)
    p.add_argument("--seed-start", type=int, default=0)
    p.add_argument("--seed-end", type=int, default=0)

    p.add_argument("--algorithm", default="seeded_radius_cog")
    p.add_argument("--branch", default="SCEPCal_MainEdep")
    p.add_argument("--hit-type", default="SimCalorimeterHit")
    p.add_argument("--optimize-method", default="brute",
                   help="brute | differential_evolution | dual_annealing | shgo | "
                        "L-BFGS-B | bounded.")
    p.add_argument("--score", default="snr_energy")
    p.add_argument("--sigma0", type=float, default=1.0)

    p.add_argument("--run-mode", choices=["generate", "local", "slurm"],
                   default="generate")
    p.add_argument("--cpus", type=int, default=1, help="slurm cpus_per_task.")
    p.add_argument("--mem", default="12G")
    p.add_argument("--time", default="1:00:00")
    return p


def main() -> None:
    args = make_parser().parse_args()
    config = build_config(args)

    from pathlib import Path
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        yaml.safe_dump(config, f, sort_keys=False, default_flow_style=False)

    # Tiny machine-readable summary line for the agent.
    ngeo = 1
    for g in config["runs"][0]["outer_loop"]["geometry"]:
        ngeo *= geom_npoints(g)
    nseed = args.seed_end - args.seed_start + 1
    nparticle = 1
    total = ngeo * nseed * nparticle
    print(f"CONFIG_OK geometries={ngeo} total_runs={total} out={out}")


if __name__ == "__main__":
    main()
