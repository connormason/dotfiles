#!/usr/bin/env bash
# 00-preflight: verify the platform. macOS: ensure the Xcode Command Line Tools. Linux: require a Debian-family
# distribution and the system commands the engine cannot install itself (it never runs apt or sudo on Linux; the NAS
# `debian` Ansible role provides them).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

# /etc/os-release identifies the Linux distribution; DOTFILES_OS_RELEASE points elsewhere (tests)
OS_RELEASE="${DOTFILES_OS_RELEASE:-/etc/os-release}"

# Commands the Linux engine needs from the system: Homebrew's build prerequisites (build-essential, procps, curl, file,
# git) plus zsh for the stowed shell
LINUX_PREREQS=(curl file git cc make ps zsh)

preflight_darwin() {
    log "macOS $(sw_vers -productVersion) on $(uname -m)"

    # Xcode Command Line Tools
    if xcode-select -p >/dev/null 2>&1; then
        log "Xcode CLT already installed at $(xcode-select -p)"
    else
        log "installing Xcode Command Line Tools (a GUI dialog may appear)"
        run xcode-select --install || true
        warn "complete the CLT install dialog, then re-run: bootstrap.sh --from 00-preflight"
    fi
}

preflight_linux() {
    local id id_like pretty cmd missing="" msg
    [ -r "$OS_RELEASE" ] || die "cannot read $OS_RELEASE to identify the Linux distribution"
    # shellcheck source=/dev/null
    id="$(. "$OS_RELEASE" && printf '%s' "${ID:-}")"
    # shellcheck source=/dev/null
    id_like="$(. "$OS_RELEASE" && printf '%s' "${ID_LIKE:-}")"
    # shellcheck source=/dev/null
    pretty="$(. "$OS_RELEASE" && printf '%s' "${PRETTY_NAME:-Linux}")"
    case " $id $id_like " in
    *" debian "*) ;;
    *) die "unsupported Linux distribution '$id' (the engine supports Debian and its derivatives)" ;;
    esac
    log "$pretty on $(uname -m)"

    for cmd in "${LINUX_PREREQS[@]}"; do
        if ! have "$cmd"; then
            missing="$missing $cmd"
        fi
    done
    if [ -n "$missing" ]; then
        msg="missing system commands:$missing (install them with the NAS 'debian' Ansible role, or: sudo apt-get"
        msg="$msg install build-essential procps curl file git zsh)"
        if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
            warn "$msg"
        else
            die "$msg"
        fi
    fi
}

OS="$(dotfiles_os)"
case "$OS" in
darwin) preflight_darwin ;;
linux) preflight_linux ;;
esac

# On macOS, sudo is primed once by the driver (bootstrap.sh) and kept alive for the whole run.
log "preflight OK"
