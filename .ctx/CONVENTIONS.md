# Conventions & Common Patterns

Code style, file organization, and the recurring "how do I add X" patterns for the dotfiles repository. Loaded
on demand from [`CLAUDE.md`](../CLAUDE.md).

## Code Style

Self-contained style rules live in [`.claude/rules/`](../.claude/rules) (they do not depend on any global
`~/.claude/rules/`):

- [`python-style.md`](../.claude/rules/python-style.md) — ruff line-length 120, target py39, single quotes,
  `force-single-line` imports, **sphinx** docstring convention, interrogate 70%. Always run Python via `uv`; never run
  `ruff format`.
- [`script-style.md`](../.claude/rules/script-style.md) — `run.py` is the reference implementation of the styling
  contract.
- [`readme-guidelines.md`](../.claude/rules/readme-guidelines.md) — per-directory READMEs with breadcrumbs;
  auto-formatted with mdformat via prek (`.ctx/` and `docs/plans/` excluded).

## Adding a New Dotfile (macOS)

1. Put the file in `stow/<package>/` at its `$HOME`-relative path (e.g. `stow/git/.config/git/ignore`). A new tool gets
   a new package directory.
2. Preview the links with `./stow.sh -n`; `bootstrap/95-dotfiles.sh` applies them.
3. Add the package to the table in [`stow/README.md`](../stow/README.md). `tests/unit/test_docs_consistency.py` fails
   when the table and the directories under `stow/` disagree.
4. Files an app rewrites at runtime (settings JSON) are rendered from `render/<target>.json` fragments instead; stow
   refuses to link a render target.

## Adding macOS Applications

Edit the manifests in `bootstrap/`:

- CLI tools and GUI apps → `Brewfile`
- VS Code extensions → `vscode-extensions.txt`
- uv tools → `uv-tools.txt`
- Applications for one machine only → that machine's overlay under `profiles/`

## Adding a New Ansible Role (NAS)

1. Create the role directory: `roles/new-role/`
2. Add `tasks/main.yml` with the role logic (FQCN modules, tags, idempotent tasks).
3. Add `defaults/main.yml` for default variables (optional).
4. Include the role in `playbooks/nas_bootstrap.yml`.
5. Add role tags for selective execution.
