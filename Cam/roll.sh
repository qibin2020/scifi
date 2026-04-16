#!/usr/bin/env bash
# Cam log roller �� compress old JSONL, archive by month. Never deletes.
#
# Usage:
#   bash roll.sh                # compress jsonl older than 1 day, archive gz older than 7 days
#   bash roll.sh --age 0        # compress all jsonl (even today's)
#   bash roll.sh --age 3        # compress jsonl older than 3 days
#   bash roll.sh --dry-run      # show what would happen
#
# What it does:
#   1. gzip .jsonl files older than --age days (default 1). Still readable: zcat *.jsonl.gz
#   2. Move .jsonl.gz files older than 7 days into monthly subdirectories
#
# Safe to run from cron or manually. Idempotent. Nothing is ever deleted.

set -euo pipefail

CAM_DIR="${CAM_DIR:-$BASEDIR/Cam}"
DRY_RUN=false
AGE=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --age)     AGE="${2:?--age requires a number of days}"; shift 2 ;;
        *)         echo "Unknown option: $1"; exit 1 ;;
    esac
done

run() {
    if $DRY_RUN; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

# --- Step 1: Compress .jsonl older than AGE days ---
count=0
if [ "$AGE" -eq 0 ]; then
    FIND_AGE=()  # match all .jsonl files
else
    FIND_AGE=(-mtime +"$((AGE - 1))")
fi
while IFS= read -r -d '' f; do
    run gzip "$f"
    ((count++)) || true
done < <(find "$CAM_DIR" -maxdepth 1 -name '*.jsonl' "${FIND_AGE[@]}" -print0 2>/dev/null)
[ $count -gt 0 ] && echo "[roll] compressed $count file(s)"

# --- Step 2: Move .jsonl.gz older than 7 days into monthly dirs ---
count=0
while IFS= read -r -d '' f; do
    base="$(basename "$f")"
    # Extract YYYYMM from filename timestamp (e.g. driver_task_20260404120000.jsonl.gz)
    if [[ "$base" =~ _([0-9]{4})([0-9]{2})[0-9]{8}\.jsonl\.gz$ ]]; then
        ym="${BASH_REMATCH[1]}-${BASH_REMATCH[2]}"
    else
        ym="other"
    fi
    run mkdir -p "$CAM_DIR/$ym"
    run mv "$f" "$CAM_DIR/$ym/"
    ((count++)) || true
done < <(find "$CAM_DIR" -maxdepth 1 -name '*.jsonl.gz' -mtime +7 -print0 2>/dev/null)
[ $count -gt 0 ] && echo "[roll] archived $count file(s) into monthly dirs"

echo "[roll] done."
