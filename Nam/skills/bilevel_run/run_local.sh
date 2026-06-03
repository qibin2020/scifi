#!/bin/bash
# bilevel_run skill — one-shot LOCAL stage runner (generate | inner | evaluate).
# Absorbs all boilerplate for the fast, non-SLURM stages: it sources the
# key4hep env, asks run_cmd.py for the right command, runs it with the chatty
# bilevel logging sent to a log file, then verifies the stage's output.
# Prints exactly ONE line:
#     LOCAL_VERIFIED mode=<MODE> run=<NAME> [geometries=<N>]   on success
#     LOCAL_FAIL <reason>                                       on failure
#
# Usage:
#   bash /srv/skills/bilevel_run/run_local.sh <CFG> <RUN_NAME> <MODE>
# <CFG> may be a task-shipped config (e.g. ./run_local.yaml) — it is resolved
# to an absolute path before the env switches directories.
# <MODE> is generate | inner | evaluate. Full mode must go through slurm_submit.
set -o pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CFG="$1"; NAME="$2"; MODE="${3:-generate}"
[ -n "$CFG" ] && [ -n "$NAME" ] || {
    echo "LOCAL_FAIL usage: run_local.sh <CFG> <RUN_NAME> <generate|inner|evaluate>"; exit 1; }
# Campaign area resolution (kept in sync with run_full.py): a missing CFG path
# is looked up under /srv/runs/<CAMPAIGN>/ (SCIF_CAMPAIGN, else SCIF_SESSION).
CAMPAIGN="${SCIF_CAMPAIGN:-${SCIF_SESSION:-}}"
if [ -n "$CAMPAIGN" ]; then BASE="/srv/runs/$CAMPAIGN"; else BASE="/srv/runs"; fi
if [ ! -f "$CFG" ] && [ -f "$BASE/$(basename "$CFG")" ]; then CFG="$BASE/$(basename "$CFG")"; fi
[ -f "$CFG" ] || { echo "LOCAL_FAIL config $CFG not found"; exit 1; }
CFG="$(readlink -f "$CFG")"
case "$MODE" in
    generate|outer|inner|evaluate) ;;
    full) echo "LOCAL_FAIL full mode is SLURM-only — use run_cmd.py + slurm_submit"; exit 1;;
    *)    echo "LOCAL_FAIL unknown mode $MODE"; exit 1;;
esac

# key4hep python (PyYAML + bilevel_opt) — env.sh at /srv/bilevel (agent
# containers) or /srv (SLURM job containers).
if [ -f /srv/bilevel/env.sh ]; then
    cd /srv/bilevel && source ./env.sh >/dev/null 2>&1
elif [ -f /srv/env.sh ]; then
    cd /srv && source ./env.sh >/dev/null 2>&1
else
    echo "LOCAL_FAIL no env.sh found (bilevel project not mounted at /srv/bilevel or /srv)"; exit 1
fi

CMD=$(python3 "$HERE/run_cmd.py" --config "$CFG" --run "$NAME" --mode "$MODE") || {
    echo "LOCAL_FAIL run_cmd.py rejected the request"; exit 1; }

if ! eval "$CMD" >/tmp/bilevel_local.log 2>&1; then
    echo "LOCAL_FAIL $MODE: $(tail -1 /tmp/bilevel_local.log)"; exit 1
fi

RUNS=$(python3 -c "import yaml;print(yaml.safe_load(open('$CFG'))['runtime']['runs_dir'])" 2>/dev/null)
[ -n "$RUNS" ] || { echo "LOCAL_FAIL cannot read runtime.runs_dir from $CFG"; exit 1; }
D="$RUNS/$NAME"

ledger() {  # append one discovery line (advisory; never fail over it)
    L="/srv/runs/LEDGER.csv"
    [ -f "$L" ] || echo "date,campaign,session,run,geometries,job,status,path" >> "$L" 2>/dev/null
    echo "$(date +%Y-%m-%dT%H:%M:%S),${CAMPAIGN:--},${SCIF_SESSION:-adhoc},$NAME,${1:--},-,LOCAL_VERIFIED,$D" >> "$L" 2>/dev/null
}

case "$MODE" in
    generate|outer)
        MF="$D/sim_outputs/manifest.json"
        N=$(python3 -c "import json;print(len(json.load(open('$MF'))))" 2>/dev/null) || {
            echo "LOCAL_FAIL no manifest at $MF"; exit 1; }
        ledger "$N"
        echo "LOCAL_VERIFIED mode=generate run=$NAME geometries=$N";;
    inner)
        [ -s "$D/results/summary.csv" ] || { echo "LOCAL_FAIL no results/summary.csv in $D"; exit 1; }
        ledger
        echo "LOCAL_VERIFIED mode=inner run=$NAME";;
    evaluate)
        [ -d "$D/results" ] && [ -n "$(ls -A "$D/results" 2>/dev/null)" ] || {
            echo "LOCAL_FAIL results dir empty in $D"; exit 1; }
        ledger
        echo "LOCAL_VERIFIED mode=evaluate run=$NAME";;
esac
