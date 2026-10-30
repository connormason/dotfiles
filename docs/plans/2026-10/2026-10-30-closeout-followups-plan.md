# Close-out follow-ups plan (post PR #19 / #22)

Four small items closing out the dotfiles overhaul before Phase B (personal MacBook runbook). No new features. Source of
the decisions: owner answers in the 2026-10-30 session; findings come from the PR #19 final review
(`bootstrap/60-macos.sh`, `sort-json-array`), a live check of the Homebrew installer pin, and a read-only Phase B
runbook review against main e76def5.

## Global Constraints

- Public repo: nothing employer-specific (names, hosts, tools, people's handles) in any file or commit message. The
  private leak patterns live at `~/.config/dotfiles/leak-patterns.txt` and are enforced by the leak guard in prek.
- Every `uv` call goes through `scripts/hooks/uv-public.sh`. Never run `ruff format`. No bare `python`/`python3`/`pip`.
  Use `$TMPDIR`, never `/tmp`, for scratch files.
- Never run stow, render, bootstrap (outside `--dry-run` in a temp HOME harness) or `doctor --fix` against the real HOME.
  The existing integration harness uses a throwaway HOME; use only that.
- Do not bypass hooks (`--no-verify`). `prek run --all-files` and the full test suite
  (`scripts/hooks/uv-public.sh run pytest -q`) must pass before each commit is considered done.
- Python style: single quotes, sphinx docstrings, `from __future__ import annotations`, one import per line, no blank
  line between a class docstring and its first member. Tests: multi-line docstrings, `-> None` on every test method.
- `docs/plans/` and `.ctx/` are excluded from mdformat (hand-maintained, 120-column wrap). Other Markdown is formatted by
  the `mdformat` prek hook; let the hook do it.
- Commits are conventional (`fix(...)`, `docs(...)`, `feat(...)`, `test(...)`), one logical change per commit, and each
  task ends with its own commit(s). Do not push.

## Task 1: `bootstrap/60-macos.sh` leftovers (three owner-approved edits)

Owner decisions (verbatim):

1. `bootstrap/60-macos.sh:19`: the `osascript` line quits `"System Preferences"` under the comment `# Close System
   Settings so it does not override changes.` Change the quoted application name to `"System Settings"` (keep the
   `|| true` guard and the comment).
2. `bootstrap/60-macos.sh:89-91`: comment `# Show recently used apps in a separate section of the Dock` sits over
   `defaults write com.apple.dock show-recents -bool false`. **Flip the value to `-bool true`** (a behaviour change the
   owner approved); the comment stays as is.
3. `bootstrap/60-macos.sh:190-191`: comment `# Enable spring loading for directories and disable delay` with only
   `com.apple.springing.enabled` set. Reword the comment to drop "and disable delay" (e.g. `# Enable spring loading for
   directories`). Do **not** add a delay key.

Steps: make the three edits; grep the repo (excluding `archive/`) for any other mention of these values (docs, tests,
README tables, `.ctx`) and update the ones that state them (for example a README table that lists `show-recents` or the
osascript target); run the shell tests that cover 60-macos (`tests/unit/test_bootstrap_stages.py` and
`tests/unit/test_bootstrap_driver.py`, plus whatever `grep -rl 60-macos tests` finds); commit as
`fix(bootstrap): align 60-macos osascript, show-recents and spring-loading with their comments`.

## Task 2: Wire `scripts/hooks/sort-json-array.py` for the VS Code `keybindings.json`

Owner decision: wire the hook for the tracked `stow/vscode/Library/Application Support/Code/User/keybindings.json`
(the only `keybindings.json` in the repo; it is currently already sorted by `command`, so the first run must be a
no-op).

1. Add a `local` hook `sort-json-array` to `.pre-commit-config.yaml` in the formatter section (priority 35, label
   `[format] json array sort (keybindings)` in the style of its neighbours), `entry: scripts/hooks/sort-json-array.py`,
   `language: python`, `args: [--key, command]`, and a `files:` regex that matches exactly that one tracked path (anchor
   it; do not use a bare `.*keybindings\.json$`). Choose `stages` by the nearest precedent for a formatter that rewrites
   files (`keep-sorted`, `pretty-format-json`, `format-pkl` use `[pre-commit]`, skipped in CI) and say why in a one-line
   comment. Update the "Formatters/fixers" priority table comment at the top of that section.
2. Verify the hook is a no-op on the real file (`scripts/hooks/uv-public.sh run scripts/hooks/sort-json-array.py -v
   <file>` leaves `git status` clean) and does not fight the other JSON hooks (`check json syntax`, `pretty-format-json`,
   gitleaks allowlist) on that file: run `prek run --all-files` and confirm a second run changes nothing.
3. Add a small unit test module `tests/unit/test_sort_json_array.py` covering: unsorted input is rewritten and the
   exit code is 1; sorted input is untouched and the exit code is 0; entries missing the key sort first and equal keys
   keep their order (stable); non-array / non-object / invalid JSON returns 1 without modifying the file; the tracked
   `keybindings.json` is already sorted (exit 0, bytes unchanged); and that `.pre-commit-config.yaml` has a
   `sort-json-array` hook whose `files` pattern matches the tracked path and does not match an unrelated `settings.json`.
   Load the script via `importlib` from `scripts/hooks/sort-json-array.py` (hyphenated name) the way other hook tests in
   `tests/unit/` do; mirror their layout.
4. Docs: in `scripts/hooks/README.md` change every "not wired" statement (intro paragraph, Scripts table row incl. hook
   id and priority, the NOTE block, the priority-bands note and "has no hook entry" sentence, the `sort-json-array.py`
   "Pre-Commit Integration" section) to describe the wired hook with the real YAML entry copied from
   `.pre-commit-config.yaml`; add a caveat that VS Code evaluates keybindings in file order and a later entry wins when
   two entries share a key and `when`, so sorting by `command` can change precedence for such conflicting pairs (none
   exist today; verify by checking the file for duplicate `key`+`when` pairs and say so). Check `docs/` and the
   repo-level README for other statements and fix them. Run the docs-consistency test.
5. Commit as `feat(hooks): wire sort-json-array for the VS Code keybindings.json` (script already existed; wiring plus
   tests plus docs may be split into two commits).

## Task 3: Re-pin the Homebrew installer (hash and URL)

Facts established by the controller: `https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh` hashes to
`5f333bbe53bc490e51e7ccb1df8779b3dd6ee73a1a7379efda216edb08ccb148` (upstream commit
`09c62fc577ec170172b0a184060f141a2c622dc1`, 2026-10-01). The currently pinned digest `b2ffbf7e...d3bc` matches none of
the last 30 upstream versions of `install.sh` (back to 2025-06), so the old pin hard-fails stage 50 and the NAS bootstrap
on a fresh machine. Owner decision: bump the hash AND pin the URL to the commit so the pin cannot drift when upstream
edits `HEAD`.

1. Re-verify independently before editing: fetch
   `https://raw.githubusercontent.com/Homebrew/install/09c62fc577ec170172b0a184060f141a2c622dc1/install.sh` into a fresh
   directory under `$TMPDIR`, `shasum -a 256` it, and confirm it equals the digest above. If it does not, STOP and report
   BLOCKED with the observed digest. Do not execute the downloaded file.
2. In `bootstrap/50-brew.sh` set `BREW_INSTALLER_URL` to the commit-pinned URL and `BREW_INSTALLER_SHA256` to the new
   digest (keep the `# pragma: allowlist secret` marker); update the "Last updated" date to 2026-10-30 and the "to
   update" instructions in the adjacent comment so they say to pick a commit SHA from the upstream history of
   `install.sh`, put it in the URL, and take the `shasum -a 256` of that exact URL.
3. In `nas_bootstrap.sh` do the same for its installer URL (line ~35) and `EXPECTED_CHECKSUM` (line ~40), including its
   "to update" comment (line ~38), keeping the file name it tells the operator to edit correct (`nas_bootstrap.sh`).
4. Update README text that describes the pin or the checksum-mismatch recovery (`README.md` "Homebrew Checksum
   Mismatch", `playbooks/README.md`, `bootstrap/README.md`, `.ctx/` if mentioned) so it matches the commit-pinned flow.
5. Extend the existing consistency test (`tests/unit/test_brew_stage.py` / `tests/unit/test_nas_bootstrap.py`, wherever
   the two-digest equality assertion lives) so it also asserts that the two scripts use the identical installer URL, that
   the URL contains a 40-hex commit SHA (not `HEAD`), and that the digest is 64 hex characters. Keep the existing
   behaviour tests for the checksum gate passing (they stub `curl`; adjust only if they hard-code the old URL).
6. Run the two test modules, then the full suite and `prek run --all-files`. Commit as `fix(bootstrap): re-pin the
   Homebrew installer to a commit-pinned URL and current SHA-256`.

## Task 4: Phase B runbook: apply the no-input fixes from the dry review

Scope is exactly the items below (owner choice: "apply the no-input fixes"). Everything else in the review stays open
and must NOT be changed here: owner questions (old checkout location, canonical checkout path, remote-desktop `mas`
entry, adopt-vs-drop of hand-installed casks, leak-patterns on the personal Mac, router enforce timing, plugin config
stow decision, `defaults` export, Claude install method) and the items not listed below (render first-run drift
handling, router verification step, hook install step, iTerm2 note, cross-doc nits).

Files: `docs/plans/2026-10/2026-10-27-dev-env-port-plan.md` (Phase B section at the end), `profiles/personal-mac/README.md`,
`docs/plans/2026-10/2026-10-26-dev-env-base-overlay-design.md` (clarification 3). Evidence for each item must be
re-checked in the source before writing; do not copy claims from this plan unchecked.

1. **Stale references (F15):** the Phase B header says "after the Phase A PR merges"; the plan's header names the deleted
   `dev-env-base` branch; the last line says Phases C/D use "the staging directory as input" (the worktree and its
   `.superpowers/overlay-staging/` are gone; the private backup lives at `~/.config/dotfiles/overlay-staging-backup/` on
   the work Mac). Rewrite to: run on `main` at or after e76def5 (PRs #18, #19, #22 merged); Global Constraints apply to
   Phase A only; the Phase C input is the backed-up staging directory (private, work Mac only). Do not put anything
   employer-specific in the text.
2. **Spike result (F16):** `docs/plans/2026-10/2026-10-29-model-router-design.md` (~lines 134-137) records that hooks
   supplied through `claude -p ... --settings` ran. Update clarification 3 in the overlay design doc (~lines 248-249) to
   state exactly what that spike answered and what is still open (project hooks alongside `--settings` hooks; which
   `env` value wins), and say in B5.3 that the probe resolves only those two points.
3. **Overlay registration (F6):** B1 truncates the registry (`>`), ignores `XDG_CONFIG_HOME` / `DOTFILES_OVERLAYS_FILE`
   (`bootstrap/lib.sh` ~104-106), whereas `profiles/personal-mac/README.md` appends. Make both idempotent and consistent:
   `mkdir -p` the directory, append only if the line is absent (`grep -qxF`), honour the same resolution as `lib.sh`,
   and let the runbook point at the README snippet instead of duplicating it. Verify the snippet in a temp HOME (a
   shell one-liner is enough; `bootstrap.sh --list` or the `manifest_files` helper may be used under a temp HOME only).
4. **Homebrew pin (F8):** B1/B3 never mention the checksum gate. Add a short note: stage 50 verifies a commit-pinned
   installer against `BREW_INSTALLER_SHA256`; if Homebrew is absent and the gate fails, follow the README "Homebrew
   Checksum Mismatch" section and update both pins (`bootstrap/50-brew.sh`, `nas_bootstrap.sh`) in one commit (a test
   enforces equality), then `--resume`.
5. **Rollback block (F9):** add a "Rollback" subsection after B3 derived from the code, not from this plan: `stow.sh`
   backs up conflicts to `~/.dotfiles-backup/<YYYYmmdd-HHMMSS>/` and rejects `-D`/`--adopt`; `render.py` keeps its own
   timestamped backups and state under `~/.local/state/dotfiles/render/`; bootstrap state/log under
   `~/.local/state/dotfiles-bootstrap/`; `60-macos.sh` writes `defaults` with no automatic backup. Give the manual
   unlink command per layer (plain `stow -D` against each layer's `stow/` dir; verify the exact form against how
   `stow.sh` invokes stow), how to restore files from the backups, how to clear render state, and a line that preference
   changes have no automatic restore point (an optional `defaults export` is an owner decision, so only mention it as
   open question Q8, do not script it).
6. **B2 `find` (F18):** the command walks `~/Library` etc. and, run after B1, matches links inside the new checkout. Use a
   pruned form (`find ~ -maxdepth 4 \( -path ~/Library -o -path ~/dotfiles-personal \) -prune -o -type l -lname
   '*dotfiles*' -print`) and note that `stow.sh --backup-conflicts` already moves blocking links and files, so B2 only
   has to remove links that no package replaces. Check `stow.sh` before asserting that.
7. **Verification steps:** B4 `ssh -G nas | grep -i '^hostname'` cannot fail (F11): replace with a check that proves the
   `Include` (`ssh -v -G nas 2>&1 | grep -E 'config\.d/personal'` or the form you verify works under a temp HOME with the
   stowed config). F17: state one invocation form for `run.py` (the README / `docs/RUN_PY_REFERENCE.md` form, from the
   repo root) and use it throughout B3-B6. F20: replace "clean, fast" with `zsh -i -c exit 2>&1 | wc -c` printing 0 and
   `time zsh -i -c exit` under the startup budget that Task 7 of the same plan states (confirm the number in the plan).
   F21: `git config --show-origin user.email` inside the checkout should name the personal identity file. F24: `which -a
   claude` and `claude --version` (a native install in `~/.local/bin` can shadow the cask).
8. **Before-you-start checklist (blockers F1/F2/F3), no decisions taken:** add a short box at the top of Phase B listing
   the three blockers as items to resolve first, each pointing at the corresponding open owner question: (a) an
   Ansible-era checkout of this same repo likely exists on that Mac: locate it, `git status` it, and take a
   dereferenced backup (`cp -RL`/`rsync -aL`) before anything clones or pulls (B1/B2 never say where it is); (b)
   `brew bundle` aborts the whole stage on any failed entry (paid `mas` entries, hand-installed casks, no App Store
   sign-in): run `brew bundle check --verbose --file <each Brewfile>` first; (c) the dry run skips the stow backup
   preview when `stow` is not installed (`bootstrap/95-dotfiles.sh` ~19-24), so install it first and treat the preview
   as a hard checkpoint. Verify each against the source before writing; keep the wording factual.
9. Do not touch anything else in the plan. Do not answer the open questions. Run `prek run --all-files` and the
   docs-consistency test; commit as `docs(plans): refresh the Phase B runbook against merged main`.
