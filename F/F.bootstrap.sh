#!/usr/bin/env bash
set -euo pipefail

# Check required env
for v in APPTAINER SIF OVERLAY FDIR; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

echo "=== F Bootstrap ==="

# Pre-check: SIF must exist
if [ ! -f "$SIF" ]; then
    echo "ERROR: Container image not found at $SIF" >&2
    echo "  Run Kam bootstrap first: bash Kam/rl9_micromamba.bootstrap.sh 0" >&2
    exit 1
fi

# 1. Create overlay (2GB, NOT sparse)
if [ ! -f "$OVERLAY" ]; then
    echo "Creating overlay: $OVERLAY (2GB)..."
    $APPTAINER overlay create --size 2048 --create-dir /F/mamba "$OVERLAY"
    echo "Overlay created."
else
    echo "Overlay exists: $OVERLAY"
fi

# 2. Create directories
mkdir -p "$FDIR/run" "$FDIR/tasks"

# 3. Install env into overlay
echo "Installing mamba env into overlay..."
$APPTAINER exec \
        --overlay "$OVERLAY" \
        --bind $TMPDIR:/tmp:rw \
        --cleanenv \
        --no-home \
        --no-mount cwd \
        --contain \
      "$SIF" \
      bash -c '
set -euo pipefail
export MAMBA_ROOT_PREFIX=/F/mamba
eval "$(/usr/local/bin/micromamba shell hook -s bash)"

if micromamba env list | grep -q "driver"; then
    echo "Env already exists, updating..."
    micromamba run -n driver pip install --no-cache-dir openai requests
else
    echo "Creating driver env..."
    mkdir -p /F/mamba
    micromamba create -y -n driver -c conda-forge python=3.12
    micromamba run -n driver pip install --no-cache-dir openai requests
fi

echo "=== Verify ==="
micromamba run -n driver python --version
micromamba run -n driver python -c "import openai; print(f\"openai {openai.__version__}\")"
echo "=== Done ==="
'

# Verify overlay has the env
$APPTAINER exec \
        --overlay "$OVERLAY":ro \
        --bind "$TMPDIR":/tmp:rw \
        --cleanenv \
        --contain \
      "$SIF" \
      bash -c '
export MAMBA_ROOT_PREFIX=/F/mamba
eval "$(/usr/local/bin/micromamba shell hook -s bash)"
micromamba run -n driver python -c "import openai" 2>/dev/null
' || { echo "ERROR: overlay verify failed — openai not importable." >&2; exit 1; }

echo "=== F Bootstrap OK ==="
echo "  Overlay: $OVERLAY"
echo "  Run:     $FDIR/run/"
echo "  Tasks:   $FDIR/tasks/"
