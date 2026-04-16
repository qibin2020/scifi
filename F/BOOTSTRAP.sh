#!/usr/bin/env bash
set -euo pipefail

# Check required env (SciF sources ENV.sh before calling this)
for v in BASEDIR APPTAINER SIF OVERLAY FDIR TASKS_SRC SKILLS_SRC RANK_SRC GATEWAY_PORT; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

_step_ok()   { echo "  [ok] $*"; echo ""; }
_step_fail() { echo "  [FAIL] $*" >&2; echo "  Bootstrap aborted. Fix the issue above and re-run." >&2; exit 1; }

echo "============================================================"
echo "  BOOTSTRAP"
echo "============================================================"
echo ""

# ---- Pam: Gateway ----
echo "=== [1/4] Pam: Gateway ==="
bash "$BASEDIR/Pam/gateway.bootstrap.sh" || _step_fail "Gateway bootstrap failed."

# Quick gateway test: start, verify, stop immediately (don't hold during Kam/F build)
echo "Verifying gateway..."
_GW_PID=""
_kill_gw() {
    if [ -n "$_GW_PID" ]; then
        # Kill the process group (shell + apptainer + litellm)
        kill -- -"$_GW_PID" 2>/dev/null || kill "$_GW_PID" 2>/dev/null
        wait "$_GW_PID" 2>/dev/null || true
        _GW_PID=""
    fi
}

setsid bash "$BASEDIR/Pam/gateway.debug.sh" >/dev/null 2>&1 &
_GW_PID=$!
GW_READY=false
for i in $(seq 1 60); do
    if curl -sf -m 3 "http://localhost:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
        GW_READY=true; break
    fi
    if ! kill -0 "$_GW_PID" 2>/dev/null; then
        _GW_PID=""; _step_fail "Gateway process died during startup."
    fi
    sleep 1
done
if ! $GW_READY; then
    _kill_gw; _step_fail "Gateway did not become healthy within 60s."
fi
MODELS=$(curl -sf "http://localhost:${GATEWAY_PORT}/v1/models" 2>/dev/null | python3 -c "
import sys, json; print(len(json.load(sys.stdin).get('data', [])))" 2>/dev/null || echo "0")
_kill_gw  # stop immediately — not needed during Kam/F build
if [ "$MODELS" -eq 0 ]; then
    _step_fail "Gateway started but no models available. Check Pam/gateway.model.yaml."
fi
_step_ok "Pam ready ($MODELS models, gateway verified and stopped)."

# ---- Kam: Containers (can be slow) ----
echo "=== [2/4] Kam: Containers ==="
bash "$BASEDIR/Kam/rl9_micromamba.bootstrap.sh" 0 || _step_fail "L0 container build failed."
_step_ok "Kam ready."

# ---- F: Driver runtime ----
echo "=== [3/4] F: Driver overlay ==="
bash "$BASEDIR/F/F.bootstrap.sh" || _step_fail "F overlay bootstrap failed."
_step_ok "F ready."

# ---- Smoke test: start gateway again, run task, stop ----
echo "=== [4/4] Smoke test ==="
if [ -d "$TASKS_SRC/test_hello" ]; then
    setsid bash "$BASEDIR/Pam/gateway.debug.sh" >/dev/null 2>&1 &
    _GW_PID=$!
    trap '_kill_gw' EXIT
    for i in $(seq 1 60); do
        curl -sf -m 3 "http://localhost:${GATEWAY_PORT}/health" >/dev/null 2>&1 && break
        sleep 1
    done
    python3 "$BASEDIR/F/portal.py" driver test_hello || { _kill_gw; _step_fail "Smoke test failed."; }
    _kill_gw
    trap - EXIT
    _step_ok "Smoke test passed."
else
    echo "SKIP: no test_hello task in $TASKS_SRC"
    echo ""
fi

echo ""
echo "============================================================"
echo "  BOOTSTRAP COMPLETE"
echo "============================================================"
echo "  Pam: $(du -h "$BASEDIR/Pam/gateway.sif" 2>/dev/null | cut -f1)  ($MODELS models)"
echo "  Kam: $(du -h "$SIF" 2>/dev/null | cut -f1)"
echo "  F:   $(du -h "$OVERLAY" 2>/dev/null | cut -f1)"
echo ""
echo "  Next: SciF START"
echo "============================================================"
