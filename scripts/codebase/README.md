[Project Root](../../README.md) > [Scripts](../README.md) > **Codebase**

# Codebase Scripts

Scripts that keep generated, tracked files current. The scheduled
[`Update gitignore`](../../.github/workflows/update-gitignore.yml) workflow runs `update_gitignore.py`.

| Script                                       | Purpose                                                                    |
| -------------------------------------------- | -------------------------------------------------------------------------- |
| [`update_gitignore.py`](update_gitignore.py) | Refresh the gitignore.io block of `.gitignore`, preserving custom patterns |

## `update_gitignore.py`

Reads the template list from the toptal.com URL in the `.gitignore` header, fetches fresh content (`urllib`, falling
back to `curl`), and re-appends the custom lines found after the generated block's end marker.

```
uv run --no-project scripts/codebase/update_gitignore.py [--gitignore-path PATH] [--dry-run] [--force]
```

| Option             | Description                                            |
| ------------------ | ------------------------------------------------------ |
| `--gitignore-path` | File to refresh (default: `.gitignore`)                |
| `--dry-run`        | Print the result without writing                       |
| `--force`          | Write (and report an update) even when nothing changed |

Exit codes: `0` updated or already up to date, `1` on any error. The file is never modified on error: a missing
gitignore.io URL, a missing end marker (which would otherwise drop custom patterns), and fetched content without the end
marker (an error page or truncated response) are all refused.

| Symbol                       | Signature                                                 | Description                                           |
| ---------------------------- | --------------------------------------------------------- | ----------------------------------------------------- |
| `extract_templates`          | `(gitignore_content: str) -> list[str]`                   | Template names from the embedded URL                  |
| `extract_custom_patterns`    | `(gitignore_content: str) -> list[str]`                   | Lines after the end marker, outer blank lines dropped |
| `fetch_gitignore_content`    | `(templates: list[str]) -> str`                           | Fetch fresh content via `urllib`, then `curl`         |
| `generate_updated_gitignore` | `(fresh_content: str, custom_patterns: list[str]) -> str` | Fresh block plus preserved custom lines               |

## Scheduled workflows

| Workflow                                                                     | Schedule (UTC) | Branch                            | Updates                                            |
| ---------------------------------------------------------------------------- | -------------- | --------------------------------- | -------------------------------------------------- |
| [`update-dependencies.yml`](../../.github/workflows/update-dependencies.yml) | Tuesdays 09:00 | `maintenance/update-dependencies` | prek hook revisions, `uv.lock`, `requirements.txt` |
| [`update-gitignore.yml`](../../.github/workflows/update-gitignore.yml)       | Mondays 09:00  | `maintenance/update-gitignore`    | `.gitignore`                                       |

Each run force-pushes one commit on top of `main` to its evergreen branch and opens, or refreshes, a pull request
against `main` through the [`open-maintenance-pr`](../../.github/actions/open-maintenance-pr/action.yml) composite
action. Both can also be started by hand (`gh workflow run "Update gitignore"`) and only run from `main`.

### One-time setup

Pull requests opened with the default `GITHUB_TOKEN` do not trigger other workflows, so the maintenance PRs would get no
lint or leak checks. The workflows therefore push and open PRs with a personal access token:

1. Create a fine-grained token limited to this repository with **Contents: read and write** and **Pull requests: read
   and write**.
2. Store it as the Actions secret `MAINTENANCE_PR_TOKEN`.

Both workflows fail at their first step with an explicit error while the secret is unset. Fine-grained tokens expire (at
most one year); a lapsed token fails the run at the push step, so renew the secret then.

## Dependencies

`update_gitignore.py` is standard-library only (`curl` is an optional fallback). The workflows additionally use `uv`,
`prek`, and `gh`, all present on `ubuntu-latest` runners or installed from the `lint` dependency group.
