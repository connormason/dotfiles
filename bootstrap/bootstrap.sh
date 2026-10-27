#!/usr/bin/env bash
# Bootstrap driver: runs the numbered stage scripts of every layer in order.
#
# Usage: bootstrap.sh [--dry-run] [--list] [--only STAGE] [--from STAGE] [--resume] [--verify] [--no-log]
#
#   --dry-run        Print mutating commands instead of executing them
#   --list           List stages in run order and exit (overlay stages are tagged with their layer root)
#   --only STAGE     Run a single stage (e.g. --only 00-preflight)
#   --from STAGE     Run from STAGE to the end
#   --resume         Run from the stage after the last successfully completed one (see --from)
#   --verify         After stages complete, run `run.py doctor` to verify the environment
#   --no-log         Do not tee this run to a logfile
#   -h, --help       Show this help
#
# Stages are the <layer>/bootstrap/NN-*.sh files of the repo root and every registered overlay (bootstrap/lib.sh:
# dotfiles_layers), merged and sorted by name. A two-digit number may be used only once across all layers. Each stage
# runs as its own `bash` process with BOOTSTRAP_DRY_RUN, DOTFILES_REPO (base layer root) and DOTFILES_LAYER (the
# stage's own layer root) exported.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Help must work even when the overlay registry is broken, so it is handled before lib.sh is sourced.
for arg in "$@"; do
    case "$arg" in
    -h | --help)
        sed -n '2,/^set -euo pipefail/p' "${BASH_SOURCE[0]}" | sed -e '$d' -e 's/^# \{0,1\}//'
        exit 0
        ;;
    esac
done

# Pin the base layer to this checkout: an inherited DOTFILES_REPO from another checkout must not redirect discovery.
DOTFILES_REPO="$(cd "$HERE/.." && pwd -P)"
export DOTFILES_REPO
# shellcheck source=/dev/null  # lib.sh is sourced at runtime from the repo root; shellcheck runs without -x
source "$HERE/lib.sh"
REPO="$DOTFILES_REPO"

# Discover NN-*.sh stages in every layer (base first, then overlays). Two-digit numbers must be unique across all
# layers so the merged order is unambiguous.
STAGE_NAMES=()
STAGE_PATHS=()
LAYERS_OUT="$(dotfiles_layers)" || exit 1

list_stages() {
    local layer f
    while IFS= read -r layer; do
        for f in "$layer"/bootstrap/[0-9][0-9]-*.sh; do
            if [ -f "$f" ]; then
                printf '%s\t%s\n' "$(basename "$f" .sh)" "$f"
            fi
        done
    done <<EOF
$LAYERS_OUT
EOF
}

prev_num=""
while IFS=$'\t' read -r name path; do
    if [ -z "$name" ]; then
        continue
    fi
    num="${name%%-*}"
    if [ "$num" = "$prev_num" ]; then
        die "stage number $num is used twice: ${STAGE_PATHS[${#STAGE_PATHS[@]} - 1]} and $path"
    fi
    prev_num="$num"
    STAGE_NAMES+=("$name")
    STAGE_PATHS+=("$path")
done < <(list_stages | LC_ALL=C sort)

stage_exists() {
    local name="$1" s
    for s in ${STAGE_NAMES[@]+"${STAGE_NAMES[@]}"}; do
        if [ "$s" = "$name" ]; then
            return 0
        fi
    done
    return 1
}

# next_stage_after NAME -> print the stage that runs immediately after NAME; return 1 (print
# nothing) if NAME is the final stage. Assumes NAME exists (guard with stage_exists first).
next_stage_after() {
    local target="$1" s matched=0
    for s in ${STAGE_NAMES[@]+"${STAGE_NAMES[@]}"}; do
        if [ "$matched" = 1 ]; then
            printf '%s' "$s"
            return 0
        fi
        if [ "$s" = "$target" ]; then
            matched=1
        fi
    done
    return 1
}

ONLY="" FROM="" VERIFY=0 LOG=1 RESUME=0
while [ $# -gt 0 ]; do
    case "$1" in
    --dry-run) export BOOTSTRAP_DRY_RUN=1 ;;
    --list)
        for i in ${STAGE_NAMES[@]+"${!STAGE_NAMES[@]}"}; do
            layer="${STAGE_PATHS[$i]%/bootstrap/*}"
            if [ "$layer" = "$REPO" ]; then
                printf '%s\n' "${STAGE_NAMES[$i]}"
            else
                printf '%s  (%s)\n' "${STAGE_NAMES[$i]}" "$layer"
            fi
        done
        exit 0
        ;;
    --only)
        ONLY="${2:-}"
        shift
        ;;
    --from)
        FROM="${2:-}"
        shift
        ;;
    --resume) RESUME=1 ;;
    --verify) VERIFY=1 ;;
    --no-log) LOG=0 ;;
    *) die "unknown argument: $1" ;;
    esac
    shift
