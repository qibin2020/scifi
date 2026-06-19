#!/bin/bash
# bilevel_digi skill — ONE-command (Sa x N) readout scan + digest.
# Replays the cached ROOT outputs of a COMPLETED run through the waveform
# digitizer + template fit for every (sampling rate, ADC bits) grid point.
# No new simulation. Deterministic and idempotent (FORCE=1 to rescan).
#
# Prints the DIGI_DIGEST block and ONE final token:
#     DIGI_VERIFIED run=<RUN> points=<P> best_serr=<x>     on success
#     DIGI_FAIL <reason>                                    on failure
#
# Usage:
#   bash /srv/skills/bilevel_digi/digi_scan.sh --run <RUN_NAME> \
#        [--sa 0.005,0.01,0.02,0.05,0.1] [--bits 6,8,10,12] \
#        [--max-units 1500] [--max-events N] [--channel combined] [--workers N]
# The --run form resolves inside the campaign area /srv/runs/<CAMPAIGN>/
# (CAMPAIGN = $SCIF_CAMPAIGN or $SCIF_SESSION). Use --rundir <DIR> only for
# an explicit foreign run directory (e.g. found via /srv/runs/LEDGER.csv).
set -o pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Campaign area resolution (kept in sync with bilevel_run/run_full.py).
CAMPAIGN="${SCIF_CAMPAIGN:-${SCIF_SESSION:-}}"
if [ -n "$CAMPAIGN" ]; then BASE="/srv/runs/$CAMPAIGN"; else BASE="/srv/runs"; fi

ARGS=()
NAME=""
while [ $# -gt 0 ]; do
    case "$1" in
        --run)    NAME="$2"; shift 2 ;;
        --rundir) ARGS+=(--rundir "$2"); NAME="${NAME:-$(basename "$2")}"; shift 2 ;;
        *)        ARGS+=("$1"); shift ;;
    esac
done
[ -n "$NAME" ] || { echo "DIGI_FAIL need --run <RUN_NAME> (or --rundir <DIR>)"; exit 1; }
# --run resolves to the campaign area unless an explicit --rundir was given.
case " ${ARGS[*]} " in
    *" --rundir "*) : ;;
    *) ARGS+=(--rundir "$BASE/$NAME") ;;
esac

# key4hep python (numpy/scipy/PyROOT + bilevel_opt on PYTHONPATH) — env.sh at
# /srv/bilevel (agent containers) or /srv (SLURM job containers).
if [ -f /srv/bilevel/env.sh ]; then
    cd /srv/bilevel && source ./env.sh >/dev/null 2>&1
elif [ -f /srv/env.sh ]; then
    cd /srv && source ./env.sh >/dev/null 2>&1
fi

python3 "$HERE/scan.py" --name "$NAME" "${ARGS[@]}"
