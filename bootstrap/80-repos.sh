#!/usr/bin/env bash
# 80-repos: clone the repositories declared in every layer's repos.txt under $HOME (clone-if-absent).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

# Each non-comment line is `name url`, separated by any run of spaces or tabs. Existing paths are never touched.
manifests="$(manifest_files repos.txt)" || die "cannot enumerate repos.txt manifests"
while IFS= read -r manifest <&4; do
    if [ -z "$manifest" ]; then
        continue
    fi
    lineno=0
    while IFS= read -r raw <&3 || [ -n "$raw" ]; do
        lineno=$((lineno + 1))
        raw="${raw%%#*}" # strip comments (inline and full-line)
        name="" url="" extra=""
        read -r name url extra <<<"$raw" || true
        if [ -z "$name" ]; then
            continue
        fi
        if [ -z "$url" ] || [ -n "$extra" ]; then
            die "$manifest:$lineno: expected 'name url', got: $raw"
        fi
        case "$name" in
        */* | . | ..) die "$manifest:$lineno: repo name must be a single path component: $name" ;;
        esac

        dest="$HOME/$name"
        if [ -d "$dest/.git" ]; then
            log "repo already cloned: $name"
        elif [ -e "$dest" ]; then
            warn "$dest exists but is not a git clone; leaving it alone"
        else
            log "cloning $name"
            run git clone "$url" "$dest"
        fi
    done 3<"$manifest"
done 4<<EOF
$manifests
EOF
log "repos OK"
