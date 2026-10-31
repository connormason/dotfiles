# Phase B findings: first real run on the personal MacBook

Date: 2026-10-31. Runbook: `docs/plans/2026-10/2026-10-27-dev-env-port-plan.md` (Phase B). Spec:
`docs/plans/2026-10/2026-10-26-dev-env-base-overlay-design.md`.

## Outcome

`bootstrap/bootstrap.sh --resume --verify` finished every stage and `run.py doctor` reported all five checks green
(tools, layers, git, links, render). Reaching that took ten driver invocations (logs under
`~/.local/state/dotfiles-bootstrap/`); most stopped at `50-brew`, for the reasons below. The
`last-completed-stage` marker is deleted on a fully successful run (`bootstrap/bootstrap.sh:305`), so its absence
mid-session only reflected the failed runs.

## Failures found, in the order they appeared

| #  | Stage       | Symptom                                                                                          | Cause                                                                      | Resolution                                                                           |
| -- | ----------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 1  | `50-brew`   | `Refusing to load formula adembc/tap/lazyssh from untrusted tap`                                 | Homebrew 7+ refuses formulae from non-official taps unless trusted         | `trusted: true` on the three third-party formulae (PR #28)                           |
| 2  | `50-brew`   | `Your Command Line Tools are too outdated`                                                       | Xcode CLT older than the macOS release requires                            | Resolved outside the repo (later runs passed); no repo change                        |
| 3  | `50-brew`   | `Cask 'macdown' has been disabled ... Gatekeeper` (disabled upstream 2026-09-01)                 | Upstream cask removal                                                      | Entry dropped from `profiles/personal-mac/bootstrap/Brewfile` (PR #28)               |
| 4  | verify      | `render refused to overwrite in-app edits`                                                       | Live Claude settings differed from the rendered fragments (drift guard)    | PR #28 added `profiles/personal-mac/render/claude.json` content; later runs rendered clean |
| 5  | `50-brew`   | `mas`: `Failed to install app for ADAM ID 409907375`, `ISErrorDomain Code=4`                     | Apple Remote Desktop `mas` install failed once; it succeeded on a later run | Transient; no repo change (Q3 below)                                                 |
| 6  | `50-brew`   | `claude-code: It seems there is already a Binary at '/opt/homebrew/bin/claude'`                  | An npm global install of `@anthropic-ai/claude-code` owned that symlink    | `npm uninstall -g` plus removal of the stale native install; the cask is now the one |
| 7  | `60-macos`  | `Could not write domain ... com.apple.mail` (non-fatal)                                          | macOS privacy protection (TCC) denies the terminal access to the container | Left best-effort; comment in `60-macos.sh` corrected                                 |

Row 7 detail: `ls ~/Library/Containers/com.apple.mail` answers `Permission denied: code 13`. The container exists; the
terminal lacks Full Disk Access. The earlier comment attributed the failure to a missing container.

## Defects in the tooling

- **`run.py` `shell_command` ignored `timeout` while streaming.** In the pty path the read loop blocked on `os.read`, so
  the timeout only applied after the child had already closed its output: `sleep 3` with `timeout=0.3` ran 3.01 s and
  returned 0. The loop now polls with `select` against a deadline. A `return` inside the `finally` block (a
  `SyntaxWarning` on every `run.py` invocation under Python 3.14+) was removed, so an exception in flight is no longer
  replaceable by the cleanup path. The loop also treats Linux's `EIO` at pty close as end of output (macOS returns
  empty bytes). Regression tests: `tests/unit/test_run_shell_command.py`.
- **Runbook path.** The runbook and several plans assume a clone at `~/dotfiles-personal`. The name is a convention
  only: this Mac's checkout is `~/dotfiles`, and every command works from whichever checkout root is current.

## Open owner questions: answers

- **Q1 (old Ansible-era checkout):** none existed on this Mac. Bootstrap ran fresh from `~/dotfiles`.
- **Q3 (paid `mas` entry in the base Brewfile):** stays in `bootstrap/Brewfile`. It installed on this Mac after one
  transient failure (row 5).
- **Q4 (apps installed by hand):** adopted by `brew bundle`; the only entries that needed repo changes were the ones in
  PR #28 (rows 1, 3).
- **Q8 (`defaults export` safety copy):** none was taken. Preference changes from `60-macos` and `96-iterm2` still have
  no automatic restore point. Decision: add a scripted `defaults export` of the domains `60-macos` writes, with a
  matching restore path. Built afterwards as stage `58-defaults-backup` plus `bootstrap/defaults-restore.sh`; it covers
  the domains of both `60-macos` and `96-iterm2` (see `bootstrap/README.md`, "Undoing preference changes").
- **Q9 (how Claude Code is installed):** an npm global install plus a stale native install (2.0.67) both existed. The
  `claude-code` cask stays in `personal-mac` and is the only install.

## Verification results (B4)

| Check                                                      | Result                                                                                         |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Warm `zsh -i -c exit` time                                 | 0.089 s (budget 300 ms)                                                                        |
| Git identity inside the checkout                           | `file:~/.config/git/identity-personal`                                                         |
| ssh `Include` for `nas`                                    | `Reading configuration data ~/.ssh/config.d/personal` and `Applying options for nas` both print |
| `which -a claude`                                          | single path, `/opt/homebrew/bin/claude` (cask 2.1.309)                                         |
| Interactive shell startup output (expects 0 bytes)         | **Inconsistent:** one run printed 109 bytes, an immediate repeat printed none                  |

The 109-byte case was not captured. Next step: run `zsh -i -c exit 2>&1 | cat -v` in several fresh terminals,
including right after a reboot, and record what prints.

## Still open (Phase B, B5)

1. Install the wanted public plugin marketplaces and plugins in Claude Code, then run `python3 run.py render --diff
   claude` and move `enabledPlugins` / `extraKnownMarketplaces` into `profiles/personal-mac/render/claude.json`
   (spec Clarification 1).
2. Use VS Code for a few days with `python3 run.py render --check vscode` daily; record whether VS Code rewrites its
   settings (Clarification 2).
3. ~~Probe `--settings` layering as written in B5.3 (Clarification 3).~~ Done; see "B5.3 results" below.
4. Reproduce and root-cause the intermittent 109-byte startup output.
5. ~~Scripted `defaults export` backup for `60-macos` (Q8).~~ Done: stage `58-defaults-backup`.

## B5.3 results: `--settings` layering

Run on 2026-10-31 in a terminal outside Claude Code (Claude Code 2.1.309): a project `.claude/settings.json` with
`env.LAYER_PROJ=project` and a `SessionStart` hook, plus `overlay.json` with `env.LAYER_OVERLAY=overlay`,
`env.LAYER_PROJ=overlay` and its own `SessionStart` hook, via `claude -p "Reply OK" --settings overlay.json`.
`out.txt` afterwards:

```text
project-hook
overlay-hook
LAYER_OVERLAY=overlay
LAYER_PROJ=overlay
```

- **Hooks:** both the project hook and the `--settings` hook ran, so hooks from the two sources add.
- **`env`:** the `--settings` value won for the shared key (`LAYER_PROJ=overlay`), and the key set only by the overlay
  was present. This is what the hook process saw; the probe did not check the environment of the session's tools.
- **Design impact:** none; the spec's Clarification 3 is closed.

Phases C and D are planned in the work repository.
