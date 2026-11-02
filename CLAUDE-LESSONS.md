# Lessons Learned

Patterns and corrections captured during development to prevent repeated mistakes. Append new lessons here.

## Format

Each lesson follows this pattern:

- **Context**: What was happening
- **Mistake**: What went wrong
- **Rule**: The rule to prevent recurrence

---

## Lessons

### Keep this repo's Claude config self-contained — don't assume global `~/.claude` exists

- **Context**: Porting Claude Code infra from the work `~/dotfiles` repo into this personal repo. The work repo's
  `.claude/rules/*.md` are thin "deltas" that inherit a global baseline at `~/.claude/rules/`.
- **Mistake**: Wrote the personal repo's rule files the same way — as deltas that reference `~/.claude/rules/`. But this
  repo cannot guarantee the global `~/.claude` configuration is present (it is only reliably set up alongside the work
  dotfiles), so the "inherited" baseline could be missing entirely, leaving the rules referencing nothing.
- **Rule**: Everything under this repo's `.claude/` (and `.ctx/`, `CLAUDE.md`) must stand on its own. Rule files carry
  the full guidance rather than deferring to a global baseline; agents and skills reference only in-repo artifacts. If
  the global config is later guaranteed for personal use, rules may optionally be slimmed back to deltas.

### A dry run cannot see competing install channels — probe the real machine before declaring a cask

- **Context**: Phase B, first real bootstrap of the personal MacBook. `profiles/personal-mac/bootstrap/Brewfile`
  declared `cask "claude-code"`.
- **Mistake**: The dry run passed, but an npm global install already owned `/opt/homebrew/bin/claude` and a stale native
  install sat in `~/.local/bin`. The cask failed with "already a Binary" and stopped `50-brew`. The same run hit three
  other machine-state surprises a dry run cannot predict (untrusted taps, a disabled upstream cask, a TCC-protected app
  container).
- **Rule**: When a Brewfile entry names a tool with several install channels (npm, native installer, cask), check
  `which -a <tool>` and the other channels on the target machine before the first real run, and record which channel is
  authoritative. Treat the first real run on a new machine as an experiment: read every log, not just the final summary.

### A regression test must fail against the old code, and for the stated reason

- **Context**: Fixing `run.py` `shell_command` (`return` inside `finally`). The first draft test passed against the
  unfixed code.
- **Mistake**: That test asserted an exception propagated, but closing the pty master sends SIGHUP to the child, so the
  swallow path was effectively unreachable and the test passed for the wrong reason. Running the draft against the old
  code, plus a probe script, exposed the larger defect: the streaming path never enforced `timeout` at all.
- **Rule**: Run a new regression test against the unfixed code and confirm it fails with the expected message before
  writing the fix. For time-based behavior, assert on elapsed time, not only on the exception or return value.
