#!/usr/bin/env bash
set -euo pipefail

# Check required env
for v in BASEDIR GATEWAY_PORT; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

echo ""
echo "Stopping gateway..."
bash "$BASEDIR/Pam/gateway.sh" stop

echo ""
echo "============================================================"
echo "  always_young — stopped"
echo "============================================================"
echo ""
echo "  Gateway:  stopped"
echo "  Tasks:    F/tasks/ (preserved)"
echo "  Audit:    Cam/ (preserved)"
echo ""
echo "  To restart:  bash START.sh"
echo "============================================================"
