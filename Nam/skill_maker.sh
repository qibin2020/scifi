#!/usr/bin/env bash
set -euo pipefail

# Check required env (source ENV.sh before running)
for v in APPTAINER SIF OVERLAY FDIR GATEWAY_PORT SKILLS_SRC RANK_SRC FALLBACK_HIGHEST FALLBACK_WORKING; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

# Support: skill_maker.sh <file.md> [skill_name]
#      or: skill_maker.sh --desc "plain text description" [skill_name]
EXTRA_BIND=""
if [ "${1:-}" = "--desc" ]; then
    shift
    TEXT="$1"; shift
    DESC_FILE="$(mktemp "$TMPDIR/scifi_desc.XXXXXX.md")"
    echo "$TEXT" > "$DESC_FILE"
    EXTRA_BIND="--bind $DESC_FILE:/tmp/_desc.md:ro"
    ARGS="/tmp/_desc.md"
    # Remaining args (skill_name etc)
    for arg in "$@"; do
        ARGS="$ARGS $arg"
    done
else
    ARGS=""
    for arg in "$@"; do
        if [ -f "$arg" ]; then
            EXTRA_BIND="$EXTRA_BIND --bind $(realpath "$arg"):/srv/input.md:ro"
            ARGS="$ARGS /srv/input.md"
        else
            ARGS="$ARGS $arg"
        fi
    done
fi

$APPTAINER exec \
        --overlay "$OVERLAY":ro \
        --env "GATEWAY_URL=http://localhost:${GATEWAY_PORT}" \
        --env "FALLBACK_HIGHEST=${FALLBACK_HIGHEST}" \
        --env "FALLBACK_WORKING=${FALLBACK_WORKING}" \
        --env "SKILLS_DIR=/srv/skills" \
        --env "CAM_DIR=${CAM_DIR:+/cam}" \
        --bind "$BASEDIR/Nam":/srv/Nam \
        --bind "$FDIR/driver.py":/srv/lib/driver.py:ro \
        --bind "$BASEDIR/Pam/pam.py":/srv/lib/pam.py:ro \
        --bind "$RANK_SRC":/srv/lib/gateway.rank.yaml:ro \
        --bind "$SKILLS_SRC":/srv/skills \
        ${CAM_DIR:+--bind "$CAM_DIR":/cam:rw} \
        --bind "$TMPDIR":/tmp:rw \
        $EXTRA_BIND \
        --cleanenv \
        --contain \
        --pwd /srv/Nam \
      "$SIF" \
      bash -c '
export MAMBA_ROOT_PREFIX=/F/mamba
eval "$(/usr/local/bin/micromamba shell hook -s bash)"
micromamba activate driver
python /srv/Nam/skill_maker.py '"$ARGS"'
'
