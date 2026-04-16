#!/usr/bin/env bash
set -euo pipefail

# Check required env
for v in BASEDIR FDIR; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

echo "============================================================"
echo "  MAINTAIN — evolution + audit roll"
echo "============================================================"
echo ""

# ---- Evolution: suggest ----
echo "=== [1/3] Evolution: suggest ==="
python3 "$BASEDIR/F/portal.py" evolution suggest
echo ""

# ---- Evolution: model ----
echo "=== [2/3] Evolution: model ==="
python3 "$BASEDIR/F/portal.py" evolution model
echo ""

# ---- Cam: roll logs ----
echo "=== [3/3] Cam: roll audit logs ==="
bash "$BASEDIR/Cam/roll.sh"
echo ""

echo "============================================================"
echo "  MAINTAIN COMPLETE"
echo "============================================================"
echo "  Global memory:     F/run/.global_memory.md"
echo "  Suggestions:       F/run/.global_suggestion.md"
echo "  Model config:      Pam/gateway.rank.yaml"
echo "  Audit logs:        Cam/"
echo "============================================================"
