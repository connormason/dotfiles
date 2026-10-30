# Dev Environment Base & Overlay Design

**Date:** 2026-10-26
**Status:** Approved in brainstorming; pending review of this written spec
**Goal:** Make this public repo the single source of the user's development environment on every Mac, with a private
work repository layered on top for employer-only tooling: complete dev-env parity between the personal and work
machines, minimal duplicated configuration, and zero employer-internal content in this repo.

## Context

Two dotfiles repositories evolved independently:

- **This repo** (public) is Ansible-based. Its macOS dev-environment roles (`zsh`, `git`, `iterm`, `python`,
  `starship`, `hammerspoon`, `macos*`) date largely from 2020–2023: oh-my-zsh + powerlevel10k, pip into the system
  Python, `hub`, Sublime. There is no tmux, editor, mise/uv, or Claude Code configuration. The NAS side
  (`roles/{debian,docker,samba,zfs}`, `services/`) is a separate project.
- **The work repo** (private, employer-hosted) migrated in 2026 from Ansible to GNU Stow packages plus numbered
  bootstrap shell stages. It has a `conf.d` zsh loader whose per-tool snippets live inside their stow packages, a
  `.gitconfig.local` identity split, a tracked `~/.claude`, VS Code / Zed / tmux / starship configuration, `run.py`
  doctor and test tooling, and unit/integration tests. Roughly two thirds of it is generic; the rest is employer-only
  (whole packages, specific lines in mixed packages, and most of the Claude Code `settings.json`).

