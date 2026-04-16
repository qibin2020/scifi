#!/usr/bin/env bash
set -euo pipefail

# Check required env (gateway.sh checks its own)
for v in BASEDIR GATEWAY_PORT; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

# ---- Start gateway ----
bash "$BASEDIR/Pam/gateway.sh" start

echo ""
echo "============================================================"
echo "  always_young — READY"
echo "============================================================"
echo ""
echo "  Gateway: http://localhost:${GATEWAY_PORT}"
echo ""
echo "  --- Run a task ---"
echo "  SciF RUN <task_name>"
echo ""
echo "  --- Create a task ---"
echo "  bash Sam/task_maker.sh description.md [output_dir]"
echo ""
echo "  --- Create a skill ---"
echo "  bash Nam/skill_maker.sh description.md [skill_name]"
echo ""
echo "  --- Available tasks ---"
ls "$TASKS_SRC" 2>/dev/null | sed 's/^/    /' || echo "    (none)"
echo ""
echo "  --- Output ---"
echo "  Task results:   F/tasks/<task_name>_<timestamp>/"
echo "  Global state:   F/run/"
echo "  Audit logs:     Cam/"
echo ""
echo "  --- Debug ---"
echo "  Container shell:    bash Kam/rl9_micromamba.debug.sh"
echo "  Gateway foreground: bash Pam/gateway.debug.sh"
echo "  Gateway status:     bash Pam/gateway.sh status"
echo "  Task history:       cat F/tasks/<task>/.history_index.md"
echo "  Global history:     cat F/run/.global_history.md"
echo ""
echo "  --- Stop ---"
echo "  bash Pam/gateway.sh stop"
echo "============================================================"
