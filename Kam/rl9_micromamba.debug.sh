#!/usr/bin/env bash
set -euo pipefail

# Check required env (source ENV.sh before running)
for v in APPTAINER SIF; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

$APPTAINER exec \
        --bind "$PWD":/srv:rw \
        --bind "$TMPDIR":/tmp:rw \
        --writable-tmpfs \
        --cleanenv \
        --contain \
        --pwd /srv \
      "$SIF" \
      bash -c '
eval "$(/usr/local/bin/micromamba shell hook -s bash)"
exec bash
'
