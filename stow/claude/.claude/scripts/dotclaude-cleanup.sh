#!/usr/bin/env bash
# dotclaude-cleanup.sh — Reclaim disk space in ~/.claude by purging stale artifacts
#
# Cleans:
#   - todos/ empty files         (2-byte [] stubs from subagents)
#   - session-env/ empty dirs    (empty session directories)
#   - debug/ files older than N days
#   - backups/ files (keeps the most recent N)
#   - shell-snapshots/ older than N days
#   - file-history/ older than N days
#   - whatever drop-in extensions in ~/.claude/scripts/dotclaude-cleanup.d/*.sh add (each is sourced into this
#     shell and may call `section` and `delete_files`, and read CLAUDE_DIR / DRY_RUN / KEEP_DAYS / KEEP_BACKUPS)
#
# Usage: dotclaude-cleanup.sh [--dry-run] [--keep-days N] [--keep-backups N]

# No `-e`: cleanup is best-effort, so one failed removal or measurement must not abort the remaining sections
set -uo pipefail

CLAUDE_DIR="${HOME}/.claude"
DRY_RUN=false
KEEP_DAYS=7
KEEP_BACKUPS=5

# --- argument parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
    --dry-run)
        DRY_RUN=true
        shift
        ;;
    --keep-days)
        KEEP_DAYS="$2"
        shift 2
        ;;
    --keep-backups)
        KEEP_BACKUPS="$2"
        shift 2
        ;;
    -h | --help)
        echo "Usage: dotclaude-cleanup.sh [--dry-run] [--keep-days N] [--keep-backups N]"
        echo ""
        echo "Options:"
        echo "  --dry-run         Show what would be deleted without deleting"
        echo "  --keep-days N     Keep debug logs/snapshots/history newer than N days (default: 7)"
        echo "  --keep-backups N  Keep the N most recent backup files (default: 5)"
        exit 0
        ;;
    *)
        echo "Unknown option: $1" >&2
        exit 1
        ;;
    esac
done

# --- helpers ---
total_freed=0
section_count=0
section_no=0

# Print a numbered section header.
section() {
    section_no=$((section_no + 1))
    echo "[${section_no}] $1"
}

# Delete a list of files/dirs (passed via stdin, one per line) and track freed space.
# Uses process substitution (< <(...)) at call sites so this runs in the current shell
# and can update global counters (total_freed, section_count).
delete_files() {
    local count=0
    local freed=0

    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        if [[ -f "$f" || -d "$f" ]]; then
            local sz
            sz=$(du -sk "$f" 2>/dev/null | awk '{print $1}')
            if ! $DRY_RUN; then
                rm -rf "$f"
            fi
            count=$((count + 1))
            freed=$((freed + sz))
        fi
    done

    if [[ $count -gt 0 ]]; then
        section_count=$((section_count + 1))
        total_freed=$((total_freed + freed))
        local human
        human=$(humanize_kb $freed)
        local verb="Removed"
        $DRY_RUN && verb="Would remove"
        echo "  ${verb} ${count} item(s) — ${human}"
    else
        echo "  Nothing to clean"
    fi
}

humanize_kb() {
    local kb=$1
    if [[ $kb -ge 1048576 ]]; then
        awk "BEGIN {printf \"%.1f GB\", $kb/1048576}"
    elif [[ $kb -ge 1024 ]]; then
        awk "BEGIN {printf \"%.1f MB\", $kb/1024}"
    else
        echo "${kb} KB"
    fi
}

# --- initial measurement ---
total_before=$(du -sk "$CLAUDE_DIR" 2>/dev/null | awk '{print $1}')

echo "=== ~/.claude cleanup ==="
echo ""
if $DRY_RUN; then
    echo "  *** DRY RUN — nothing will be deleted ***"
    echo ""
fi
echo "Directory size before: $(humanize_kb "$total_before")"
echo "Retention: keep ${KEEP_DAYS} days of logs/snapshots, ${KEEP_BACKUPS} most recent backups"
echo ""

# --- Empty todo stubs ---
section "todos/ (empty 2-byte subagent stubs)"
if [[ -d "${CLAUDE_DIR}/todos" ]]; then
    delete_files < <(find "${CLAUDE_DIR}/todos" -maxdepth 1 -type f -name "*.json" -size -3c 2>/dev/null)
else
    echo "  Not present — skipping"
fi

# --- Empty session-env entries ---
section "session-env/ (empty session directories)"
if [[ -d "${CLAUDE_DIR}/session-env" ]]; then
    delete_files < <(find "${CLAUDE_DIR}/session-env" -mindepth 1 -maxdepth 1 -type d -empty 2>/dev/null)
else
    echo "  Not present — skipping"
fi

# --- Old debug logs ---
section "debug/ (debug logs older than ${KEEP_DAYS} days)"
if [[ -d "${CLAUDE_DIR}/debug" ]]; then
    delete_files < <(find "${CLAUDE_DIR}/debug" -maxdepth 1 -type f -mtime +"${KEEP_DAYS}" 2>/dev/null)
else
    echo "  Not present — skipping"
fi

# --- Old backups (keep most recent N) ---
section "backups/ (keeping ${KEEP_BACKUPS} most recent)"
if [[ -d "${CLAUDE_DIR}/backups" ]]; then
    delete_files < <(find "${CLAUDE_DIR}/backups" -maxdepth 1 -type f -name "*.backup.*" -print0 2>/dev/null |
        xargs -0 ls -t 2>/dev/null |
        tail -n +"$((KEEP_BACKUPS + 1))")
else
    echo "  Not present — skipping"
fi

# --- Old shell snapshots ---
section "shell-snapshots/ (older than ${KEEP_DAYS} days)"
if [[ -d "${CLAUDE_DIR}/shell-snapshots" ]]; then
    delete_files < <(find "${CLAUDE_DIR}/shell-snapshots" -maxdepth 1 -type f -mtime +"${KEEP_DAYS}" 2>/dev/null)
else
    echo "  Not present — skipping"
fi

# --- Old file-history entries ---
section "file-history/ (older than ${KEEP_DAYS} days)"
if [[ -d "${CLAUDE_DIR}/file-history" ]]; then
    delete_files < <(find "${CLAUDE_DIR}/file-history" -maxdepth 1 -type f -mtime +"${KEEP_DAYS}" 2>/dev/null)
else
    echo "  Not present — skipping"
fi

# --- drop-in extensions (overlays add their own sections here) ---
for extension in "${CLAUDE_DIR}/scripts/dotclaude-cleanup.d"/*.sh; do
    [[ -f "$extension" ]] || continue
    # shellcheck source=/dev/null
    source "$extension"
done

# --- summary ---
echo ""
echo "─────────────────────────────────────"

if $DRY_RUN; then
    echo "DRY RUN complete — no files were deleted"
    echo "Estimated reclaimable space: $(humanize_kb "$total_freed")"
else
    total_after=$(du -sk "$CLAUDE_DIR" 2>/dev/null | awk '{print $1}')
    actual_freed=$((total_before - total_after))
    echo "Directory size after:  $(humanize_kb "$total_after")"
    echo "Space reclaimed:       $(humanize_kb "$actual_freed")"
fi
echo "Sections cleaned: ${section_count}"
echo "─────────────────────────────────────"
