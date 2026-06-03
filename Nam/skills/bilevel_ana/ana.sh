#!/bin/bash
# bilevel_ana skill — one-shot digest runner.
# Sources the key4hep env (numpy-capable python), then runs extract.py with the
# given flags. Prints the ANA_DIGEST block and ONE final token:
#     ANA_OK geometries=<N> best_score=<S>    on success
#     ANA_FAIL <reason>                        on failure
#
# Usage:
#   bash /srv/skills/bilevel_ana/ana.sh --run <RUN_NAME>
#   bash /srv/skills/bilevel_ana/ana.sh --results <DIR>
# The --run form resolves inside the campaign area /srv/runs/<CAMPAIGN>/
# (CAMPAIGN = $SCIF_CAMPAIGN or $SCIF_SESSION) — the normal case for runs
# made in this same task. Use --results only for an explicit foreign path.
set -o pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Campaign area resolution (kept in sync with bilevel_run/run_full.py).
CAMPAIGN="${SCIF_CAMPAIGN:-${SCIF_SESSION:-}}"
if [ -n "$CAMPAIGN" ]; then BASE="/srv/runs/$CAMPAIGN"; else BASE="/srv/runs"; fi

if [ "$1" = "--run" ]; then
    NAME="$2"; shift 2
    [ -n "$NAME" ] || { echo "ANA_FAIL --run needs a run name"; exit 1; }
    set -- --results "$BASE/$NAME/results" "$@"
fi

# key4hep python (numpy) — env.sh at /srv/bilevel (agent containers) or /srv
# (SLURM job containers). Fall back to bare python3.
if [ -f /srv/bilevel/env.sh ]; then
    cd /srv/bilevel && source ./env.sh >/dev/null 2>&1
elif [ -f /srv/env.sh ]; then
    cd /srv && source ./env.sh >/dev/null 2>&1
fi

python3 "$HERE/extract.py" "$@"
