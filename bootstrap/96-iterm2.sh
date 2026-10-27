#!/usr/bin/env bash
# 96-iterm2: point iTerm2 at the stow-managed custom prefs folder (runs after 95-dotfiles creates it).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

PREFS_DIR="$HOME/.config/iterm2"
if [ ! -d "$PREFS_DIR" ]; then
    warn "iTerm2 prefs dir $PREFS_DIR not found — 95-dotfiles (stow) should have created it"
fi

run defaults write com.googlecode.iterm2 PrefsCustomFolder -string "$PREFS_DIR"
run defaults write com.googlecode.iterm2 LoadPrefsFromCustomFolder -bool true
run defaults write com.googlecode.iterm2 PromptOnQuit -bool false
log "iterm2 OK (PrefsCustomFolder=$PREFS_DIR)"
