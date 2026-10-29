#!/usr/bin/env bash
# Shell Lint on Edit Hook
# After Claude edits a shell script, auto-format with shfmt (matching the repo's commit-time shfmt
# hook) and surface shellcheck diagnostics back to Claude.
#
# No-ops when the file is not an sh/bash script or when the relevant tools are unavailable.
# zsh files are skipped: shfmt and shellcheck do not support the zsh dialect.

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

[[ -n "$FILE_PATH" ]] || exit 0
[[ -f "$FILE_PATH" ]] || exit 0

# Classify the file: only sh/bash scripts are handled (by extension, or by shebang when extensionless)
case "$FILE_PATH" in
*.zsh) exit 0 ;;  # shfmt/shellcheck don't support zsh
*.sh | *.bash) ;; # definitely shell
*)
    FIRST_LINE="$(head -n 1 "$FILE_PATH" 2>/dev/null || true)"
    case "$FIRST_LINE" in
    \#\!*bash* | \#\!*dash* | \#\!*/sh | \#\!*\ sh) ;;
    *) exit 0 ;;
    esac
    ;;
esac

# shfmt: auto-format in place (mirrors the commit-time shfmt hook)
if command -v shfmt >/dev/null 2>&1; then
    shfmt -w "$FILE_PATH" >/dev/null 2>&1 || true
fi

# Run shellcheck and surface diagnostics back to Claude (advisory; cannot auto-fix)
if command -v shellcheck >/dev/null 2>&1; then
    if ! OUT="$(shellcheck -x "$FILE_PATH" 2>&1)"; then
        echo "shellcheck found issues in $FILE_PATH (shfmt formatting already applied):" >&2
        echo "$OUT" >&2
        exit 2
    fi
fi

exit 0
