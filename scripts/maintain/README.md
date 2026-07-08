[Project Root](../../README.md) > [Scripts](../README.md) > **Maintain Scripts**

---

# Maintain Scripts

Python scripts for automating common codebase maintenance tasks: keeping `.gitignore` patterns current and pre-commit
hook versions up to date.

## Scripts

| Script                | Language | Description                                                                                   |
| --------------------- | -------- | --------------------------------------------------------------------------------------------- |
| `update_gitignore.py` | Python   | Refresh `.gitignore` with latest patterns from gitignore.io while preserving custom additions |
| `update_precommit.py` | Python   | Bump pre-commit hook versions via `pre-commit autoupdate`                                     |

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

## update_precommit.py

Thin wrapper around `pre-commit autoupdate` that adds dry-run support, targeted repo filtering, and a configurable
timeout. In dry-run mode the config file is reverted to its original state after autoupdate runs, so the diff is visible
without any permanent changes.

**Usage:**

```bash
# Update all hooks in .pre-commit-config.yaml
uv run scripts/maintain/update_precommit.py

# Preview what would change without persisting the update
uv run scripts/maintain/update_precommit.py --dry-run

# Update only a specific repo
uv run scripts/maintain/update_precommit.py --repo https://github.com/astral-sh/ruff-pre-commit

# Update multiple repos
uv run scripts/maintain/update_precommit.py \
  --repo https://github.com/astral-sh/ruff-pre-commit \
  --repo https://github.com/pre-commit/pre-commit-hooks

# Use a non-default config file with a longer timeout
uv run scripts/maintain/update_precommit.py -c .pre-commit-config.yaml --timeout 240
```

**Options:**

| Flag                    | Default                   | Description                                                 |
| ----------------------- | ------------------------- | ----------------------------------------------------------- |
| `-c, --config PATH`     | `.pre-commit-config.yaml` | Path to the pre-commit config file                          |
| `-r, --repo URL`        | (all repos)               | Restrict update to this repo URL; repeat for multiple repos |
| `-t, --timeout SECONDS` | `120`                     | Timeout for the `pre-commit autoupdate` subprocess          |
| `--dry-run`             | off                       | Run autoupdate, show changes, then revert the file          |
| `-h, --help`            | —                         | Show help and exit                                          |

**Behavior:**

1. Reads the current config file content for later comparison / revert.
2. Runs `pre-commit autoupdate` (optionally scoped to specific repos).
3. Prints stdout from autoupdate (`Updating <repo> ... <old> -> <new>` lines).
4. If `--dry-run` and changes were made, reverts the file to its original state.
5. Reports whether any hook versions changed.

**Public API (`__all__`):**

| Symbol           | Signature                                      | Description          |
| ---------------- | ---------------------------------------------- | -------------------- |
| `run_autoupdate` | \`(config_path: Path, \*, repo_urls: list[str] | None, timeout: float |

**Dependencies:** Python standard library only (`argparse`, `subprocess`, `pathlib`). Requires `pre-commit` on PATH.

---

## See Also

- [Scripts Overview](../README.md) — Parent directory documentation
