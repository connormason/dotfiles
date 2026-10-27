#!/usr/bin/env bash
# 90-python: install the uv tools declared in every layer's uv-tools.txt.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

# uv and hatch come from the Brewfile (stage 50-brew). Verify only.
if have uv; then
    log "uv present: $(uv --version)"
else
    warn "uv not found — ensure stage 50-brew ran (uv is in the Brewfile); skipping uv tools"
    log "python OK"
    exit 0
fi
if have hatch; then
    log "hatch present: $(hatch --version 2>/dev/null || echo unknown)"
else
    warn "hatch not found — ensure stage 50-brew ran (hatch is in the Brewfile)"
fi

# Merge every layer's uv-tools.txt (base first). Format: the package name, optionally followed by `uv tool install`
# flags; `#` starts a comment. A later layer's line for a tool replaces the earlier one in place, so an overlay can
# add flags to a base tool. TOOL_NAMES/TOOL_ARGS are parallel arrays (bash 3.2 has no associative arrays).
TOOL_NAMES=()
TOOL_ARGS=()
set -f # lines are word-split below; never glob-expand them (e.g. `--with pkg[extra]`)
manifests="$(manifest_files uv-tools.txt)" || die "cannot enumerate uv-tools.txt manifests"
while IFS= read -r manifest; do
    if [ -z "$manifest" ]; then
        continue
    fi
    while IFS= read -r raw || [ -n "$raw" ]; do
        raw="${raw%%#*}" # strip comments (inline and full-line)
        # shellcheck disable=SC2086
        set -- $raw # word-split: trims/collapses whitespace, drops blank lines
        if [ "$#" -eq 0 ]; then
            continue
        fi
        slot=${#TOOL_NAMES[@]}
        for i in ${TOOL_NAMES[@]+"${!TOOL_NAMES[@]}"}; do
            if [ "${TOOL_NAMES[$i]}" = "$1" ]; then
                slot=$i
                break
            fi
        done
        TOOL_NAMES[slot]="$1"
        TOOL_ARGS[slot]="$*"
    done <"$manifest"
done <<EOF
$manifests
EOF

# Install whatever is missing. Idempotent: tools already present are skipped (re-resolving dozens of tools every run
# is slow), so a changed line takes effect only after `uv tool install --force …` or `uv tool upgrade` by hand.
installed="$(uv tool list 2>/dev/null | grep -v '^-' | awk '{print $1}' || true)"
for i in ${TOOL_NAMES[@]+"${!TOOL_NAMES[@]}"}; do
    tool="${TOOL_NAMES[$i]}"
    if printf '%s\n' "$installed" | grep -qxF -- "$tool"; then
        log "uv tool present: $tool"
    else
        log "installing uv tool: ${TOOL_ARGS[$i]}"
        # shellcheck disable=SC2086
        run uv tool install ${TOOL_ARGS[$i]}
    fi
done
log "python OK"
