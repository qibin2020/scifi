#!/usr/bin/env bash
set -euo pipefail

# Check required env (source ENV.sh before running)
for v in BASEDIR APPTAINER SIF OVERLAY; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

$APPTAINER exec \
        --overlay "$OVERLAY":ro \
        --bind "$PWD":/srv:rw \
        --bind "$TMPDIR":/tmp:rw \
        --cleanenv \
        --contain \
        --no-home \
        --pwd /srv \
      "$SIF" \
      bash -c '
export HOME=/srv
export MAMBA_ROOT_PREFIX=/F/mamba
eval "$(/usr/local/bin/micromamba shell hook -s bash)"
micromamba activate driver
exec bash
'
