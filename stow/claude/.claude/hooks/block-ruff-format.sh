#!/usr/bin/env bash
# PreToolUse(Bash) guard: block any command that invokes `ruff format`.
#
# The user never wants ruff's formatter run on any project — it strips manual column alignment and
# adds blank lines after class docstrings, neither of which is wanted. `ruff check --fix` is fine and
# encouraged; only the formatter is banned. Catches bare `ruff format` and `uv run ruff format`, with
# any whitespace, while leaving `ruff format`-lookalikes (e.g. `ruff formatter`) and `ruff check` alone.
#
# Reads the PreToolUse hook payload on stdin; emits a deny decision (exit 0) on match, nothing otherwise.
set -euo pipefail

cmd="$(jq -r '.tool_input.command // ""')"

if printf '%s' "$cmd" | grep -Eq 'ruff[[:space:]]+format([^a-zA-Z]|$)'; then
    cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"`ruff format` is banned on this user's projects — it strips manual column alignment and adds blank lines after class docstrings, which the user does not want. Use `ruff check --fix` instead, and match the surrounding hand-maintained style."}}
JSON
fi
