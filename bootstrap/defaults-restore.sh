#!/usr/bin/env bash
#
# defaults-restore: put back the preference domains saved by 58-defaults-backup.
#
# Usage: defaults-restore.sh [-n|--dry-run] [--list] [SNAPSHOT_DIR]
#
# SNAPSHOT_DIR defaults to the oldest snapshot under the backup root, the state before the first bootstrap run. `defaults
# import` replaces a whole domain, so changes made to these domains after the snapshot are lost too. Domains recorded as
# absent are deleted. Run it from a terminal that has Full Disk Access if com.apple.mail matters, and quit iTerm2 first
# (it rewrites its own preferences on exit).
#
# DEFAULTS_BACKUP_DIR overrides the backup root (default: ~/.dotfiles-backup).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"
require_os darwin

ROOT="${DEFAULTS_BACKUP_DIR:-$HOME/.dotfiles-backup}"
list_only=0
snapshot=""

while [ $# -gt 0 ]; do
    # shellcheck disable=SC2034  # BOOTSTRAP_DRY_RUN is read by run() in lib.sh
    case "$1" in
    -n | --dry-run) BOOTSTRAP_DRY_RUN=1 ;;
    --list) list_only=1 ;;
    -h | --help)
        sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    -*) die "unknown option: $1" ;;
    *) snapshot="$1" ;;
    esac
    shift
done

# Snapshot names embed a sortable timestamp, so a glob lists them oldest first.
snapshots=()
for dir in "$ROOT"/defaults-*/; do
    if [ -f "${dir}MANIFEST.tsv" ]; then
        snapshots+=("${dir%/}")
    fi
done

if [ "$list_only" = 1 ]; then
    if [ "${#snapshots[@]}" -eq 0 ]; then
        log "no snapshots under $ROOT"
    else
        printf '%s\n' "${snapshots[@]}"
    fi
    exit 0
fi

if [ -z "$snapshot" ]; then
    if [ "${#snapshots[@]}" -eq 0 ]; then
        die "no snapshots under $ROOT (run bootstrap stage 58-defaults-backup first)"
    fi
    snapshot="${snapshots[0]}"
fi
if [ ! -f "$snapshot/MANIFEST.tsv" ]; then
    die "$snapshot has no MANIFEST.tsv"
fi

log "restoring preferences from $snapshot"
while IFS=$'\t' read -r domain file state; do
    # Domains under /Library are root-owned file domains: 60-macos wrote them with sudo, so restore does too.
    prefix=()
    if [ "${domain#/}" != "$domain" ]; then
        prefix=(sudo)
    fi

    case "$state" in
    # ${prefix[@]+...}: macOS bash 3.2 treats an empty array as unset under `set -u`.
    present) try ${prefix[@]+"${prefix[@]}"} defaults import "$domain" "$snapshot/$file" ;;
    absent) try ${prefix[@]+"${prefix[@]}"} defaults delete "$domain" ;;
    *) warn "skipping $domain: unknown state '$state'" ;;
    esac
done <"$snapshot/MANIFEST.tsv"

# cfprefsd serves cached values; restart the processes whose preferences changed.
run killall Dock || true
run killall Finder || true
run killall SystemUIServer || true

log "defaults restore OK (from $snapshot)"