The user develops personal projects on **both** machines. The work machine must never break during the transition. The
public-repo leak guard (`docs/plans/2026-10/2026-10-26-public-leak-guard-design.md`, merged in #17) protects this repo:
every port from the work repo passes through it.

### Prerequisites (before any content is ported in Phase A)

1. **Private leak patterns installed on the work Mac.** Until the work overlay supplies
   `~/.config/dotfiles/leak-patterns.txt`, the guard only knows the public baseline and cannot recognize internal tool
   or product names. A minimal private file is created on the work Mac by hand before porting starts; Phase C later
   moves it into the work overlay.
2. **A `pre-push` leak check.** `cherry-pick`, `rebase`, `am`, and `--no-verify` bypass the `pre-commit` and
   `commit-msg` hooks, and ported commits are the likeliest carriers of internal identifiers. A `pre-push` stage runs
   `check-leaks` over the pushed range's changed files, author/committer identities, and commit messages, so nothing
   reaches the public remote unchecked.

## Decisions

| Decision                  | Choice                                                                                     | Rationale                                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Dev-env engine            | Adopt the work repo's stow + numbered-stage architecture; retire Ansible for macOS         | Proven and more mature on the work machine; sharing one engine is the point of the exercise.          |
| Layering                  | One engine (this repo) plus registered overlays                                            | No duplicated engine logic; the work repo shrinks to employer-only content.                           |
| Ownership                 | Every `$HOME` target owned by exactly one layer; the base ships composition points         | Stow conflicts become impossible by construction, and the rule is testable.                           |
| Base stack                | The work repo's generic stack, wholesale                                                   | Parity. Legacy personal configs are dropped.                                                          |
| Legacy personal survivors | Personal-only GUI apps, as the in-repo `profiles/personal-mac` overlay                     | User choice; macOS defaults, Dock layout, and the old Hammerspoon config are dropped.                 |
| Claude Code settings      | Rendered merge of per-layer fragments into a real `settings.json`, with a drift guard      | Works for every launch path (CLI, IDE, desktop); the employer auth helper must never be missed.       |
| VS Code settings          | Same render tool                                                                           | One mechanism; a fallback is recorded under Clarifications.                                           |
| Git identity              | Personal default, work-overlay default, and `includeIf hasconfig:remote` for personal remotes | Correct identity per repo on both machines with no secrets; reduces the chance of work-email commits to public repos (see the limits below). |
| NAS Ansible               | Untouched (`roles/`, `playbooks/`, `library/`, `services/`, inventory/vault commands)      | Separate project.                                                                                     |

## Architecture

### Repository layout (after this project)

```
dotfiles-personal/
  stow/<pkg>/               generic stow packages
  stow.sh                   engine entry: base packages, then each registered overlay's packages
  bootstrap/
    bootstrap.sh lib.sh     driver (--dry-run / --only / --from / --resume / --verify)
    NN-*.sh                 base stages
    Brewfile uv-tools.txt vscode-extensions.txt repos.txt
  render/                   base JSON fragments: claude.json, vscode.json
  profiles/personal-mac/    in-repo overlay (personal-only Brewfile)
  run.py                    dev/test/doctor/render tooling + NAS inventory/vault commands
  roles/ playbooks/ library/ services/   NAS only (unchanged)
  tests/
```

### Overlay contract

An **overlay** is any directory shaped like the repo root; every part is optional:

| Path in overlay                                                       | Meaning                                                    |
| --------------------------------------------------------------------- | ---------------------------------------------------------- |
| `stow/<pkg>/`                                                         | Additional stow packages (discovered by directory listing) |
| `bootstrap/NN-*.sh`                                                   | Additional stages, merged with base stages by number       |
| `bootstrap/{Brewfile,uv-tools.txt,vscode-extensions.txt,repos.txt}`   | Manifest fragments, concatenated after the base's          |
| `render/<id>.json`                                                    | Render fragments, merged after the base's                  |

Overlays are registered one absolute path per line in `~/.config/dotfiles/overlays` (machine-local, untracked). Personal
Mac: `<repo>/profiles/personal-mac`. Work Mac: the work repo root. Layer order is the base first, then overlays in file
order.

**Engine rules:**

- Packages are discovered by listing directories (replacing the work repo's hardcoded package array); a test asserts that
  discovery matches the directory tree.
- Duplicate stage numbers across layers are an error. Stages from all layers run in numeric order, so an overlay stage
  can run between base stages (for example, an employer Homebrew installer at `45` before the base `50-brew`).
- No hardcoded repository paths: the engine resolves its own root, and overlay paths come from the registry.
- Composition directories are created as real directories before stowing, so stow never folds them into a single
  symlink: `~/.config/zsh/conf.d`, `~/.ssh/config.d`, `~/.claude/{agents,commands,hooks,rules,skills}`.
- Rendered files are owned by the render tool: `stow.sh` refuses any package that provides a render target (or a path
  above one), reading the target list from `render.py --list-targets` so the list has one source of truth.

### Composition points

| Area                                                         | Composition point                                                                 | Base ships                   | Overlays may add       |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------- | ---------------------------- | ---------------------- |
| zsh                                                          | `~/.config/zsh/conf.d/NN-*.zsh` in lexical order; untracked `~/.zshrc.local` last | `00`–`90` snippets           | more `NN-*.zsh`        |
| git                                                          | `[include] path = ~/.gitconfig.overlay`, followed by the identity `includeIf`     | `.gitconfig`                 | `~/.gitconfig.overlay` |
| ssh                                                          | `Include ~/.ssh/config.d/*` at the top of `~/.ssh/config`                         | `config.d/personal`          | `config.d/<name>`      |
| Hammerspoon                                                  | `pcall(require, 'overlay')` at the end of `init.lua`                              | `init.lua`, Spoons           | `overlay.lua`          |
| Tools without include support (`uv.toml`, `pip.conf`, `.npmrc`) | owned whole by exactly one layer                                               | nothing                      | the whole file         |
| Manifests                                                    | concatenation                                                                     | base lists                   | fragments              |
| Leak guard                                                   | `~/.config/dotfiles/leak-patterns.txt`                                            | nothing                      | private patterns       |
| Rendered JSON                                                | `render/<id>.json` per layer                                                      | `claude.json`, `vscode.json` | fragments              |

**Git identity** (`.gitconfig`; order matters, later wins):

```ini
[user]
    name  = <personal name>
    email = <personal email>               ; already public in this repo's history
[include]
    path = ~/.gitconfig.overlay            ; work overlay: default identity = work email
[includeIf "hasconfig:remote.*.url:git@github.com:connormason/**"]
    path = ~/.config/git/identity-personal ; repos with a matching remote use the personal identity (limits below)
[includeIf "hasconfig:remote.*.url:https://github.com/connormason/**"]
    path = ~/.config/git/identity-personal
[includeIf "hasconfig:remote.*.url:ssh://git@github.com/connormason/**"]
    path = ~/.config/git/identity-personal
[includeIf "hasconfig:remote.*.url:https://*@github.com/connormason/**"]
    path = ~/.config/git/identity-personal ; token / userinfo HTTPS remotes
```

Git ignores missing include files, so a machine without an overlay needs nothing extra. (`hasconfig:remote.*.url`
requires git 2.36+; Homebrew git satisfies this, and `doctor` checks it.)

**Limits.** The `includeIf` match is a case-sensitive glob against the remote URLs present when git reads its
configuration, so it is a mitigation, not a guarantee. A repository falls back to the overlay's default identity when it
has no remote yet (commits made before `git remote add` keep the default), when the owner or host differs in letter
case, when the remote uses an SSH host alias or an explicit port, or when the URL is spelled any other way (for example
`www.github.com`, or an `url.<base>.insteadOf` alias, which is matched as written). Mitigation: add the remote before
the first commit, or set `user.name` and `user.email` in the repository (without that, `user.name` still comes from the
overlay's default if it sets one, else from the personal default). The leak guard's `--identity` check is the backstop
for patterns it knows.

### Render tool (`run.py render`, bootstrap stage `97-render`)

- **Targets:** `claude` → `~/.claude/settings.json`; `vscode` → `~/Library/Application Support/Code/User/settings.json`.
- **Merge** (base, then overlays in order): objects deep-merge; arrays concatenate with order-preserving de-duplication;
  for scalars the later layer wins; an explicit `null` deletes the key.
- **Output:** deterministic pretty JSON (sorted keys, 2-space indent, trailing newline).
- **Drift guard:** the last managed render (the managed keys as JSON, mode `0600`) is stored in
  `${XDG_STATE_HOME:-~/.local/state}/dotfiles/render/<id>.json`. If the live file's managed content differs from both
  that state and the new render (edited in-app), `render` refuses, prints the live-vs-last-render diff, and exits
  non-zero. `render --diff` previews; `render --force` backs the live file up to `~/.dotfiles-backup/<timestamp>/` and
  overwrites.
- **Claude specifics:** `CLAUDE.md` stays generic, and employer-specific instructions become overlay `rules/*.md`
  (user-level rules auto-load). Hook commands use `$HOME`, never an absolute home path. The base fragment enables public
  plugin marketplaces; an overlay fragment may add others and disable duplicates via `false`/`null`.

### Package scope (base)

These are ported from the work repo's generic stack, with every employer-specific line moved to the work overlay through
the composition points above:

- **shell:** `conf.d` loader, oh-my-zsh, completion, aliases, directories, banner.
- **git:** config, `gh` `config.yml`, worktrunk, git template hook. `gh` `hosts.yml` becomes untracked.
- **python:** zsh snippet, IPython startup, hatch/uv tool configuration without any index settings.
- **node.**
- **claude:** directories plus the base render fragment.
- **vscode:** keybindings and snippets plus the base render fragment.
- **zed, iterm2, hammerspoon, tmux, starship, fzf, zoxide, homebrew.**
- **os_tools:** btop, eza, fastfetch, htop, ranger, sshm.

Bootstrap stages cover a generic SSH key, Homebrew with `brew bundle` over all Brewfiles, uv tools, macOS settings,
repos from `repos.txt`, stow, render, and verify.

`run.py` gains the work repo's generic commands (`doctor`, `status`, `bootstrap`, `test-*`, the hook commands, manifest
dumps, `report`, `backup`) plus `render`. `snapshot`, which the Phase D safeguards use, is owned by the Phase C plan
(work repo). The NAS inventory/vault commands stay.

**Removed:** the Ansible roles `iterm`, `python`, `starship`, `hammerspoon`, `macos`, `macos_settings`, `macos_dock`,
`link_dotfile`, plus `playbooks/local_bootstrap.yml` and `local_bootstrap.sh`. Roles shared with the NAS playbook
(`git`, `ssh`, `zsh`, `tailscale`) stay until the NAS project replaces them; only their macOS branches are removed.

## Rollout

| Phase                      | Where                | Machine impact                                                                                                      |
| -------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **A — build the base**     | this repo            | None. Engine, packages, render tool, tests, macOS CI job.                                                           |
| **B — personal Mac**       | personal MacBook     | Remove old Ansible-era links, bootstrap base + `personal-mac`, verify (`doctor`, plugin merge, settings layering).  |
| **C — build work overlay** | work repo (own plan) | None. The overlay is rendered into a throwaway `$HOME` on the work Mac and compared with the live `$HOME`.          |
| **D — work cutover**       | work Mac (own plan)  | The only risky step; safeguards below.                                                                              |

Phases C and D are planned in the work repository, the only place that can name employer-specific content.

**Phase D safeguards** (requirements on that plan):

1. `run.py snapshot` (built by the Phase C plan in the work repo; this base does not ship it) before cutover records:
   - the resolved-content hash of every managed `$HOME` path
   - a `zsh -i` dump of the environment, `PATH`, `fpath`, aliases, and function names
   - `git config --list`
   - `ssh -G` for key hosts
   - the parsed rendered JSON
2. A `stow -n` dry run of base + overlay reports zero conflicts.
3. Cutover happens with a spare terminal open: tag the work repo `pre-overlay`, unstow the old packages (`stow -D`),
   stow the new ones, render. The unstow must come **before** the new layers are stowed: the old work repo's stow
   folded whole directories into single symlinks pointing into that repo, and if they are still present the new
   `stow.sh --backup-conflicts` classifies each one as a foreign symlink and moves it into `~/.dotfiles-backup/`,
   emptying those directories in `$HOME`. Relative foreign symlinks also break once moved inside the backup directory
   (they resolve against their new location), so the backup is no restore source for them.
4. Re-snapshot and diff. The diff must be empty or match an explicit allowlist; otherwise, roll back.
5. Smoke tests:
   - a new terminal opens
   - commits in a work repo and in a personal repo carry the right identities
   - `claude` starts and authenticates
   - VS Code opens
   - package managers resolve to the expected indexes
6. `rollback.sh`, rehearsed in Phase C against the throwaway `$HOME`, unstows the new layers, re-stows `pre-overlay`,
   and restores rendered files from backup. The old packages stay in work-repo history for at least two weeks of stable
   use.

**Transition drift:** once Phase A starts, any change to a generic package in the work repo is ported to this base the
same week. The Phase C comparison catches misses.

## Testing

| Test                                  | Proves                                                                                                    |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Ownership (unit)                      | No two layers claim one `$HOME` target; discovery matches the tree; composition dirs are pre-created real. |
| Render (unit)                         | Merge semantics, deterministic output, and the drift guard's refuse / `--diff` / `--force` paths, on fixture fragments. |
| Stage ordering (unit)                 | Cross-layer numeric merge; duplicate numbers rejected.                                                    |
| Throwaway-home integration (macOS CI) | See below.                                                                                                |
| Docs consistency (unit)               | READMEs and package tables match the tree.                                                                |
| Leak guard                            | Existing (pre-commit, commit-msg, CI); `pre-push` added as a prerequisite.                               |

The throwaway-home integration test runs with `HOME=$(mktemp -d)` and stows the base plus a fixture overlay that
exercises every composition point. It then checks:

- `zsh -i -c exit` succeeds with empty stderr in under 300 ms
- `git config user.email` switches by remote URL
- `ssh -G` reads `config.d`
- the rendered JSON parses

On machines, `run.py doctor` additionally checks overlay registration, render drift, composition-directory integrity,
and the git version. The Phase D snapshot diff is the cutover acceptance test.

## Clarifications Needed (resolve by experiment in Phases A/B)

1. How Claude Code merges `enabledPlugins` when the same plugin is reachable through two marketplaces.
2. Whether VS Code rewrites its `settings.json` often enough to make the drift guard noisy. If it does, VS Code falls back
   to base-only settings, with machine-specific values applied through a VS Code profile.
3. `claude --settings` layering semantics. The 2026-10-29 model-router spike
   (`docs/plans/2026-10/2026-10-29-model-router-design.md`, "Spike results") answered one part: hooks supplied through
   `claude -p ... --settings` run (its `PreToolUse`/`PostToolUse` hooks fired, and the `PreToolUse` input rewrite took
   effect). Still open: whether a project's `.claude/settings.json` hooks run alongside `--settings` hooks, and which
   value wins when both set the same `env` key; Phase B step B5.3 probes those two points. The design does not depend
   on them; they are recorded for completeness.

## Out of Scope

- NAS / home-lab rebuild (separate project).
- The employer-specific port map, overlay contents, and the Phase C/D plan (work repository).
- Linux dev-environment support. The base targets macOS, and the engine should not preclude Linux later.
