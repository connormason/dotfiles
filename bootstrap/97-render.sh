#!/usr/bin/env bash
# 97-render: render JSON settings files (VS Code, Claude Code, ...) from every layer's render/ fragments.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

RENDER="$REPO/scripts/dotfiles/render.py"
if ! have python3; then
    case "$(dotfiles_os)" in
    darwin) die "python3 required to render settings (install the Xcode Command Line Tools)" ;;
    *) die "python3 required to render settings (install it via the system packages or the NAS 'debian' Ansible role)" ;;
    esac
fi

# Dry run: `render.py --check` writes nothing; report drift (exit 1) or errors (exit 2) without failing the stage.
if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
    rc=0
    python3 "$RENDER" --check || rc=$?
    case "$rc" in
    0) log "rendered settings already in sync" ;;
    1) warn "rendered settings out of sync; a real run renders them (preview with: run.py render --diff)" ;;
    *) warn "render --check failed (exit $rc): a real run would fail this stage" ;;
    esac
    log "render OK"
    exit 0
fi

# render.py exit codes: 0 ok, 1 drift refused (an in-app edit since the last render), 2 bad fragment/registry or I/O.
rc=0
run python3 "$RENDER" || rc=$?
case "$rc" in
0) log "render OK" ;;
1)
    warn "render refused to overwrite in-app edits; inspect with: run.py render --diff"
    warn "then move the change into a render fragment, or overwrite it (backing it up) with: run.py render --force"
    ;;
*) die "render failed (exit $rc): fix the fragment or overlays registry it reports, then re-run --from 97-render" ;;
esac
