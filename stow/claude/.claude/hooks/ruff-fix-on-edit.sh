#!/usr/bin/env bash
# Ruff Auto-Fix on Edit Hook
# After Claude edits a .py file, apply ruff's safe lint fixes in place and surface any
# remaining (unfixable) violations back to Claude.
#
# Runs `ruff check --fix` ONLY — never `ruff format` (this setup does not use ruff's formatter).
# No-ops outside ruff-configured projects, or when neither uv nor ruff is available.

set -euo pipefail

# Resolve the edited file path (env var first; fall back to the hook's stdin JSON payload)
FILE_PATH="${TOOL_INPUT_FILE_PATH:-}"
if [[ -z "$FILE_PATH" ]]; then
    INPUT="$(cat 2>/dev/null || true)"
    if [[ -n "$INPUT" ]]; then
        FILE_PATH="$(printf '%s' "$INPUT" |
            python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' \
                2>/dev/null || true)"
    fi
fi

# Only operate on existing .py files
[[ "$FILE_PATH" == *.py ]] || exit 0
[[ -f "$FILE_PATH" ]] || exit 0

# Find the nearest ancestor that configures ruff; bail if this is not a ruff project
find_ruff_root() {
    local dir
    dir="$(cd "$(dirname "$FILE_PATH")" && pwd)"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/ruff.toml" || -f "$dir/.ruff.toml" ]]; then
            printf '%s\n' "$dir"
            return 0
        fi
        if [[ -f "$dir/pyproject.toml" ]] && grep -q '\[tool\.ruff' "$dir/pyproject.toml" 2>/dev/null; then
            printf '%s\n' "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    return 1
}

ROOT="$(find_ruff_root)" || exit 0

# Resolve a ruff invocation. Prefer the project's pinned ruff via `uv run` (matches the commit-time
# ruff version); fall back to a ruff on PATH. No-op if neither is available.
if command -v uv >/dev/null 2>&1 && [[ -f "$ROOT/pyproject.toml" || -f "$ROOT/uv.lock" ]]; then
    RUFF=(uv run --quiet --project "$ROOT" ruff)
elif command -v ruff >/dev/null 2>&1; then
    RUFF=(ruff)
else
    exit 0
fi

# Apply safe fixes in place (never `ruff format`)
"${RUFF[@]}" check --fix --quiet "$FILE_PATH" >/dev/null 2>&1 || true

# Surface any remaining (unfixable) violations so Claude can address them
REMAINING="$("${RUFF[@]}" check --quiet "$FILE_PATH" 2>/dev/null || true)"
if [[ -n "$REMAINING" ]]; then
    echo "ruff: remaining violations in $FILE_PATH (safe auto-fixes already applied):" >&2
    echo "$REMAINING" >&2
    exit 2
fi

exit 0
