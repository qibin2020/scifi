#!/usr/bin/env bash
# Run gateway in foreground (debug mode). Ctrl-C to stop.
# For normal use, START.sh (or SciF START) starts the gateway as a background instance.
set -euo pipefail

# Check required env
for v in BASEDIR APPTAINER GATEWAY_PORT; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

GATEWAY_CONFIG="$BASEDIR/Pam/gateway.model.yaml"

if [ ! -f "$GATEWAY_CONFIG" ]; then
    echo "ERROR: Config not found at $GATEWAY_CONFIG" >&2
    exit 1
fi

ENV_FLAGS=()
for _ev in LITELLM_MASTER_KEY ANTHROPIC_API_KEY BEDROCK_API_KEY; do
    if [ -n "${!_ev:-}" ]; then
        ENV_FLAGS+=(--env "$_ev=${!_ev}")
    fi
done

echo "Starting gateway in foreground on port $GATEWAY_PORT (Ctrl-C to stop)..."
$APPTAINER run \
        "${ENV_FLAGS[@]}" \
        --bind "$GATEWAY_CONFIG":/app/config.yaml \
        --bind "$TMPDIR":/tmp:rw \
        --writable-tmpfs \
        --cleanenv \
        --contain \
        --pwd /app \
      "$BASEDIR/Pam/gateway.sif" \
      --config /app/config.yaml --port "$GATEWAY_PORT"

