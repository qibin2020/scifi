#!/usr/bin/env bash
set -euo pipefail

# Build all container layers sequentially (each depends on the previous).
# Run from the Kam/ directory. Requires APPTAINER and network access.
#
# Layers:
#   L0 (118 MB) — Rocky 9 + micromamba + SSH + CLI tools
#   L1 (691 MB) — + EPEL, gcc, mesa, ImageMagick, htop, man pages, minimal LaTeX
#   L2 (977 MB) — + code-server (browser IDE)
#   L3 (1.6 GB) — + X11, TurboVNC, noVNC, Firefox, Okular, Texmaker, ksnip, Zathura, full LaTeX
#
# Usage:
#   bash rl9_micromamba.bootstrap.sh        # build all layers
#   bash rl9_micromamba.bootstrap.sh 0      # build only L0
#   bash rl9_micromamba.bootstrap.sh 1 3    # build L1 and L3
#   bash rl9_micromamba.bootstrap.sh 2+     # build L2 and above

KAM="$BASEDIR/Kam"
OLD_CWD="$PWD"
cd "$KAM"

APPTAINER="${APPTAINER:-/cvmfs/atlas.cern.ch/repo/containers/sw/apptainer/x86_64-el10/current/bin/apptainer}"
BUILD_TMPDIR="${TMPDIR:-/tmp}"

build_layer() {
    local n=$1
    local def="rl9_micromamba_${n}.def"
    local sif="rl9_micromamba_${n}.sif"

    if [ ! -f "$def" ]; then
        echo "ERROR: $def not found" >&2
        return 1
    fi

    # Check dependency: L1+ needs the previous layer's SIF
    if [ "$n" -gt 0 ]; then
        local prev="rl9_micromamba_$(( n - 1 )).sif"
        if [ ! -f "$prev" ]; then
            echo "ERROR: $prev not found — build layer $(( n - 1 )) first" >&2
            return 1
        fi
    fi

    # Skip if SIF already exists
    if [ -f "$sif" ]; then
        echo "[L${n}] $sif exists ($(du -h "$sif" | cut -f1)), skipping."
        return 0
    fi

    echo "[L${n}] building $sif from $def ..."
    APPTAINER_TMPDIR="$BUILD_TMPDIR" "$APPTAINER" build \
        --tmpdir "$BUILD_TMPDIR" \
        "$sif" "$def" 2>&1

    if [ -f "$sif" ]; then
        local size
        size=$(du -h "$sif" | cut -f1)
        echo "[L${n}] done: $sif ($size)"
    else
        echo "[L${n}] FAILED" >&2
        return 1
    fi
}

# Parse arguments
LAYERS=()
if [ $# -eq 0 ]; then
    LAYERS=(0 1 2 3)
else
    for arg in "$@"; do
        if [[ "$arg" == *"+" ]]; then
            start="${arg%+}"
            for (( i=start; i<=3; i++ )); do
                LAYERS+=("$i")
            done
        else
            LAYERS+=("$arg")
        fi
    done
fi

echo "=== Building layers: ${LAYERS[*]} ==="
echo "    Apptainer: $APPTAINER"
echo "    Tmpdir:    $BUILD_TMPDIR"
echo ""

for n in "${LAYERS[@]}"; do
    build_layer "$n"
    echo ""
done

cd "$OLD_CWD"

echo "=== All done ==="
ls -lh "$KAM"/rl9_micromamba_?.sif 2>/dev/null
