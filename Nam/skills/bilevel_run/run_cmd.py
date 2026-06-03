#!/usr/bin/env python3
"""bilevel_run helper: print the exact command string for a bilevel run.

Given high-level inputs (config path, run name, mode, parallelism) this prints
ONE clean line: the command to hand to `slurm_submit` (full mode) or to run in
bash (generate/inner/evaluate). The agent must NOT assemble the long && chain by
hand -- it runs this script, copies the single printed line, and submits it.

All paths use the in-container /srv scheme, because slurm_submit commands run
inside the SciFi container (project -> /srv). Generate/inner/evaluate local
modes also assume /srv when run via the container wrapper.

Modes:
  full      generate -> parallel ddsim (bash payload) -> inner.  SLURM only.
  generate  write geometry XMLs + ddsim manifest. Fast, local-ok.
  outer     alias of the generate stage (--stage outer --run-mode generate).
  inner     inner-loop optimization on existing ROOTs. Fast, local-ok.
  evaluate  multi-score evaluation on existing ROOTs. Fast, local-ok.

Usage:
  python3 run_cmd.py --config /srv/scif_configs/opt_test.yaml \
      --run run_skilltest --mode full --parallel 4
"""
from __future__ import print_function

import argparse
import sys

BILEVEL = "bilevel_opt"
PAYLOAD = "/srv/driver/slurm_outer_payload.sh"


def build(config, run, mode, parallel):
    """Return (command_string, is_slurm)."""
    base = "%s --config %s" % (BILEVEL, config)

    if mode in ("generate", "outer"):
        # Fast: only writes run scripts + manifest. Local-ok.
        cmd = "%s --stage outer --run-mode generate --run %s" % (base, run)
        return cmd, False

    if mode == "inner":
        cmd = "%s --stage inner --run %s" % (base, run)
        return cmd, False

    if mode == "evaluate":
        cmd = "%s --stage evaluate --run %s" % (base, run)
        return cmd, False

    if mode == "full":
        # generate -> parallel ddsim -> inner, as ONE chain.
        # NOTE: the payload is invoked with `bash` (subprocess), NOT `source`:
        # its `set -e` / `exit 0` would otherwise kill the chain and skip inner.
        #
        # Parallelism is NOT baked into the command: the payload self-sizes to
        # its allocation at runtime (clamps to nproc/2, the memory-safe ddsim
        # count). This removes the cpus-vs-MAX_PARALLEL consistency burden from
        # the agent — it chooses ONE number (slurm_submit cpus) and the job
        # adapts. An explicit --parallel still overrides (clamped by the
        # payload), for manual/bench use.
        gen = "%s --stage outer --run-mode generate --run %s" % (base, run)
        if parallel is not None:
            ddsim = "RUN_NAME=%s MAX_PARALLEL=%d bash %s" % (run, parallel, PAYLOAD)
        else:
            ddsim = "RUN_NAME=%s bash %s" % (run, PAYLOAD)
        inner = "%s --stage inner --run %s" % (base, run)
        cmd = "%s && %s && %s" % (gen, ddsim, inner)
        return cmd, True

    raise ValueError("unknown mode: %s" % mode)


def main():
    p = argparse.ArgumentParser(description="Print the bilevel run command line.")
    p.add_argument("--config", required=True,
                   help="Config path in /srv scheme, e.g. /srv/scif_configs/opt_test.yaml")
    p.add_argument("--run", required=True, help="Run name, e.g. run_skilltest")
    p.add_argument("--mode", required=True,
                   choices=["full", "generate", "outer", "inner", "evaluate"])
    p.add_argument("--parallel", type=int, default=None,
                   help="Explicit MAX_PARALLEL override for ddsim in full mode. "
                        "Default: omit — the job self-sizes to its allocation "
                        "(payload clamps to nproc/2).")
    args = p.parse_args()

    try:
        cmd, is_slurm = build(args.config, args.run, args.mode, args.parallel)
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    # Single clean line: exactly what to pass to slurm_submit (full) or bash.
    print(cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
