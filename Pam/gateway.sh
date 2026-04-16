#!/usr/bin/env bash
# Gateway start/stop/status via apptainer instance.
# Usage: bash gateway.sh [start|stop|status]
set -euo pipefail

# Check required env
for v in BASEDIR APPTAINER GATEWAY_PORT; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

INSTANCE_NAME="pam_gateway"
GATEWAY_CONFIG="$BASEDIR/Pam/gateway.model.yaml"
ACTION="${1:-start}"

_is_running() {
    $APPTAINER instance list 2>/dev/null | grep -q "$INSTANCE_NAME"
}

case "$ACTION" in
    start)
        if _is_running; then
            echo "Gateway already running (instance: $INSTANCE_NAME)"
            exit 0
        fi
        if [ ! -f "$GATEWAY_CONFIG" ]; then
            echo "ERROR: Config not found at $GATEWAY_CONFIG" >&2
            exit 1
        fi
        ENV_FLAGS=()
        # AWS_REGION is forwarded so litellm's boto3 Bedrock client targets the
        # right region. us-east-2 is the only region with Anthropic use-case
        # approval on this account for opus/sonnet — without this, boto3
        # defaults to us-east-1 (unapproved) and returns the misleading
        # "use case form not submitted" control-plane error.
        for _ev in LITELLM_MASTER_KEY ANTHROPIC_API_KEY BEDROCK_API_KEY OLLAMA_API_KEY OPENAI_API_KEY GEMINI_API_KEY MISTRAL_API_KEY DEEPSEEK_API_KEY OPENROUTER_API_KEY GROQ_API_KEY TOGETHERAI_API_KEY FIREWORKS_AI_API_KEY AZURE_API_KEY AZURE_API_BASE AWS_REGION AWS_DEFAULT_REGION; do
            if [ -n "${!_ev:-}" ]; then
                ENV_FLAGS+=(--env "$_ev=${!_ev}")
            fi
        done

        $APPTAINER instance start \
                "${ENV_FLAGS[@]}" \
                --bind "$GATEWAY_CONFIG":/app/config.yaml \
                --bind "$TMPDIR":/tmp:rw \
                --writable-tmpfs \
                --cleanenv \
                --contain \
              "$BASEDIR/Pam/gateway.sif" \
              "$INSTANCE_NAME" \
              --config /app/config.yaml --port "$GATEWAY_PORT"

        echo -n "Waiting for gateway on port $GATEWAY_PORT..."
        for i in $(seq 1 30); do
            if curl -sf "http://localhost:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
                echo " ready."
                exit 0
            fi
            if ! _is_running; then
                echo " instance died."
                exit 1
            fi
            [ "$i" -eq 30 ] && { echo " FAILED."; exit 1; }
            sleep 1
            echo -n "."
        done
        ;;
    stop)
        if _is_running; then
            $APPTAINER instance stop "$INSTANCE_NAME" 2>/dev/null
            echo "Gateway stopped."
        else
            echo "Gateway not running."
        fi
        ;;
    status)
        if _is_running; then
            echo "Gateway running (instance: $INSTANCE_NAME, port: $GATEWAY_PORT)"
            curl -sf "http://localhost:${GATEWAY_PORT}/health" >/dev/null 2>&1 \
                && echo "  Health: OK" || echo "  Health: FAILED"
        else
            echo "Gateway not running."
        fi
        ;;
    *)
        echo "Usage: gateway.sh [start|stop|status]"
        exit 1
        ;;
esac
