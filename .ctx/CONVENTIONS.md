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
5. A package meant for one OS only carries a `.dotfiles-os` marker listing its OS ids (`darwin`, `linux`); without one,
   `stow.sh` links it on every OS, the NAS included. See [`stow/README.md`](../stow/README.md#os-specific-packages).

## Adding macOS Applications

Edit the manifests in `bootstrap/`:

- CLI tools and GUI apps → `Brewfile`
- VS Code extensions → `vscode-extensions.txt`
- uv tools → `uv-tools.txt`
- Applications for one machine only → that machine's overlay under `profiles/`

The NAS applies the base `Brewfile` too (through Linuxbrew), so entries that exist only on macOS (casks, fonts, Mac App
Store apps, formulae the NAS should not get) go inside the `if OS.mac?` block at the end of the file.

## Adding a New Ansible Role (NAS)

The full procedure is in [`roles/README.md`](../roles/README.md#adding-a-role). In short:

1. Create `roles/<name>/` with `tasks/main.yml` (FQCN modules, idempotent tasks), optional `defaults/main.yml`, and a
   `README.md`.
2. Include it in `playbooks/nas_bootstrap.yml` with `include_role`, putting the role-name tag in both `apply` and the
   include's own `tags`.
3. Add any new collection to `roles/requirements.yml`, and update `EXPECTED_ORDER` in
   `tests/unit/test_nas_playbook.py`.
4. Document it in playbook order: a row in `roles/README.md`, a step in the execution-order list of
   `playbooks/README.md`, and a bullet in the "Role System (NAS)" list of [`ARCHITECTURE.md`](ARCHITECTURE.md).
   `tests/unit/test_docs_consistency.py` checks all three against the playbook.

## Adding a Compose Service (NAS)

1. Create `services/<name>/compose.yml`. The service key inside it equals the directory name, because `deploy.sh` runs
   `up -d <name>`.
2. A service that needs a secret also ships `services/<name>/env.j2` and sets `env_file: <name>/.env` in its
   `compose.yml`; the `services` role renders the template (from inventory variables) for services that have a
   `compose.yml`.
3. Add a row to the Quick Reference table in [`services/README.md`](../services/README.md#quick-reference);
   `tests/unit/test_docs_consistency.py` fails when the table and the compose files disagree.
4. Deploy with `python3 run.py nas-deploy <name>` (`--dry-run` previews). A push to `main` that touches the directory
   deploys it from CI as well.
5. To disable a service, rename its `compose.yml` to `compose.yml.disabled`.
