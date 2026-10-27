#!/usr/bin/env bash
# 00-preflight: verify macOS, ensure Xcode Command Line Tools.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

[ "$(uname -s)" = "Darwin" ] || die "this bootstrap targets macOS only"
log "macOS $(sw_vers -productVersion) on $(uname -m)"

# Xcode Command Line Tools
if xcode-select -p >/dev/null 2>&1; then
    log "Xcode CLT already installed at $(xcode-select -p)"
else
    log "installing Xcode Command Line Tools (a GUI dialog may appear)"
    run xcode-select --install || true
    warn "complete the CLT install dialog, then re-run: bootstrap.sh --from 00-preflight"
fi

# sudo is primed once by the driver (bootstrap.sh) and kept alive for the whole run.
log "preflight OK"
