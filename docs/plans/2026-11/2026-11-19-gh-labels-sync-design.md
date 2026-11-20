# GitHub Label Sync — Design

## Problem

The source repository carries a hand-tuned label set (12 labels: three GitHub defaults plus nine custom ones, none with
a description). Every new project needs the same set, and copying each name, color, and description through the GitHub
UI is slow and error-prone. GitHub offers no account-level default labels, so the definition has to live somewhere the
user controls and be pushed to each repo on demand.

## Decision

A single-file Python tool, `gh-labels`, plus a TOML file that is the source of truth for the label set. Both ship as a
stow package (`ghtools`) so the command is on `PATH` on every machine and the definition is versioned with the rest of
the dotfiles.

Approaches considered:

| Approach                                                      | Verdict                                                                                                       |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Shell loop over `gh label create --force`                     | Rejected: no dry run, no diff, no pruning, and TOML parsing in bash is clumsy.                                |
| **PEP 723 Python script, stdlib `tomllib`, `gh api` calls**   | **Chosen:** idempotent, previewable, zero dependencies beyond `uv`, and `gh` supplies host selection and auth. |
| Probot or settings-sync service                               | Rejected: far too heavy for personal repos.                                                                   |

## Where it lives

The package goes in the **personal base repository, `~/dotfiles-personal`**, not in an employer-specific overlay
repository.

- The tool is generic: it works against any GitHub host that `gh` can reach.
- The overlay repository is converging onto the base as an overlay-only layer. Its packages must be companions of a base
  package (enforced by its layout tests), and its legacy `stow/` directory is scheduled for deletion.
- A new package under that legacy `stow/` would fail the overlay's coverage test unless the base also provided it, and
  would then be deleted anyway.
- The base already runs `stow --no-folding` for every package, so `~/.local/bin` (which holds uv tool symlinks and other
  real files) needs no special handling there, and `~/.local/bin` is already on `PATH`
  (`stow/shell/.config/zsh/conf.d/00-path.zsh`).

Consequence: implementation runs in a session started in `~/dotfiles-personal` (cross-repo git is refused from the
overlay repository's sessions). This plan lives in the base repository.

## Package layout (in `~/dotfiles-personal`)

```
stow/ghtools/
├── .config/gh-labels/labels.toml   # source of truth for the label set
└── .local/bin/gh-labels            # executable, PEP 723 `uv run --script`
tests/unit/ghtools/
├── __init__.py
└── test_gh_labels.py
```

## Config schema

```toml
[[label]]
name        = "feature"
color       = "5ab1cd"                  # '#' optional; normalised to six lowercase hex digits
description = "New user-facing capability"  # optional
```

Validation rejects: no `[[label]]` tables, unknown keys, a missing or empty `name`, a name over 50 characters, a
description over 100 characters (GitHub's limits), a non-six-hex-digit color, and names that collide
case-insensitively (GitHub treats names that way).

## CLI

```
gh-labels apply [-r [HOST/]OWNER/REPO] [-c PATH] [-n] [--prune]
gh-labels pull  [-r [HOST/]OWNER/REPO] [-o PATH]
```

- `apply` reconciles the repository's labels with the config.
- `pull` prints (or writes with `-o`) the repository's current labels as TOML, so the definition can be seeded from an
  existing repo such as the source repository.
- `--repo` defaults to the repository of the current directory (`gh repo view`). The host is taken from that repo's
  URL; for an explicit repo on a host other than `gh`'s default, pass `HOST/OWNER/REPO`.
- `--config` defaults to `$XDG_CONFIG_HOME/gh-labels/labels.toml`, falling back to `~/.config/gh-labels/labels.toml`.

## Reconcile semantics

1. Fetch labels with `gh api --paginate --slurp repos/OWNER/REPO/labels?per_page=100` and flatten the pages.
2. Match configured labels to existing ones by case-folded name.
3. **Create** labels that are missing; **update** labels whose name casing, color, or description differ; leave the rest
   alone.
4. Labels in the repository but not in the config are reported only. `--prune` deletes them. It is opt-in because
   deleting a label strips it from every issue and pull request that carries it.
5. `--dry-run` prints the same report and makes no mutating call.
6. A second run against an unchanged repository performs no mutations.

All `gh` calls pass arguments as a list (no shell), and label names are URL-quoted in endpoint paths.

## Out of scope for v1

- Renaming labels via `aliases` (rename on GitHub, or prune and re-create).
- Syncing many repositories in one invocation (loop in the shell).
- Org-level or template-repository label inheritance.

## Testing

Pure functions (color normalisation, parsing and validation, TOML rendering, repo parsing, plan building) are unit
tested directly. The `gh` layer is replaced by a recording fake so create, update, prune, dry-run, host selection, and
both subcommands are exercised end to end without network access. Further tests check that the shipped seed
`labels.toml` validates and that the script is executable with a PEP 723 header. The base's
`tests/unit/test_docs_consistency.py` keeps `stow/README.md` honest about the new package.
