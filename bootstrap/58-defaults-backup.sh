#!/usr/bin/env bash
#
# 58-defaults-backup: snapshot the preference domains that 60-macos and 96-iterm2 are about to write.
#
# Each run writes <backup root>/defaults-<YYYYmmdd-HHMMSS>/ holding one plist per domain in defaults-domains.txt plus a
# MANIFEST.tsv (`domain<TAB>file<TAB>present|absent`). `defaults export` succeeds on a missing domain and writes an empty
# plist, so presence is decided with `defaults read`; absent domains are recorded so restore deletes them instead of
# importing nothing. Undo with bootstrap/defaults-restore.sh.
#
# DEFAULTS_BACKUP_DIR overrides the backup root (default: ~/.dotfiles-backup).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"
require_os darwin

ROOT="${DEFAULTS_BACKUP_DIR:-$HOME/.dotfiles-backup}"
SNAPSHOT="$ROOT/defaults-$(date +%Y%m%d-%H%M%S)"

# plist_name DOMAIN -> file name for DOMAIN's plist ("/" is not allowed in a file name)
plist_name() {
    local name="${1//\//_}"
    printf '%s.plist\n' "${name#_}"
}

run mkdir -p "$SNAPSHOT"
manifest="$SNAPSHOT/MANIFEST.tsv"

count=0
while IFS= read -r domain; do
    domain="${domain%%#*}"
    domain="$(printf '%s' "$domain" | tr -d '[:space:]')"
    if [ -z "$domain" ]; then
        continue
    fi

    file="$(plist_name "$domain")"
    if defaults read "$domain" >/dev/null 2>&1; then
        state=present
        run defaults export "$domain" "$SNAPSHOT/$file"
    else
        state=absent
        warn "$domain is absent or unreadable (e.g. a sandbox container behind Full Disk Access); restore will delete it"
    fi

    if [ "${BOOTSTRAP_DRY_RUN}" != "1" ]; then
        printf '%s\t%s\t%s\n' "$domain" "$file" "$state" >>"$manifest"
    fi
    count=$((count + 1))
done <"$HERE/defaults-domains.txt"

log "defaults backup OK ($count domains -> $SNAPSHOT; restore with bootstrap/defaults-restore.sh)"
