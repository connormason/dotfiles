#!/usr/bin/env bash
# PreToolUse guard: refuse edits to the Ansible vault password and the inventory clone.
#
# Claude Code delivers tool data as JSON on stdin (tool_input.file_path); it exports no per-argument environment
# variable. Exit status 2 blocks the tool call and shows stderr to Claude.
set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
    echo 'BLOCKED: jq is required by the file-protection hook (.claude/hooks/block-protected-files.sh) and is missing' >&2
    exit 2
fi

file_path="$(jq -r '.tool_input.file_path // empty')"
[[ -n "$file_path" ]] || exit 0

if [[ "$file_path" =~ (^|/)vault_password[^/]*$ || "$file_path" =~ (^|/)inventory/ ]]; then
    echo 'BLOCKED: Cannot edit vault password or inventory files — these are sensitive and managed separately' >&2
    exit 2
fi
