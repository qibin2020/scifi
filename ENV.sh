export BASEDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH=$BASEDIR:$PATH

## System defaults
export TMPDIR=${TMPDIR:-/tmp}

## Paths
# export APPTAINER=/cvmfs/atlas.cern.ch/repo/containers/sw/apptainer/x86_64-el10/current/bin/apptainer
export APPTAINER=$(which apptainer)
export SIF=$BASEDIR/Kam/rl9_micromamba_0.sif
export OVERLAY=$BASEDIR/F/F.overlay.img
export FDIR=$BASEDIR/F
export TASKS_SRC=$BASEDIR/Sam/tasks
export SKILLS_SRC=$BASEDIR/Nam/skills
export RANK_SRC=$BASEDIR/Pam/gateway.rank.yaml

## Gateway
if [[ ! -f ${BASEDIR}/.secret.sh ]]; then
    echo "ERROR: ${BASEDIR}/.secret.sh not found. Copy from .secret.sh.template and fill in your keys." >&2
    return 1 2>/dev/null || exit 1
fi
chmod 600 ${BASEDIR}/.secret.sh
. ${BASEDIR}/.secret.sh
export GATEWAY_PORT=$(( ($(id -u) % 55535) + 10000 ))
# export LITELLM_MASTER_KEY=   # leave unset → litellm runs without master key auth

## Fallback model groups (hardcoded model names in the system)
## FALLBACK_HIGHEST/FALLBACK_WORKING: used when ranking system (gateway.rank.yaml) is unavailable
## See Pam/gateway.model.yaml for supported model names. Models sharing same name become group, supported for load balancing and high availability.
export FALLBACK_HIGHEST=fallback
export FALLBACK_WORKING=fallback
## SCIFI_MODEL: hardcoded model or group name for the SciFi natural language interface
export SCIFI_MODEL=ui

## Default env skill (auto-injected when a task declares no env skill)
## One of: common_env | local_env | temp_env
export DEFAULT_ENV_SKILL=temp_env

## Driver — limits
export MAX_ITERATIONS=50
export CHECKPOINT_EVERY=5
export MAX_CONTEXT=80
export MAX_DEPTH=5
export MAX_REVIEW_ITER=10
export MAX_REFLECT_ITER=15
export MAX_RETRIES=3
export MAX_PARALLEL_AGENTS=4
export MAX_BASH_TIME=300
export WALL_LIMIT_PER_RANK=600,1200,2400,3000,3600,6000
export ITER_LIMIT_PER_RANK=100,200,300,300,500,500
export TOTAL_WALL_PER_RANK=1800,1800,1800,1800,1800,1800

## Evolution
export MAX_EVOLVE_ITER=20

## Cam (write-only audit recording)
export CAM_DIR="$BASEDIR/Cam"
