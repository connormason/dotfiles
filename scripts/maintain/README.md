[Project Root](../../README.md) > [Scripts](../README.md) > **Maintain Scripts**

---

# Maintain Scripts

Python scripts for automating common codebase maintenance tasks: keeping `.gitignore` patterns current and prek hook
versions up to date.

## Scripts

| Script                | Language | Description                                                                                   |
| --------------------- | -------- | --------------------------------------------------------------------------------------------- |
| `update_gitignore.py` | Python   | Refresh `.gitignore` with latest patterns from gitignore.io while preserving custom additions |
| `update_prek.py`      | Python   | Bump prek hook versions via `prek auto-update`                                                |

---

## update_gitignore.py

Fetches fresh ignore patterns for the template list embedded in the current `.gitignore`, splices them in, and preserves
any custom patterns that appear after the generated block. Uses three fetch methods in order: Python `urllib`, `curl`,
and `git-ignore-io`.

**Usage:**

```bash
# Update .gitignore with latest patterns
uv run scripts/maintain/update_gitignore.py

# Preview the updated content without writing the file
uv run scripts/maintain/update_gitignore.py --dry-run

# Force rewrite even when no content has changed
uv run scripts/maintain/update_gitignore.py --force

# Target a different .gitignore file
uv run scripts/maintain/update_gitignore.py --gitignore-path path/to/.gitignore
```

**Options:**

| Flag                    | Default      | Description                                      |
| ----------------------- | ------------ | ------------------------------------------------ |
| `--dry-run`             | off          | Print the updated content; do not write the file |
| `--force`               | off          | Write even when content is unchanged             |
| `--gitignore-path PATH` | `.gitignore` | Path to the `.gitignore` file to update          |

**Behavior:**

1. Reads the current `.gitignore` and extracts the template list from the embedded gitignore.io URL.
2. Extracts any custom patterns that appear after the `# End of https://www.toptal.com/developers/gitignore/api/`
   marker.
3. Fetches fresh content from `toptal.com/developers/gitignore/api/{templates}` (falls back to `curl`, then
   `git-ignore-io`).
4. Combines the fresh content with the preserved custom patterns.
5. Skips the write if content is unchanged (unless `--force`).

**Public API (`__all__`):**

| Symbol                             | Signature                                                 | Description                                            |
| ---------------------------------- | --------------------------------------------------------- | ------------------------------------------------------ |
| `extract_templates_from_gitignore` | `(gitignore_content: str) -> list[str]`                   | Parse template names from the gitignore.io URL         |
| `extract_custom_patterns`          | `(gitignore_content: str) -> list[str]`                   | Extract lines below the generated-content end marker   |
| `fetch_gitignore_content`          | `(templates: list[str]) -> str`                           | Fetch fresh content from gitignore.io (with fallbacks) |
| `generate_updated_gitignore`       | `(fresh_content: str, custom_patterns: list[str]) -> str` | Combine fresh content with preserved custom patterns   |

**Dependencies:** Python standard library only (`argparse`, `re`, `urllib`, `subprocess`).

---

## update_prek.py

Thin wrapper around `prek auto-update` that adds dry-run support, targeted repo filtering, tag/cooldown constraints, and
a configurable timeout. In dry-run mode the config file is reverted to its original state after auto-update runs, so the
diff is visible without any permanent changes.

**Usage:**

```bash
# Update all hooks in .pre-commit-config.yaml
uv run scripts/maintain/update_prek.py

# Preview what would change without persisting the update
uv run scripts/maintain/update_prek.py --dry-run

# Update only a specific repo
uv run scripts/maintain/update_prek.py --repo https://github.com/astral-sh/ruff-pre-commit

# Update multiple repos
uv run scripts/maintain/update_prek.py \
  --repo https://github.com/astral-sh/ruff-pre-commit \
  --repo https://github.com/pre-commit/pre-commit-hooks

# Only bump versions released at least 7 days ago, using a longer timeout
uv run scripts/maintain/update_prek.py --cooldown-days 7 --timeout 240
```

**Options:**

| Flag                      | Default                   | Description                                                   |
| ------------------------- | ------------------------- | ------------------------------------------------------------- |
| `-c, --config PATH`       | `.pre-commit-config.yaml` | Path to the prek/pre-commit config file                       |
| `-r, --repo URL`          | (all repos)               | Restrict update to this repo URL; repeat for multiple repos   |
| `--exclude-repo URL`      | (none)                    | Skip the given repo URL; repeat for multiple repos            |
| `--include-tag PATTERN`   | (all tags)                | Only consider tags matching this glob pattern; repeatable     |
| `--exclude-tag PATTERN`   | (none)                    | Ignore tags matching this glob pattern; repeatable            |
| `--repo-include-tag SPEC` | (none)                    | Per-repo tag include filter as `<repo>=<pattern>`; repeatable |
| `--repo-exclude-tag SPEC` | (none)                    | Per-repo tag exclude filter as `<repo>=<pattern>`; repeatable |
| `--bleeding-edge`         | off                       | Update to the default branch head instead of the latest tag   |
| `--freeze`                | off                       | Store frozen hashes in `rev` instead of tag names             |
| `--cooldown-days DAYS`    | (none)                    | Minimum release age (in days) for a version to be eligible    |
| `-j, --jobs N`            | (prek default)            | Number of threads prek should use (`0` lets prek decide)      |
| `--refresh`               | off                       | Refresh all cached prek data before running                   |
| `-t, --timeout SECONDS`   | `120`                     | Timeout for the `prek auto-update` subprocess                 |
| `--dry-run`               | off                       | Run auto-update, show changes, then revert the file           |
| `-h, --help`              | —                         | Show help and exit                                            |

**Behavior:**

1. Reads the current config file content for later comparison / revert.
2. Runs `prek auto-update` (optionally scoped to specific repos and tag/cooldown constraints).
3. Prints stdout from auto-update (`Updating <repo> ... <old> -> <new>` lines).
4. If `--dry-run` and changes were made, reverts the file to its original state.
5. Reports whether any hook versions changed.

**Public API (`__all__`):**

| Symbol           | Signature                                                            | Description                                   |
| ---------------- | -------------------------------------------------------------------- | --------------------------------------------- |
| `run_autoupdate` | `(config_path: Path, *, repo_urls=None, ..., timeout=120, **kwargs)` | Run `prek auto-update` and return the process |

**Dependencies:** Python standard library only (`argparse`, `subprocess`, `pathlib`). Requires `prek` on PATH.

---

## See Also

- [Scripts Overview](../README.md) — Parent directory documentation
