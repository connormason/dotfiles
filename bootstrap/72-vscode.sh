#!/usr/bin/env bash
# 72-vscode: install the VS Code extensions declared in every layer's manifest.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"
require_os darwin

# VS Code provides the `code` CLI via the visual-studio-code cask (stage 50-brew). Skip cleanly if it
# is absent — not every machine profile installs VS Code, and a missing editor must not fail bootstrap.
if ! have code; then
    warn "code CLI not found — skipping VS Code extensions (ensure stage 50-brew installed visual-studio-code)"
    log "vscode OK"
    exit 0
fi

# Collect the union of every layer's vscode-extensions.txt (base first), de-duplicated case-insensitively. Format: one
# `publisher.name` extension ID per line; `#` starts a comment. Refresh the base manifest from this machine with
# `code --list-extensions`.
manifests="$(manifest_files vscode-extensions.txt)" || die "cannot enumerate VS Code extension manifests"
wanted=""
while IFS= read -r manifest; do
    if [ -z "$manifest" ]; then
        continue
    fi
    while IFS= read -r raw || [ -n "$raw" ]; do
        raw="${raw%%#*}" # strip comments (inline and full-line)
        ext="$(printf '%s' "$raw" | tr -d '[:space:]')"
        if [ -z "$ext" ]; then
            continue
        fi
        if ! printf '%s' "$wanted" | grep -qixF -- "$ext"; then
            wanted="$wanted$ext"$'\n'
        fi
    done <"$manifest"
done <<EOF
$manifests
EOF

# Install whatever is missing. Idempotent: extensions already installed are skipped (re-resolving dozens of extensions
# every run is slow). `code --list-extensions` emits canonical casing; match case-insensitively to be safe.
installed="$(code --list-extensions 2>/dev/null || true)"
while IFS= read -r ext <&3; do
    if [ -z "$ext" ]; then
        continue
    fi
    if printf '%s\n' "$installed" | grep -qixF -- "$ext"; then
        log "vscode extension present: $ext"
    else
        log "installing vscode extension: $ext"
        run code --install-extension "$ext"
    fi
done 3<<EOF
$wanted
EOF
log "vscode OK"