done

if [ -n "$ONLY" ] && ! stage_exists "$ONLY"; then
    die "unknown stage: $ONLY"
fi
if [ -n "$FROM" ] && ! stage_exists "$FROM"; then
    die "unknown stage: $FROM"
fi
if [ "$RESUME" = 1 ] && { [ -n "$ONLY" ] || [ -n "$FROM" ]; }; then
    die "--resume cannot be combined with --only/--from"
fi

# Persist the last successfully-completed stage here so --resume can pick up where a failed run
# left off. Lives alongside the run logs under the same state dir (honors BOOTSTRAP_LOG_DIR).
STATE_DIR="${BOOTSTRAP_LOG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles-bootstrap}"
STATE_FILE="$STATE_DIR/last-completed-stage"

# record_stage NAME -> persist NAME as the last completed stage. Skipped under dry-run (nothing
# real happened) and --only (a single stage is not sequential progress). Fail-open like logging.
record_stage() {
    if [ "${BOOTSTRAP_DRY_RUN:-0}" = "1" ] || [ -n "$ONLY" ]; then
        return 0
    fi
    mkdir -p "$STATE_DIR" 2>/dev/null || return 0
    printf '%s\n' "$1" >"$STATE_FILE" 2>/dev/null || true
}

# Resolve --resume into a --from target: start at the stage after the last completed one. A run
# that died at stage X recorded X-1 as complete, so this restarts at X.
if [ "$RESUME" = 1 ]; then
    if [ -s "$STATE_FILE" ]; then
        last_completed="$(cat "$STATE_FILE")"
        if ! stage_exists "$last_completed"; then
            warn "recorded stage '$last_completed' no longer exists — running from the first stage"
        elif FROM="$(next_stage_after "$last_completed")"; then
            log "resuming from stage: $FROM (last completed: $last_completed)"
        else
            log "all stages already completed (last: $last_completed) — nothing to resume"
            rm -f "$STATE_FILE"
            exit 0
        fi
    else
        log "no resume state found — running from the first stage"
    fi
fi

# Tee the whole run to a timestamped logfile so a failure deep into provisioning leaves a
# diagnosable artifact. Set up before priming sudo so the sudo prompt/keepalive is captured too.
# Honors BOOTSTRAP_LOG_DIR; disabled with --no-log. Only stdout/stderr are redirected — stdin
# (sudo/confirm prompts) is untouched.
LOGFILE=""
if [ "$LOG" = "1" ]; then
    LOG_DIR="${BOOTSTRAP_LOG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles-bootstrap}"
    if [ "${BOOTSTRAP_DRY_RUN:-0}" = "1" ]; then
        # Dry-run changes nothing on disk — don't create the log dir/file, just say what would happen.
        log "would tee this run to a logfile under $LOG_DIR"
    else
        mkdir -p "$LOG_DIR"
        LOGFILE="$LOG_DIR/bootstrap-$(date +%Y%m%d-%H%M%S).log"
        # Deliberately fail-open: if $LOG_DIR is unwritable, tee simply can't write and the run
        # continues unlogged rather than aborting provisioning.
        exec > >(tee -a "$LOGFILE") 2>&1
        log "logging to $LOGFILE"
    fi
fi

# Per-stage timing + end-of-run summary state (parallel arrays, indexed together). Distinct from
# STAGE_NAMES/STAGE_PATHS above, which hold every discovered stage rather than the ones that ran.
RESULT_NAMES=() RESULT_STATUS=() RESULT_SECS=()
RUN_START=$SECONDS
FAILED_STAGE=""
VERIFY_STATUS="" # "", "ok", "fail", or "skipped" (dry-run)

