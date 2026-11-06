#!/usr/bin/env bash
# PostToolUse lint: ruff auto-fix for edited Python files, yamllint for edited YAML files.
#
# Claude Code delivers tool data as JSON on stdin (tool_input.file_path); it exports no per-argument environment
# variable. The repo root is derived from the edited file so the hook also works inside git worktrees. Everything runs
# through scripts/hooks/uv-public.sh so a work-machine package index never leaks into uv.lock. `ruff format` is
# deliberately never run: this repo does not use the formatter.
#
# Exit 0 is silent. A yamllint failure exits 2 so its output reaches Claude (PostToolUse cannot block; it can only report).
set -euo pipefail

command -v jq >/dev/null 2>&1 || exit 0

file_path="$(jq -r '.tool_input.file_path // empty')"
[[ -n "$file_path" && -f "$file_path" ]] || exit 0

case "$file_path" in
*.py | *.yml | *.yaml) ;;
*) exit 0 ;;
esac

repo_root="$(cd "$(dirname "$file_path")" && git rev-parse --show-toplevel 2>/dev/null)" || exit 0
uv_public="$repo_root/scripts/hooks/uv-public.sh"
[[ -x "$uv_public" ]] || exit 0

cd "$repo_root"

case "$file_path" in
*.py)
    "$uv_public" run ruff check --fix-only --quiet "$file_path" >/dev/null 2>&1 || true
    ;;
*.yml | *.yaml)
    if ! output="$("$uv_public" run yamllint "$file_path" 2>&1)"; then
        printf 'yamllint reported problems in %s:\n%s\n' "$file_path" "$output" >&2
        exit 2
    fi
    ;;
esac
