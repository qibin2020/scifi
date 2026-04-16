#!/usr/bin/env bash
set -euo pipefail

# Check required env
for v in BASEDIR APPTAINER SIF OVERLAY FDIR; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

echo "============================================================"
echo "  RESET — always_young system"
echo "============================================================"
echo ""
echo "  This will REMOVE:"
echo "    F/   — overlay image, run/ (global memory/history/suggestions)"
echo "    Kam/ — all .sif container images"
echo "    Pam/ — gateway.sif"
echo ""
echo "  This will KEEP:"
echo "    F/tasks/         — all completed task runs"
echo "    Sam/             — task definitions + task_maker"
echo "    Nam/             — skills + skill_maker"
echo "    Cam/             — all audit logs"
echo "    Pam/gateway.*    — config files (rank, secret)"
echo "    ENV.sh           — environment config"
echo ""
read -p "  Continue? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "  Aborted."
    exit 0
fi
echo ""

# ---- Stop running gateway ----
echo "[reset] Stopping gateway instances..."
$APPTAINER instance stop -a 2>/dev/null || true

# ---- F: Remove overlay and run/ ----
echo "[reset] F: removing overlay and run/..."
if [ -f "$OVERLAY" ]; then
    mv "$OVERLAY" "${OVERLAY}.bak"
    echo "  overlay → ${OVERLAY}.bak"
fi
if [ -d "$FDIR/run" ]; then
    mv "$FDIR/run" "$FDIR/run.bak.$(date +%Y%m%d%H%M%S)"
    echo "  run/ → run.bak.*"
fi
echo "  KEPT: F/tasks/ ($(ls "$FDIR/tasks" 2>/dev/null | wc -l) task runs)"

# ---- Kam: Remove SIFs ----
echo "[reset] Kam: removing .sif files..."
for sif in "$BASEDIR/Kam/"*.sif; do
    [ -f "$sif" ] || continue
    mv "$sif" "${sif}.bak"
    echo "  $(basename "$sif") → $(basename "${sif}.bak")"
done

# ---- Pam: Remove gateway SIF ----
echo "[reset] Pam: removing gateway.sif..."
if [ -f "$BASEDIR/Pam/gateway.sif" ]; then
    mv "$BASEDIR/Pam/gateway.sif" "$BASEDIR/Pam/gateway.sif.bak"
    echo "  gateway.sif → gateway.sif.bak"
fi

echo ""
echo "============================================================"
echo "  RESET COMPLETE"
echo "============================================================"
echo "  All runtime state cleared (backed up as .bak files)."
echo "  Tasks, skills, audit logs, and configs preserved."
echo ""
echo "  To fully rebuild: bash BOOTSTRAP.sh"
echo "  To clean .bak files: rm -f Kam/*.bak Pam/*.bak F/*.bak"
echo "============================================================"
