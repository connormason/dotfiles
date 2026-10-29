# Hardening follow-up plan (post PR #18)

Fixes deferred from the final whole-branch review of PR #18 (`db876e5^1..db876e5`). No new features.

## Global Constraints

- Branch from `origin/main`; work only inside the worktree `.claude/worktrees/hardening-followup`.
- Every uv call goes through `scripts/hooks/uv-public.sh`. Never run `ruff format` (`ruff check --fix` is fine).
- Public repo: nothing employer-specific (names, hosts, tools, people's handles). Private patterns live at
  `~/.config/dotfiles/leak-patterns.txt`; run the leak guard and prek before every commit.
- Never run stow, render, bootstrap or `doctor --fix` against the real HOME; use the temp-HOME harness only.
- Python style: `.claude/rules/python-style.md` (single quotes, one import per line, sphinx docstrings, 120 cols, no
  blank line after a class docstring, multi-line test docstrings with `-> None`).
- `git add` new files before running the full suite (`tests/unit/test_stow_tree.py` rejects untracked files).
- Never push the local `archive/*` tags.

## Task 1: Pre-push scan hardening (`scripts/hooks/check-leaks-push.sh`)

Requirements:

1. Strip NUL bytes from the patch that is scanned (`tr -d '\000'`). Do **not** use `git log -z`. A NUL byte currently
   switches off the whole scan, including the appended path listing.
1. Run the path listing with `git -c core.quotePath=false log --name-only ...` so non-ASCII paths are not emitted as
   quoted octal escapes.
1. Widen the awk added-line prefix from `^[ +]?\+` to `^[ +]*\+` so octopus merges (N parents, N prefix columns) are
   seen.
1. Wrap every line over 120 columns in the script (lines ~11 and ~46 at the time of the review).
1. Update the inspect hints and the header comment so they match the commands actually run (including
   `--no-textconv`, `core.quotePath=false`, and the path-section line-number offset).
1. Tests in `tests/unit/test_check_leaks_push.py` (TDD; each new test must fail before the fix):
   - a merge-introduced path-only leak (file whose only leaky element is its path, introduced by a merge) is caught;
   - a patch containing a NUL byte still reports a leak elsewhere in the range (scan not switched off);
   - a non-ASCII path containing a leak pattern is caught (quotePath);
   - an octopus merge introducing an added leaky line is caught;
   - the `repo` fixture isolates global git config (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`) so a
     developer's `diff.renames` etc. cannot change results.

## Task 2: NAS bootstrap hygiene (`nas_bootstrap.sh`, `roles/requirements.yml`)

1. Correct the text at `nas_bootstrap.sh:54` to name `nas_bootstrap.sh` (the file that defines `EXPECTED_CHECKSUM`).
1. `nas_bootstrap.sh:33` downloads the Homebrew installer to the predictable `/tmp/brew-install.sh`; use `mktemp` with
   an EXIT-trap cleanup, matching `bootstrap/50-brew.sh`. The checksum is still verified before execution and a
   mismatch still aborts. Do not change anything else in the flow.
1. `roles/requirements.yml`: list the collections the roles actually use (`community.docker`, used in
   `roles/docker/tasks/main.yml`; `community.crypto`, used in `roles/ssh/tasks/main.yml`; confirm both with grep) and
   drop `ansible.posix` only if grep proves nothing under `roles/` or `playbooks/` uses it. Check how the file is
   consumed (`grep -rn requirements.yml`) so the change cannot break the NAS bootstrap.
1. Verify with `bash -n nas_bootstrap.sh`, `shellcheck` if available, and the existing test suite.

## Task 3: Documentation corrections

1. `scripts/hooks/README.md`: lines ~72-75 claim the repo has no `keybindings.json` (it now has
   `stow/vscode/Library/Application Support/Code/User/keybindings.json`); lines ~119-125 and ~147-152 document a
   `sort-json-array` hook that is **not** wired in `.pre-commit-config.yaml`; the `check-json5` `files:` snippet at
   ~88-92 is stale versus `.pre-commit-config.yaml:262`. Make the README match reality. Do NOT wire any new hook.
1. `stow/README.md` (git row) and the design doc `docs/plans/2026-10/2026-10-26-dev-env-base-overlay-design.md:49`:
   the per-remote `includeIf "hasconfig:remote.*.url:..."` identity switch needs a remote and is case-sensitive; a repo
   with no remote yet, an owner in another letter case, an SSH host alias or an explicit port falls back to the
   overlay's default identity. State this limitation (suggest: set `user.email` locally or add the remote before the
   first commit) and soften the "prevents work-email commits" wording. Facts only; verify against
   `stow/git/.gitconfig` before writing.
1. `README.md` quick start (~60-62 and the tree at ~238): the clone URL and directory name say `dotfiles-personal`; the
   GitHub repo is `connormason/dotfiles` (`git remote -v`). Align the URL (`git@github.com:connormason/dotfiles.git`)
   and the `cd` target. Check other docs for the same stale clone instructions.
1. `profiles/personal-mac/README.md`: the overlay registration command fails when `~/.config/dotfiles/` is absent;
   prefix with `mkdir -p`, honouring the same location logic as `bootstrap/lib.sh` (read lines ~104-106 first and
   mirror the `XDG_CONFIG_HOME` / `DOTFILES_OVERLAYS_FILE` behaviour in the documented command if it stays short).
1. Format changed markdown with `prek run mdformat --files <files>` (`docs/plans/` and `.ctx/` are excluded).

## Task 4: Bootstrap hardening and tests

1. `bootstrap/bootstrap.sh:~114-121`: `--only ""` / `--from ""` currently mean "no filter" (an empty shell variable
   would run every stage incl. sudo/brew/defaults), and a trailing `--only` / `--from` with no value exits silently
   under `set -e`. Make both `die` with a clear message. TDD in the existing driver tests
   (`tests/unit/test_bootstrap_driver.py`; hermetic temp HOME, never the real HOME).
1. Add a unit test for the Homebrew installer checksum gate in `bootstrap/50-brew.sh:~34-46` using a stub `curl`
   (and `shasum` only if necessary) on PATH inside a temp HOME: a matching checksum reaches the (stubbed) installer;
   a mismatch exits non-zero, never executes the downloaded file, and removes the temp file.
1. Add a one-line consistency test asserting the SHA-256 pinned in `nas_bootstrap.sh` (`EXPECTED_CHECKSUM`) equals the
   one in `bootstrap/50-brew.sh` (`BREW_INSTALLER_SHA256`). Run it after Task 2 (which must not change the hash).

## Task 5: Identity-limit wording follow-ups (from the Task 3 review)

1. `stow/git/.gitconfig:~56`: the comment still says personal remotes "always use the personal identity". Replace it with
   wording that matches the documented limits (remotes matching these globs use the personal identity; see
   `stow/README.md`, Git identity section). Comment-only change: no behaviour change; verify with the existing git tests.
1. `stow/README.md` Git identity section (~519-520) and the design-doc Limits paragraph
   (`docs/plans/2026-10/2026-10-26-dev-env-base-overlay-design.md`): the advice says to set `user.email` locally; say
   `user.name` and `user.email` (user.name otherwise still comes from the overlay default or personal config).
1. Format changed markdown with `prek run mdformat --files <files>`; run `prek run --files <changed files>`.
