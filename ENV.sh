export BASEDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH=$BASEDIR:$PATH

## System defaults
export TMPDIR=${TMPDIR:-/tmp}

## Paths
# Pick an apptainer build from CVMFS that roughly matches the host's
# (architecture, libc era). Host OS major version maps to an "el" major
# version (RHEL-style); the match is approximate — e.g. Debian 13 ~ el10,
# Debian 12 ~ el9. Matching the main version is good enough.
_detect_apptainer() {
    local base="/cvmfs/atlas.cern.ch/repo/containers/sw/apptainer"
    local arch el_ver candidate v
    case "$(uname -m)" in
        x86_64)         arch="x86_64" ;;
        aarch64|arm64)  arch="aarch64" ;;
        *)              return 1 ;;
    esac
    if [[ -r /etc/os-release ]]; then
        local ID="" VERSION_ID=""
        . /etc/os-release
        local major="${VERSION_ID%%.*}"
        case "$ID" in
            rhel|centos|almalinux|rocky|ol|scientific)
                el_ver="$major" ;;
            debian)
                el_ver=$(( major - 3 )) ;;
            ubuntu)
                case "$major" in
                    24|25|26) el_ver=10 ;;
                    22|23)    el_ver=9  ;;
                    20|21)    el_ver=8  ;;
                    18|19)    el_ver=7  ;;
                esac ;;
            sles|sle*|opensuse*)
                case "$major" in
                    16) el_ver=10 ;;
                    15) el_ver=9  ;;
                    12) el_ver=7  ;;
                esac ;;
            fedora)
                if   (( major >= 38 )); then el_ver=10
                elif (( major >= 34 )); then el_ver=9
                elif (( major >= 29 )); then el_ver=8
                else                         el_ver=7
                fi ;;
        esac
    fi
    # Preferred match first, then newest → oldest available.
    for v in "$el_ver" 10 9 8 7; do
        [[ -z "$v" ]] && continue
        candidate="$base/${arch}-el${v}/current/bin/apptainer"
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

APPTAINER="$(_detect_apptainer)" || APPTAINER="$(command -v apptainer 2>/dev/null)"
export APPTAINER
unset -f _detect_apptainer

_check_apptainer() {
    if [[ -n "$APPTAINER" && -x "$APPTAINER" ]]; then
        return 0
    fi
    {
        echo "ERROR: apptainer not available."
        echo "  APPTAINER     = ${APPTAINER:-<unset>}"
        echo "  uname -m      = $(uname -m)"
        if [[ -r /etc/os-release ]]; then
            local ID="" VERSION_ID=""
            . /etc/os-release
            echo "  OS            = ${ID} ${VERSION_ID}"
        fi
        echo "  CVMFS scanned = /cvmfs/atlas.cern.ch/repo/containers/sw/apptainer/<arch>-el{7,8,9,10}"
        if [[ -d /cvmfs/atlas.cern.ch/repo/containers/sw/apptainer ]]; then
            echo "  Available     = $(ls /cvmfs/atlas.cern.ch/repo/containers/sw/apptainer 2>/dev/null | tr '\n' ' ')"
        else
            echo "  CVMFS path is not mounted."
        fi
        echo "  Fix: mount CVMFS (atlas.cern.ch), or install apptainer on PATH."
    } >&2
    return 1
}
_check_apptainer || return 1 2>/dev/null || exit 1
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
## Pinned LiteLLM image (ghcr.io upstream). Bump deliberately; do NOT auto-follow latest.
export GATEWAY_IMAGE=ghcr.io/berriai/litellm
export GATEWAY_TAG=v1.83.3-stable

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
##
## System-level limits are intentionally minimal:
##   - MAX_ITERATIONS: per-SAM iteration cap (single global cap, no per-rank scaling)
##   - MAX_RETRIES   : SAM retry budget — # of RALPH attempts before giveup
##   - MAX_BASH_TIME : per-bash-call timeout (only applies when task BashTime != -1)
##   - TOTAL_WALL_PER_RANK: per-rank total wall incl. bash — hard clock safety cap
##     (rank otherwise only hints model selection in Pam; it does not scale iters
##     or LLM-only wall — those come from MAX_ITERATIONS and per-task Timeout).
##
export MAX_ITERATIONS=50         # global per-SAM iteration cap
export CHECKPOINT_EVERY=5        # re-ground every N effective iters (re-inject task + memory)
export MAX_CONTEXT=80            # max LLM messages kept before trim (first 2 + last N-3)
export MAX_DEPTH=5               # max subtask nesting depth
export MAX_REVIEW_ITER=100       # review agent iter limit (verify/triage)
export MAX_REFLECT_ITER=15       # reflection agent iter limit (after MAX_RETRIES exhausted)
export MAX_RETRIES=5             # SAM RALPH-retry budget — review rejections before reflect
export MAX_PARALLEL_AGENTS=4     # concurrent subtask cap (scheduler semaphore)
export MAX_BASH_TIME=300         # per-bash-call timeout cap (BashTime: -1 in task disables)
export TOTAL_WALL_PER_RANK=3600,3600,3600,3600,3600,3600   # per-rank total wall incl. bash; 1 hr uniform safety cap

## Driver — robustness knobs (all optional; driver.py + portal.py fall back to
## the defaults shown). ERROR_LIMIT and NUDGE_LIMIT both trigger session-level
## model blacklist when the threshold is hit; raise to be more tolerant of
## upstream flake (Ollama Cloud bursts, transient 5xx), lower for tighter
## detection of fundamentally broken models. MAX_RECOVERY caps delay/retry
## rounds after LOOP_EXHAUSTED. MAX_REVIEW_ITER_VERIFY and TOOL_RESULT_CAP
## are budget knobs (no blacklist effect).
# export ERROR_LIMIT=5             # consecutive API errors → blacklist worker model
# export NUDGE_LIMIT=5             # consecutive no-tool / malformed-tool turns → blacklist
# export MAX_RECOVERY=3            # delay/retry rounds after LOOP_EXHAUSTED before giving up
# export MAX_REVIEW_ITER_VERIFY=30 # iter floor for verify-heavy done-case reviews
# export TOOL_RESULT_CAP=10000     # chars kept of bash/read_file tool result (head + last 5 lines)

## Evolution
export MAX_EVOLVE_ITER=20

## Cam (write-only audit recording)
export CAM_DIR="$BASEDIR/Cam"
