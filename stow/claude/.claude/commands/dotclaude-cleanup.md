Run the ~/.claude disk cleanup script to reclaim space from stale artifacts.

## Task

Execute the cleanup script at `~/.claude/scripts/dotclaude-cleanup.sh` and relay the results.

## Workflow

1. **Dry run first**: Run the script with `--dry-run` to show what would be cleaned
2. **Show the preview**: Display the dry-run output so the user can review it
3. **Confirm**: Ask the user if they want to proceed with the actual cleanup
4. **Execute**: If confirmed, run the script without `--dry-run`
5. **Report**: Display the final cleanup summary

## Options

The user can pass arguments after the command which are forwarded to the script:

- `--dry-run` — Only show what would be deleted (skip step 3, stop at dry run)
- `--keep-days N` — Keep debug logs, snapshots, and file history newer than N days (default: 7)
- `--keep-backups N` — Keep the N most recent backup files (default: 5)

## Examples

```
/dotclaude-cleanup                    # interactive: dry-run preview, then confirm
/dotclaude-cleanup --dry-run          # preview only, no deletion
/dotclaude-cleanup --keep-days 14     # be more conservative with retention
```

## What Gets Cleaned

| Area               | Description                                      |
| ------------------ | ------------------------------------------------ |
| `todos/`           | Empty 2-byte JSON stubs from subagents           |
| `session-env/`     | Empty session environment stubs                  |
| `debug/`           | Debug logs older than retention window           |
| `backups/`         | Old config backups beyond the keep count         |
| `shell-snapshots/` | Shell snapshots older than retention window      |
| `file-history/`    | File history entries older than retention window |

Overlays can add sections by dropping `*.sh` files into `~/.claude/scripts/dotclaude-cleanup.d/`; the script sources
each one after its built-in sections.

## Implementation

Run the script via Bash:

```bash
# Dry run
~/.claude/scripts/dotclaude-cleanup.sh --dry-run $ARGUMENTS

# Actual cleanup (after user confirms)
~/.claude/scripts/dotclaude-cleanup.sh $ARGUMENTS
```

Display the output verbatim — the script formats its own summary with section-by-section breakdowns and a total space
reclaimed figure.
