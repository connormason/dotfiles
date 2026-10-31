#!/usr/bin/env bash
# 50-brew: ensure Homebrew, then apply every layer's Brewfile.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

OS="$(dotfiles_os)"

# Homebrew's Linux prefix. The engine never uses sudo on Linux, so the prefix must already exist and be writable by the
# user (the NAS `debian` Ansible role creates it); the installer then needs no root. DOTFILES_LINUXBREW_PREFIX moves
# this check for tests only: the installer itself always targets the default prefix.
LINUXBREW_PREFIX="${DOTFILES_LINUXBREW_PREFIX:-/home/linuxbrew/.linuxbrew}"

# Pinned to an upstream commit so the content cannot drift when Homebrew edits install.sh on HEAD.
BREW_INSTALLER_URL="https://raw.githubusercontent.com/Homebrew/install/09c62fc577ec170172b0a184060f141a2c622dc1/install.sh"

# SHA-256 of the installer at BREW_INSTALLER_URL; a mismatch aborts the install. To update: pick a commit SHA from the
# upstream history of install.sh (https://github.com/Homebrew/install/commits/HEAD/install.sh), put it in the URL above,
# then take the SHA-256 of that exact URL:
#   curl -fsSL <BREW_INSTALLER_URL> | shasum -a 256
# Last updated: 2026-10-30
BREW_INSTALLER_SHA256="5f333bbe53bc490e51e7ccb1df8779b3dd6ee73a1a7379efda216edb08ccb148" # pragma: allowlist secret
BREW_INSTALLER=""

# shellcheck disable=SC2329  # invoked via the EXIT trap
cleanup_installer() {
    if [ -n "$BREW_INSTALLER" ]; then
        rm -f "$BREW_INSTALLER"
    fi
}

# install_homebrew -> download the official installer, verify its checksum, then run it.
install_homebrew() {
    local actual msg installer_env=()
    if [ "$OS" = "linux" ]; then
        if [ ! -d "$LINUXBREW_PREFIX" ] || [ ! -w "$LINUXBREW_PREFIX" ]; then
            msg="$LINUXBREW_PREFIX must exist and be writable by $(id -un) so Homebrew installs without sudo"
            msg="$msg (the NAS 'debian' Ansible role creates it)"
            if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
                warn "$msg"
            else
                die "$msg"
            fi
        fi
        # The installer's confirmation prompt would block an unattended run (Ansible)
        installer_env=(env NONINTERACTIVE=1)
    fi

    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        run curl -fsSL "$BREW_INSTALLER_URL" -o '<temp file>'
        log "would verify the installer's SHA-256 is $BREW_INSTALLER_SHA256"
        run ${installer_env[@]+"${installer_env[@]}"} /bin/bash '<temp file>'
        return 0
    fi

    BREW_INSTALLER="$(mktemp "${TMPDIR:-/tmp}/brew-install.XXXXXX")"
    trap cleanup_installer EXIT
    run curl -fsSL "$BREW_INSTALLER_URL" -o "$BREW_INSTALLER"

    actual="$(sha256_of "$BREW_INSTALLER")"
    if [ "$actual" != "$BREW_INSTALLER_SHA256" ]; then
        warn "Homebrew installer checksum mismatch"
        warn "  expected: $BREW_INSTALLER_SHA256"
        warn "  actual:   $actual"
        warn "the URL is pinned to an upstream commit: treat this as a bad or tampered download, not a Homebrew update"
        warn "retry first; re-pin $0 and nas_bootstrap.sh together only to adopt a newer upstream commit (README.md)"
        die "Homebrew installer checksum mismatch; retry with: bootstrap.sh --from 50-brew"
    fi
    log "installer checksum verified"

    run ${installer_env[@]+"${installer_env[@]}"} /bin/bash "$BREW_INSTALLER"
}

if have brew; then
    log "brew present: $(command -v brew)"
else
    log "installing Homebrew"
    install_homebrew
    ensure_brew_on_path
    if [ "${BOOTSTRAP_DRY_RUN}" != "1" ] && ! have brew; then
        die "Homebrew installed, but brew is not in any known prefix"
    fi
fi

# Apply each layer's Brewfile, base first. Then verify it: Homebrew has no lockfile (`brew bundle` lost its `lock`
# subcommand), so `brew bundle check` is the reproducibility signal. It flags drift between a Brewfile and what is
# installed, and is non-fatal: a benign mismatch must not abort provisioning.
brewfiles="$(manifest_files Brewfile)" || die "cannot enumerate Brewfiles (check the overlays registry)"
while IFS= read -r brewfile <&3; do
    if [ -z "$brewfile" ]; then
        continue
    fi
    log "applying $brewfile"
    run brew bundle --file "$brewfile"
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        run brew bundle check --file "$brewfile"
    elif brew bundle check --file "$brewfile"; then
        log "Brewfile satisfied: $brewfile"
    else
        warn "Brewfile drift: $brewfile has dependencies missing or out of date (see 'brew bundle check' above)"
    fi
done 3<<EOF
$brewfiles
EOF

# macOS only: resolve the starship PATH collision: prefer the Homebrew copy over a legacy root install. The legacy copy
# is a regular file; on Intel Macs Homebrew's own copy is a symlink at the same path.
LEGACY_STARSHIP=/usr/local/bin/starship
if [ "$OS" = "darwin" ] && have brew && brew list starship >/dev/null 2>&1 && [ -f "$LEGACY_STARSHIP" ] && [ ! -L "$LEGACY_STARSHIP" ]; then
    warn "legacy root starship at $LEGACY_STARSHIP shadows the Homebrew copy"
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        run sudo rm -f "$LEGACY_STARSHIP"
    elif confirm "Remove $LEGACY_STARSHIP so Homebrew's copy is authoritative?"; then
        run sudo rm -f "$LEGACY_STARSHIP"
    fi
fi
log "brew OK"
