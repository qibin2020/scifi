#!/bin/bash
# bilevel_run skill — ONE-command FULL runner (entry point).
# Stages the config, sizes and submits the SLURM job, waits for it, verifies
# the outputs. The agent runs THIS with a long bash timeout and reads ONE token.
#
# Usage:
#   bash /srv/skills/bilevel_run/run_full.sh <CFG> <RUN_NAME> <G> [TIME_MINUTES]
#
# Prints `SUBMITTED job=<id>` then ONE final line:
#   RUN_VERIFIED run=<NAME> roots=<N> job=<id>    on success
#   RUN_FAIL <reason>                              on failure
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/run_full.py" "$@"
