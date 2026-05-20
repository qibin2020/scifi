#!/bin/bash
set -u
cd /home/u0/Work/scifi
source ENV.sh

MAX_RETRIES=3
LOGDIR=tools/bench/apass_logs
STATES_DIR=tools/bench/states
WORKBASE=tools/bench/apass_work
mkdir -p "$LOGDIR" "$WORKBASE"

run_task() {
    local task=$1
    local tname=$(basename $task)
    local workdir="$WORKBASE/${tname}_$$"

    for attempt in $(seq 1 $MAX_RETRIES); do
        rm -rf "$workdir"
        mkdir -p "$workdir"
        cp -al "$STATES_DIR/warm/mnt" "$workdir/mnt"

        local log="$LOGDIR/${tname}_attempt${attempt}.log"
        echo "[$(date +%H:%M:%S)] $tname attempt $attempt starting" >&2
        local t0=$(date +%s)

        FDIR="$workdir" bash SciF RUN "$task" > "$log" 2>&1
        local rc=$?
        local wall=$(( $(date +%s) - t0 ))

        local camfile=$(ls -t Cam/driver_${tname}_*.jsonl 2>/dev/null | head -1)
        local verdict="UNKNOWN"
        if [ -n "$camfile" ]; then
            verdict=$(python3 -c "
import json
v='UNKNOWN'
for line in open('$camfile'):
    d=json.loads(line.strip())
    ev=d.get('event','')
    if ev in ('SAM_VERIFIED','REVIEW_VERDICT_PASS'): v='PASS'
    elif ev=='TOTAL_WALL_LIMIT': v='TIMEOUT'
print(v)
" 2>/dev/null)
        fi
        echo "[$(date +%H:%M:%S)] $tname attempt $attempt: verdict=$verdict rc=$rc wall=${wall}s"

        rm -rf "$workdir"

        if [ "$verdict" = "PASS" ]; then
            return 0
        fi
    done
    return 1
}

echo "=== A-PASS sanity test: c1+c2+c3 parallel, max $MAX_RETRIES retries each ==="
echo "=== State isolation: per-task workdir under $WORKBASE ==="
echo "Started: $(date)"

run_task sci_study/fw_complete1 &
pid1=$!
run_task sci_study/fw_complete2 &
pid2=$!
run_task sci_study/fw_complete3 &
pid3=$!

wait $pid1; r1=$?
wait $pid2; r2=$?
wait $pid3; r3=$?

echo ""
echo "=== RESULTS ==="
echo "c1: $([ $r1 -eq 0 ] && echo PASS || echo FAIL)"
echo "c2: $([ $r2 -eq 0 ] && echo PASS || echo FAIL)"
echo "c3: $([ $r3 -eq 0 ] && echo PASS || echo FAIL)"
echo "Finished: $(date)"
