#!/usr/bin/env bash
#
# 98-nas-music: auto-mount the NAS media share on the personal MacBook (for Serato).
#
# Runs after 95-dotfiles, which links the `nas-music` package: the nas-music-mount script and its LaunchAgent plist.
# This stage supplies what the repo cannot hold:
#   1. ~/.config/nas-music/mount.conf (host, share, user), prompted for unless already present or given through the
#      NAS_MUSIC_HOST / NAS_MUSIC_SHARE / NAS_MUSIC_USER environment variables
#   2. the share password in the login Keychain, typed into `security`'s own prompt (never argv, never the repo)
#   3. the LaunchAgent, (re)loaded into the user's GUI domain and started once
# Re-running is safe: existing config and Keychain entries are kept, and the agent is booted out before it is loaded.
set -euo pipefail

# shellcheck source=/dev/null
source "$DOTFILES_REPO/bootstrap/lib.sh"
require_os darwin

LABEL="com.connormason.nas-music-mount"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/nas-music"
CONF="$CONF_DIR/mount.conf"
SCRIPT="$HOME/.local/bin/nas-music-mount"

# Settings, highest precedence first: the config file, the NAS_MUSIC_* environment variables, then these defaults
if [ -f "$CONF" ]; then
    # shellcheck source=/dev/null
    source "$CONF"
fi
host="${NAS_MUSIC_HOST:-nas.local}"
share="${NAS_MUSIC_SHARE:-media}"
user="${NAS_MUSIC_USER:-}"

# ask VAR PROMPT -> set VAR from a prompt that offers its current value as the default
ask() {
    local var="$1" prompt="$2" current reply
    current="${!var}"
    read -r -p "$prompt${current:+ [$current]}: " reply
    printf -v "$var" '%s' "${reply:-$current}"
}

# --- 1. config --------------------------------------------------------------------------------------------------
if [ ! -f "$CONF" ]; then
    if [ -z "$user" ]; then
        if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
            log "would prompt for the NAS host, share, and user, then write $CONF"
            exit 0
        elif is_interactive; then
            ask host "NAS hostname"
            ask share "SMB share name"
            ask user "NAS user"
        else
            warn "non-interactive run and no NAS_MUSIC_USER set: skipping the NAS music mount"
            exit 0
        fi
    fi
    if [ -z "$user" ]; then
        die "a NAS user is required"
    fi

    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        printf '\033[2m[dry-run]\033[0m write %s (host=%s share=%s user=%s)\n' "$CONF" "$host" "$share" "$user"
    else
        mkdir -p "$CONF_DIR"
        {
            printf '# Written by bootstrap stage 98-nas-music; read by nas-music-mount. Safe to edit.\n'
            printf 'NAS_MUSIC_HOST=%q\n' "$host"
            printf 'NAS_MUSIC_SHARE=%q\n' "$share"
            printf 'NAS_MUSIC_USER=%q\n' "$user"
        } >"$CONF"
    fi
    note_change "nas-music: wrote $CONF"
fi

if [ -z "$user" ]; then
    die "$CONF does not set NAS_MUSIC_USER"
fi

# --- 2. Keychain password ---------------------------------------------------------------------------------------
if security find-internet-password -s "$host" -a "$user" -r 'smb ' >/dev/null 2>&1; then
    log "Keychain already holds a password for $user@$host"
elif [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
    printf '\033[2m[dry-run]\033[0m would offer to store the %s@%s password in the login Keychain\n' "$user" "$host"
elif confirm "Store the NAS password for $user@$host in the login Keychain now?"; then
    # -w last with no value makes `security` prompt for the password itself. The first mount may show a one-time
    # Keychain access dialog; choose "Always Allow".
    security add-internet-password -s "$host" -a "$user" -r 'smb ' -l "NAS music ($host)" -U -w
    note_change "nas-music: stored the Keychain password for $user@$host"
else
    warn "no Keychain password stored: nas-music-mount stays idle until you re-run this stage or mount once from Finder (Cmd+K, tick 'Remember this password in my keychain')"
fi

# --- 3. LaunchAgent ---------------------------------------------------------------------------------------------
if [ ! -f "$PLIST" ] || [ ! -x "$SCRIPT" ]; then
    if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
        log "the nas-music package is not linked yet (95-dotfiles links it); skipping the launchctl preview"
        exit 0
    fi
    die "nas-music is not linked ($PLIST / $SCRIPT missing): run bootstrap/bootstrap.sh --only 95-dotfiles first"
fi

domain="gui/$(id -u)"
# bootout fails when the agent is not loaded yet, which is the normal first-run state
run launchctl bootout "$domain/$LABEL" 2>/dev/null || true
run launchctl bootstrap "$domain" "$PLIST"
try launchctl kickstart "$domain/$LABEL"
note_change "nas-music: loaded LaunchAgent $LABEL"

log "nas-music OK ($user@$host/$share -> /Volumes/$share; status: nas-music-mount --status)"
