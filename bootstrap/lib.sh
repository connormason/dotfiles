#!/usr/bin/env bash
# Shared helpers for the bootstrap stage scripts. Source this; do not execute.
set -euo pipefail

# Dry-run flag: when 1, run() prints commands instead of executing them.
: "${BOOTSTRAP_DRY_RUN:=0}"

# Repo root (this file lives in <repo>/bootstrap/). Exported so overlay stages can source "$DOTFILES_REPO/bootstrap/lib.sh".
DOTFILES_REPO="${DOTFILES_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export DOTFILES_REPO

log() { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die() {
    printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2
    exit 1
}

# have NAME -> success if NAME is an executable on PATH
have() { command -v "$1" >/dev/null 2>&1; }

# fmt_duration SECONDS -> human-readable duration ("42s" under a minute, else "m:ss")
fmt_duration() {
    local s="${1:-0}"
    if [ "$s" -lt 60 ]; then
        printf '%ds' "$s"
    else
        printf '%d:%02d' "$((s / 60))" "$((s % 60))"
    fi
}

# run CMD... -> the single mutation chokepoint. Under dry-run, print only.
run() {
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        printf '\033[2m[dry-run]\033[0m %s\n' "$*"
        return 0
    fi
    "$@"
}

# try CMD... -> best-effort mutation: run CMD (honoring dry-run) but downgrade failure to a warning
# instead of aborting under `set -e`. Use for non-critical operations that may legitimately fail on
# some machines (e.g. cosmetic `defaults write` to a sandboxed app container whose directory does
# not exist until the app has been launched).
try() {
    run "$@" || warn "non-fatal: command failed: $*"
}

# prime_sudo -> prime sudo once and keep the credential alive for the rest of the run.
#
# Call this ONCE from the driver, never per-stage. The keep-alive loop ties its lifetime to the
# calling shell's PID ("$$"), so it must run in the long-lived driver process; each stage runs in
# its own subshell and would kill the loop on exit. Stage subshells share the driver's tty and so
# inherit the tty-cached sudo credential — they need not prime again. macOS caches the sudo
# timestamp per-tty with a ~5-minute timeout that long stages (e.g. brew installs) routinely
# outlast, so the background refresh is what prevents repeat password prompts mid-run.
#
# Exports SUDO_KEEPALIVE_PID so the driver can reap the loop on exit.
prime_sudo() {
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        log "would prime sudo"
        return 0
    fi

    sudo -v || die "sudo required"

    # keep-alive: refresh the timestamp every 60s until the driver process exits
    while true; do
        sudo -n true 2>/dev/null || exit
        sleep 60
        kill -0 "$$" 2>/dev/null || exit
    done &
    # shellcheck disable=SC2034  # read by the driver (bootstrap.sh) that sources this file
    SUDO_KEEPALIVE_PID=$!
}

# confirm PROMPT -> interactive yes/no, default no
confirm() {
    local reply
    read -r -p "$1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

# Append the first Homebrew prefix that has bin/brew to PATH. Appended (not prepended) so an active virtualenv's python
# is not shadowed. A layer's bootstrap/env.sh may set DOTFILES_BREW_PREFIXES (space-separated) to add prefixes.
ensure_brew_on_path() {
    local prefix
    for prefix in ${DOTFILES_BREW_PREFIXES:-/opt/homebrew /usr/local}; do
        if [ -x "$prefix/bin/brew" ]; then
            case ":$PATH:" in
            *":$prefix/bin:"*) ;;
            *) PATH="$PATH:$prefix/bin:$prefix/sbin" ;;
            esac
            export PATH
            return 0
        fi
    done
    return 0
}

# Path of the overlays registry (one overlay root per line; '#' comments and blank lines ignored).
dotfiles_overlays_file() {
    printf '%s\n' "${DOTFILES_OVERLAYS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles/overlays}"
}

# Print the repo root, then each registered overlay root (absolute), one per line. Dies on a missing overlay.
dotfiles_layers() {
    local registry line
    registry="$(dotfiles_overlays_file)"
    printf '%s\n' "$DOTFILES_REPO"
    if [ ! -f "$registry" ]; then
        return 0
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        if [ -z "$line" ]; then
            continue
        fi
        case "$line" in
        \~/*) line="$HOME/${line#\~/}" ;;
        esac
        if [ ! -d "$line" ]; then
            die "overlay not found: $line (listed in $registry)"
        fi
        (cd "$line" && pwd -P)
    done <"$registry"
}

# Print <layer>/bootstrap/NAME for every layer that provides it, base first.
manifest_files() {
    local layers layer
    layers="$(dotfiles_layers)" || return 1
    while IFS= read -r layer; do
        if [ -f "$layer/bootstrap/$1" ]; then
            printf '%s\n' "$layer/bootstrap/$1"
        fi
    done <<EOF
$layers
EOF
}

# Source every layer's bootstrap/env.sh (base first) so overlays can set variables base stages read.
_dotfiles_source_layer_env() {
    local layers layer
    layers="$(dotfiles_layers)" || exit 1
    while IFS= read -r layer; do
        if [ -f "$layer/bootstrap/env.sh" ]; then
            # shellcheck source=/dev/null
            source "$layer/bootstrap/env.sh"
        fi
    done <<EOF
$layers
EOF
}

# Make brew-installed tools available to every stage that sources this library.
_dotfiles_source_layer_env
ensure_brew_on_path
