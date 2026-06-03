#!/bin/bash
# bilevel_run skill — one-shot output verifier for a finished FULL run.
# Absorbs the post-run check so a task md never spells it out: it counts the
# ROOT files under <run>/sim_outputs/ and checks results/summary.csv exists and
# is non-empty. Prints exactly ONE line:
#     RUN_VERIFIED run=<NAME> roots=<N>        on success
#     RUN_FAIL <reason>                        on failure (e.g. roots=4/6,
#                                              or "summary.csv missing")
#
# Usage:
#   bash /srv/skills/bilevel_run/verify.sh <RUN_NAME> <EXPECTED_GEOMETRIES> [RUNS_DIR]
# RUNS_DIR defaults to /srv/runs (override only for host-side testing).
set -o pipefail

# Tolerate a stray leading config-path arg (a common agent slip:
# `verify.sh /srv/runs/<name>.yaml <name> <G>`) — verification only needs the
# run name and the expected count, so skip any *.yaml/*.yml argument.
case "$1" in *.yaml|*.yml) shift;; esac

name="$1"
expected="$2"
runs="${3:-/srv/runs}"

if [ -z "$name" ] || [ -z "$expected" ]; then
    echo "RUN_FAIL usage: verify.sh <RUN_NAME> <EXPECTED_GEOMETRIES> [RUNS_DIR]"
    exit 1
fi

D="$runs/$name"
if [ ! -d "$D" ]; then
    echo "RUN_FAIL run dir $D missing"
    exit 1
fi

roots=$(ls "$D"/sim_outputs/*.root 2>/dev/null | wc -l | tr -d ' ')

if [ "$roots" != "$expected" ]; then
    echo "RUN_FAIL roots=$roots/$expected"
    exit 1
fi

csv="$D/results/summary.csv"
if [ ! -s "$csv" ]; then
    echo "RUN_FAIL summary.csv missing"
    exit 1
fi

echo "RUN_VERIFIED run=$name roots=$roots"
