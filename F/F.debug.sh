#!/usr/bin/env bash
set -euo pipefail

# Interactive debug shell inside the SciF container.
# Run from any task dir (e.g. F/tasks/<task>_<ts>) to continue work manually:
#   - $PWD is mounted at /srv and is the shell's HOME + cwd
#   - F/mnt -> /mnt and F/home -> /home (same as the running agent sees)
#   - /tmp is a fresh per-run bind (discarded on exit)
#   - if $PWD/env.sh exists, it is sourced so bare python/gcc/... resolves
#     to whatever env the agent used during the run (local_env / common_env)
#   - GPU auto-detect: respects $CUDA_VISIBLE_DEVICES if set, else falls back
#     to nvidia-smi. Passes --nv when any GPU is visible.

for v in BASEDIR APPTAINER SIF OVERLAY; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v not set. Source ENV.sh first." >&2; exit 1; fi
done

BINDS=( --bind "$PWD":/srv:rw --bind "${TMPDIR:-/tmp}":/tmp:rw )
[ -d "$BASEDIR/F/mnt" ]  && BINDS+=( --bind "$BASEDIR/F/mnt":/mnt:rw )
[ -d "$BASEDIR/F/home" ] && BINDS+=( --bind "$BASEDIR/F/home":/home:rw )

# GPU auto-detect — CUDA_VISIBLE_DEVICES wins, nvidia-smi is the fallback.
GPU_ARGS=()
if [ -n "${CUDA_VISIBLE_DEVICES:-}" ]; then
    GPU_ARGS=( --nv )
    export APPTAINERENV_CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES"
    echo "[F.debug] GPU: --nv, CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES (respected from host)" >&2
elif command -v nvidia-smi >/dev/null 2>&1 \
     && VIS=$(nvidia-smi --query-gpu=index --format=csv,noheader,nounits 2>/dev/null | paste -sd, -) \
     && [ -n "$VIS" ]; then
    GPU_ARGS=( --nv )
    echo "[F.debug] GPU: --nv, all host GPUs visible ($VIS)" >&2
else
    echo "[F.debug] GPU: none (no CUDA_VISIBLE_DEVICES, no nvidia-smi)" >&2
fi

$APPTAINER exec \
        --overlay "$OVERLAY":ro \
        "${BINDS[@]}" \
        ${GPU_ARGS[@]+"${GPU_ARGS[@]}"} \
        --cleanenv \
        --contain \
        --no-home \
        --pwd /srv \
      "$SIF" \
      bash -c '
export HOME=/srv
export MAMBA_ROOT_PREFIX=/F/mamba
eval "$(/usr/local/bin/micromamba shell hook -s bash)"
micromamba activate driver
[ -f /srv/env.sh ] && . /srv/env.sh
exec bash
'
