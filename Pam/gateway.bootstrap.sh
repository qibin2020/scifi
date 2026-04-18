#!/usr/bin/env bash
set -euo pipefail

# Check required env
for var in BASEDIR APPTAINER GATEWAY_IMAGE GATEWAY_TAG; do
    if [ -z "${!var:-}" ]; then
        echo "ERROR: $var is not set. Source ENV.sh first." >&2
        exit 1
    fi
done
if [ ! -x "$APPTAINER" ]; then
    echo "ERROR: apptainer not found at $APPTAINER" >&2
    exit 1
fi

PAM="$BASEDIR/Pam"

# Check secret config exists and has real API keys
SECRET="$PAM/gateway.model.yaml"
if [ ! -f "$SECRET" ]; then
    echo "ERROR: $SECRET not found." >&2
    echo "  Copy gateway.model.yaml.template → gateway.model.yaml" >&2
    echo "  and fill in your API keys." >&2
    exit 1
fi
if grep -q '<SETME>' "$SECRET"; then
    echo "ERROR: $SECRET still has <SETME> placeholder(s)." >&2
    echo "  Edit the file and replace all <SETME> with real API keys:" >&2
    grep -n '<SETME>' "$SECRET" | sed 's/^/    /' >&2
    exit 1
fi
# Check that at least one API-key env var referenced in model yaml is set
_keys_needed=$(grep -oP 'os\.environ/\K\w+' "$SECRET" | sort -u)
_any_set=false
for _key_var in $_keys_needed; do
    _val="${!_key_var:-}"
    if [ -n "$_val" ] && [ "$_val" != "<SETME>" ]; then
        _any_set=true
    fi
done
if [ "$_any_set" = false ]; then
    echo "ERROR: no API keys are set. Need at least one of:" >&2
    echo "$_keys_needed" | sed 's/^/  /' >&2
    exit 1
fi

# Check rank config — auto-generate if missing
RANK="$PAM/gateway.rank.yaml"
if [ ! -f "$RANK" ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  WARNING: gateway.rank.yaml not found — auto-generating"
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo ""
    echo "  Scanning gateway.model.yaml for model names..."
    echo "  All models will be set to rank=0, budget=-1, thinkable=false."
    echo "  This is safe but suboptimal. Run 'SciF MAINTAIN' after bootstrap"
    echo "  to let evolution assign proper ranks."
    echo ""

    python3 -c "
import re, sys
with open('$SECRET') as f:
    text = f.read()
names = sorted(set(re.findall(r'model_name:\s*(\S+)', text)))
if not names:
    print('ERROR: no model_name entries found in secret yaml', file=sys.stderr)
    sys.exit(1)
print('# Auto-generated rank config — all rank 0, budget -1, thinkable false')
print('# Run SciF MAINTAIN (evolution model) to assign proper ranks.')
print('')
print('models:')
for n in names:
    print(f'  - rank: 0')
    print(f'    name: {n}')
    print(f'    budget: -1')
    print(f'    thinkable: false')
print('')
print('connection_max: 10')
" > "$RANK"

    echo "  Generated $RANK with $(grep -c 'name:' "$RANK") model(s):"
    grep 'name:' "$RANK" | sed 's/^/    /'
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo ""
fi

echo "=== Pulling ${GATEWAY_IMAGE}:${GATEWAY_TAG} ==="
PRECURSOR="$PAM/gateway.precursor.sif"
FINAL="$PAM/gateway.sif"

if [ -f "$PRECURSOR" ]; then
    echo "precursor exists, skipping pull."
else
    $APPTAINER pull "$PRECURSOR" "docker://${GATEWAY_IMAGE}:${GATEWAY_TAG}"
    if [ ! -f "$PRECURSOR" ]; then
        echo "ERROR: precursor SIF not created. Pull failed." >&2
        exit 1
    fi
fi

# Build final SIF from def (adds startscript for instance mode)
if [ -f "$FINAL" ]; then
    echo "gateway.sif exists, skipping build."
else
    echo "=== Building gateway.sif ==="
    OLD_CWD="$PWD"
    cd "$PAM"
    APPTAINER_TMPDIR="${TMPDIR:-/tmp}" $APPTAINER build --tmpdir "${TMPDIR:-/tmp}" gateway.sif gateway.def 2>&1
    cd "$OLD_CWD"
    if [ ! -f "$FINAL" ]; then
        echo "ERROR: gateway.sif not created. Build failed." >&2
        exit 1
    fi
fi

# Clean up precursor
rm -f "$PRECURSOR"

echo "=== Pam bootstrap OK: $(du -h "$FINAL" | cut -f1) ==="
