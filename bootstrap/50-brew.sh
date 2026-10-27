#!/usr/bin/env bash
# 50-brew: ensure Homebrew, then apply every layer's Brewfile.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

BREW_INSTALLER_URL="https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
# SHA-256 of the installer at BREW_INSTALLER_URL; a mismatch aborts the install. Update when Homebrew changes it:
#   curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | shasum -a 256
# Last updated: 2026-01-11
BREW_INSTALLER_SHA256="b2ffbf7e7f451c6db3b5d1976fc6a9c2faecf58ee5e1dbf6e498643c91f0d3bc" # pragma: allowlist secret
BREW_INSTALLER=""

# shellcheck disable=SC2329  # invoked via the EXIT trap
cleanup_installer() {
    if [ -n "$BREW_INSTALLER" ]; then
        rm -f "$BREW_INSTALLER"
    fi
}

# install_homebrew -> download the official installer, verify its checksum, then run it.
install_homebrew() {
    local actual
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        run curl -fsSL "$BREW_INSTALLER_URL" -o '<temp file>'
        log "would verify the installer's SHA-256 is $BREW_INSTALLER_SHA256"
        run /bin/bash '<temp file>'
        return 0
    fi

    BREW_INSTALLER="$(mktemp "${TMPDIR:-/tmp}/brew-install.XXXXXX")"
    trap cleanup_installer EXIT
    run curl -fsSL "$BREW_INSTALLER_URL" -o "$BREW_INSTALLER"

    actual="$(shasum -a 256 "$BREW_INSTALLER" | awk '{print $1}')"
    if [ "$actual" != "$BREW_INSTALLER_SHA256" ]; then
        warn "Homebrew installer checksum mismatch"
        warn "  expected: $BREW_INSTALLER_SHA256"
        warn "  actual:   $actual"
        warn "either Homebrew updated its installer (normal) or the download was tampered with."
        warn "verify the new checksum at https://github.com/Homebrew/install and update BREW_INSTALLER_SHA256 in $0"
        die "Homebrew installer checksum mismatch; re-run after updating: bootstrap.sh --from 50-brew"
    fi
    log "installer checksum verified"

    run /bin/bash "$BREW_INSTALLER"
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

# Resolve the starship PATH collision: prefer the Homebrew copy over a legacy root install. The legacy copy is a regular
# file; on Intel Macs Homebrew's own copy is a symlink at the same path.
LEGACY_STARSHIP=/usr/local/bin/starship
if have brew && brew list starship >/dev/null 2>&1 && [ -f "$LEGACY_STARSHIP" ] && [ ! -L "$LEGACY_STARSHIP" ]; then
    warn "legacy root starship at $LEGACY_STARSHIP shadows the Homebrew copy"
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        run sudo rm -f "$LEGACY_STARSHIP"
    elif confirm "Remove $LEGACY_STARSHIP so Homebrew's copy is authoritative?"; then
        run sudo rm -f "$LEGACY_STARSHIP"
    fi
fi
log "brew OK"
