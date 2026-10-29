#!/usr/bin/env bash
# Secret Scanner Hook (PreToolUse: Edit|Write|MultiEdit)
# Blocks writing sensitive data into files. Scans the *pending* content — what the
# tool is about to write (Write .content / Edit .new_string / MultiEdit .edits[].new_string)
# — NOT the on-disk file, so it catches secrets before they land.

set -euo pipefail

# Hook payload arrives as JSON on stdin.
INPUT="$(cat 2>/dev/null || true)"
[[ -z "$INPUT" ]] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

FILE_PATH="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)"

# Collect every string this call would write.
CONTENT="$(printf '%s' "$INPUT" | jq -r '
    [ (.tool_input.content // empty),
      (.tool_input.new_string // empty),
      ((.tool_input.edits // []) | .[]?.new_string // empty)
    ] | join("\n")
' 2>/dev/null || true)"

[[ -z "$CONTENT" ]] && exit 0

# High-signal credential formats only — kept tight because this now hard-blocks writes.
declare -a PATTERNS=(
    "AKIA[0-9A-Z]{16}"             # AWS Access Key ID
    "AIza[0-9A-Za-z_-]{35}"        # Google API Key
    "sk-[A-Za-z0-9]{48}"           # OpenAI API Key
    "xox[baprs]-[0-9A-Za-z-]+"     # Slack Token
    "ghp_[A-Za-z0-9]{36}"          # GitHub Personal Access Token
    "-----BEGIN.*PRIVATE KEY-----" # PEM private key
)

FOUND_SECRETS=false

for pattern in "${PATTERNS[@]}"; do
    if printf '%s' "$CONTENT" | grep -qE "$pattern" 2>/dev/null; then
        if [[ "$FOUND_SECRETS" == "false" ]]; then
            echo "⚠️  SECURITY WARNING: potential secret in pending write to ${FILE_PATH:-<unknown file>}" >&2
            echo "" >&2
            FOUND_SECRETS=true
        fi
        echo "  Pattern matched: ${pattern:0:30}..." >&2
    fi
done

if [[ "$FOUND_SECRETS" == "true" ]]; then
    echo "" >&2
    echo "Remove the sensitive data before writing. If this is a false positive, make the edit manually." >&2
    exit 2
fi

exit 0
