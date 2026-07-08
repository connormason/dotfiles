# Conventions & Common Patterns

Code style, file organization, and the recurring "how do I add X" patterns for the dotfiles-personal repository. Loaded
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

## Adding a New Dotfile

1. Place the source file in the appropriate `roles/*/files/` directory.
2. Use the `link_dotfile` role in the playbook:

```yaml
- include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_dir }}/roles/myapp/files/config"
    link_dotfile_dst: "{{ home_dir }}/.config/myapp/config"
```

## Adding a New Ansible Role

1. Create the role directory: `roles/new-role/`
2. Add `tasks/main.yml` with the role logic (FQCN modules, tags, idempotent tasks).
3. Add `defaults/main.yml` for default variables (optional).
4. Include the role in the appropriate playbook (`local_bootstrap.yml` or `nas_bootstrap.yml`).
5. Add role tags for selective execution.

## Adding macOS Applications

Edit `roles/macos/defaults/main.yml`:

- CLI tools → `brew_packages`
- GUI apps → `brew_cask_packages`
- App Store apps → `mas_apps` (requires the app ID from the App Store)