# shellcheck disable=SC2329  # invoked indirectly by cleanup() via the EXIT trap
print_summary() {
    local i emoji
    printf '\n'
    log "run summary:"
    for i in ${RESULT_NAMES[@]+"${!RESULT_NAMES[@]}"}; do
        case "${RESULT_STATUS[$i]}" in
        ok) emoji='✅' ;;
        fail) emoji='🔴' ;;
        *) emoji='•' ;;
        esac
        printf '  %s %-16s %s\n' "$emoji" "${RESULT_NAMES[$i]}" "$(fmt_duration "${RESULT_SECS[$i]}")"
    done
    case "$VERIFY_STATUS" in
    ok) printf '  %s %-16s\n' '✅' 'verify (doctor)' ;;
    fail) printf '  %s %-16s\n' '🔴' 'verify (doctor)' ;;
    skipped) printf '  %s %-16s\n' '•' 'verify (dry-run)' ;;
    esac
    printf '  total: %s\n' "$(fmt_duration "$((SECONDS - RUN_START))")"
    if [ -n "$LOGFILE" ]; then
        printf '  log:   %s\n' "$LOGFILE"
    fi
    if [ -n "$FAILED_STAGE" ]; then
        warn "failed at stage: $FAILED_STAGE — resume with: bootstrap.sh --resume (or: --from $FAILED_STAGE)"
    fi
    return 0 # keep a clean status so `set -e` doesn't abort the EXIT trap before it re-exits `rc`
}

# Prime sudo once, here in the driver, and keep it alive for the whole run. The keep-alive loop
# is tied to this process, so it outlives the individual stage subshells (which all share this
# tty's cached credential). No-op under dry-run.
prime_sudo

# Single EXIT handler: reap the sudo keep-alive loop and print the run summary (so the summary
# appears on failure/interrupt too, not just clean completion). Capture the pending exit status
# first and re-exit it, so the summary's own commands don't clobber the driver's exit code.
# shellcheck disable=SC2329  # invoked indirectly via `trap cleanup EXIT`
cleanup() {
    local rc=$?
    if [ -n "${SUDO_KEEPALIVE_PID:-}" ]; then
        kill "${SUDO_KEEPALIVE_PID}" 2>/dev/null || true
    fi
    print_summary
    exit "$rc"
}
trap cleanup EXIT
# Convert Ctrl-C / TERM into a normal exit so the single EXIT trap still reaps the sudo keep-alive
# loop and prints the summary/resume hint (bash does not run EXIT traps on an untrapped signal death).
trap 'exit 130' INT
trap 'exit 143' TERM

started=0
overall_rc=0
for i in ${STAGE_NAMES[@]+"${!STAGE_NAMES[@]}"}; do
    name="${STAGE_NAMES[$i]}"
    path="${STAGE_PATHS[$i]}"
    if [ -n "$ONLY" ]; then
        if [ "$name" != "$ONLY" ]; then
            continue
        fi
    elif [ -n "$FROM" ]; then
        if [ "$started" = 0 ] && [ "$name" != "$FROM" ]; then
            continue
        fi
        started=1
    fi
    log "=== stage: $name ==="
    stage_start=$SECONDS
    # Run the stage in its own subshell, capturing status without letting `set -e` abort the
    # driver, so a failing stage still lands in the summary before we stop.
    set +e
    BOOTSTRAP_DRY_RUN="${BOOTSTRAP_DRY_RUN:-0}" DOTFILES_REPO="$REPO" DOTFILES_LAYER="${path%/bootstrap/*}" \
        bash "$path"
    rc=$?
    set -e
    RESULT_NAMES+=("$name")
    RESULT_SECS+=("$((SECONDS - stage_start))")
    if [ "$rc" -eq 0 ]; then
        RESULT_STATUS+=("ok")
        record_stage "$name"
    else
        RESULT_STATUS+=("fail")
        FAILED_STAGE="$name"
        overall_rc="$rc"
        break
    fi
done

# All stages passed: clear the resume state so a later --resume reports "nothing to resume"
# rather than re-running the tail. Guarded to match record_stage (skip under dry-run/--only).
if [ "$overall_rc" -eq 0 ] && [ -z "$ONLY" ] && [ "${BOOTSTRAP_DRY_RUN:-0}" != "1" ]; then
    rm -f "$STATE_FILE"
fi

# Post-provision verification: run the doctor once all stages have succeeded.
if [ "$overall_rc" -eq 0 ] && [ "$VERIFY" = "1" ]; then
    log "=== verify: run.py doctor ==="
    if [ "${BOOTSTRAP_DRY_RUN:-0}" = "1" ]; then
        printf '\033[2m[dry-run]\033[0m scripts/hooks/uv-public.sh run python run.py doctor\n'
        VERIFY_STATUS="skipped"
    elif ! have uv; then
        # Standalone `bootstrap.sh --verify` (e.g. with --only/--from) may run before uv is installed.
        warn "uv not found — skipping verify (install uv, then re-run with --verify)"
        VERIFY_STATUS="skipped"
    elif (cd "$REPO" && "$REPO/scripts/hooks/uv-public.sh" run python run.py doctor); then
        VERIFY_STATUS="ok"
    else
        VERIFY_STATUS="fail"
        overall_rc=1
    fi
fi

exit "$overall_rc"
