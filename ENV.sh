export BASEDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

## Paths
export APPTAINER=/cvmfs/atlas.cern.ch/repo/containers/sw/apptainer/x86_64-el10/current/bin/apptainer
export SIF=$BASEDIR/Kam/rl9_micromamba_0.sif
export OVERLAY=$BASEDIR/F/F.overlay.img
export FDIR=$BASEDIR/F
export TASKS_SRC=$BASEDIR/Sam/tasks
export SKILLS_SRC=$BASEDIR/Nam/skills
export RANK_SRC=$BASEDIR/Pam/gateway.rank.yaml

## Gateway
[[ -f ${BASEDIR}/.secret.sh ]] && chmod 600 ${BASEDIR}/.secret.sh
. ${BASEDIR}/.secret.sh
export GATEWAY_PORT=$(( ($(id -u) % 55535) + 10000 ))
# export LITELLM_MASTER_KEY=   # leave unset → litellm runs without master key auth

## Fallback models (only hardcoded model names in the system)
## Used when the ranking system (gateway.rank.yaml) is unavailable
export FALLBACK_HIGHEST=fallback_high
export FALLBACK_WORKING=fallback
export SCIFI_MODEL=scifi_model

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
export WALL_LIMIT_PER_RANK=60,120,240,300,360,600
export ITER_LIMIT_PER_RANK=10,20,30,30,50,50
export TOTAL_WALL_PER_RANK=1800,1800,1800,1800,1800,1800

## Evolution
export MAX_EVOLVE_ITER=20

## Cam (write-only audit recording)
export CAM_DIR="$BASEDIR/Cam"
