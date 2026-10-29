#!/usr/bin/env bash
# Settings Backup Hook (PreToolUse: Edit|Write|MultiEdit)
# Creates timestamped backups of critical config files before edits.

set -euo pipefail

# Resolve the target path (env var first; fall back to the hook's stdin JSON payload).
FILE_PATH="${TOOL_INPUT_FILE_PATH:-}"
if [[ -z "$FILE_PATH" ]]; then
    INPUT="$(cat 2>/dev/null || true)"
    if [[ -n "$INPUT" ]] && command -v jq >/dev/null 2>&1; then
        FILE_PATH="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)"
    fi
fi

# Only backup critical config files.
if [[ ! "$FILE_PATH" =~ (settings\.json|CLAUDE\.md|\.claude/.*\.md)$ ]]; then
    exit 0
fi

# Skip if the file doesn't exist yet (new file — nothing to back up).
[[ -f "$FILE_PATH" ]] || exit 0

BACKUP_DIR="$(dirname "$FILE_PATH")/.backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BASENAME=$(basename "$FILE_PATH")
BACKUP_PATH="$BACKUP_DIR/${BASENAME}.${TIMESTAMP}.bak"

cp "$FILE_PATH" "$BACKUP_PATH"

# Keep only the 10 most recent backups per file. Portable (no GNU-only -z flags):
# timestamped names sort chronologically, so reverse-sort keeps newest first.
find "$BACKUP_DIR" -maxdepth 1 -type f -name "${BASENAME}.*.bak" 2>/dev/null |
    sort -r |
    tail -n +11 |
    while IFS= read -r old; do
        rm -f "$old"
    done || true

exit 0
