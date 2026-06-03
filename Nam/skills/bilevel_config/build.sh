#!/bin/bash
# bilevel_config skill — one-shot builder.
# Absorbs the boilerplate so a task md only needs the scan flags:
#   sources key4hep (PyYAML python), runs make_config.py with the given flags,
#   then validates the config by generating the manifest. Prints ONE token:
#     CONFIG_VALIDATED geometries=<N> out=<path>   on success
#     CONFIG_FAIL <reason>                          on failure
#
# CAMPAIGN AREA. When --out / --runs-dir are NOT given, they default into the
# campaign area /srv/runs/<CAMPAIGN>/ where CAMPAIGN = $SCIF_CAMPAIGN (the
# task's `Campaign:` key, shared by chained tasks) or else $SCIF_SESSION
# (this invocation's unique id). Explicit flags always win (legacy tasks
# unaffected).
#
# Usage (same flags as make_config.py; --name and the scan flags required):
#   bash /srv/skills/bilevel_config/build.sh --name myscan \
#        --scheme srv --geom width:5,6,7,8:cm ... --opt R_cluster_mm:10:150:15 ...
set -o pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# key4hep python (PyYAML + bilevel_opt) — env.sh lives at the project root /srv/bilevel.
if [ -f /srv/bilevel/env.sh ]; then
    cd /srv/bilevel && source ./env.sh >/dev/null 2>&1
elif [ -f /srv/env.sh ]; then
    cd /srv && source ./env.sh >/dev/null 2>&1
fi

# Campaign area resolution (kept in sync with bilevel_run/run_full.py).
CAMPAIGN="${SCIF_CAMPAIGN:-${SCIF_SESSION:-}}"
if [ -n "$CAMPAIGN" ]; then BASE="/srv/runs/$CAMPAIGN"; else BASE="/srv/runs"; fi

# Parse the flags we need; note which were given explicitly.
out=""; name=""; runs=""; args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
    case "${args[$i]}" in
        --out)      out="${args[$((i+1))]}";;
        --name)     name="${args[$((i+1))]}";;
        --runs-dir) runs="${args[$((i+1))]}";;
    esac
done
[ -n "$name" ] || { echo "CONFIG_FAIL missing --name"; exit 1; }

# Default --out / --runs-dir into the campaign area when absent.
extra=()
if [ -z "$runs" ]; then runs="$BASE"; extra+=(--runs-dir "$runs"); fi
if [ -z "$out" ];  then out="$BASE/$name.yaml"; extra+=(--out "$out"); fi
mkdir -p "$(dirname "$out")" "$runs" 2>/dev/null

# 1. generate the YAML
if ! python3 "$HERE/make_config.py" "$@" "${extra[@]}" >/tmp/mkc.log 2>&1; then
    echo "CONFIG_FAIL make_config: $(tail -1 /tmp/mkc.log)"; exit 1
fi

# 2. validate: the config must actually parse + generate the geometry manifest
if ! bilevel_opt --config "$out" --stage outer --run-mode generate --run "$name" >/tmp/gen.log 2>&1; then
    echo "CONFIG_FAIL generate: $(tail -1 /tmp/gen.log)"; exit 1
fi
mf="$runs/$name/sim_outputs/manifest.json"
n=$(python3 -c "import json,sys; print(len(json.load(open('$mf'))))" 2>/dev/null) || {
    echo "CONFIG_FAIL no manifest at $mf"; exit 1; }

echo "CONFIG_VALIDATED geometries=$n out=$out"
