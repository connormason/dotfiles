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

### The edit-time ruff hook rewrites Python mid-refactor — add imports with their first use

- **Context**: Migrating `run.py` from the `@command` decorator to `Command` classes in several sequential edits. The
  project `PostToolUse` hook runs `ruff check --fix-only` on every edited `.py` file.
- **Mistake**: Added the new imports (`abc`, `enum`, `ClassVar`, `Sequence`, `traceback`) in their own edit ahead of the
  code using them; the hook deleted them as unused (F401). Worse, while `abc` was briefly missing, B027 stopped firing
  on the intentional no-op `Command.add_arguments`, so the hook also stripped its now-"unused" `# noqa: B027` (RUF100).
- **Rule**: In multi-step Python refactors, add an import in the same edit as (or after) its first use, and after any
  edit that leaves the file temporarily broken, re-check that `noqa` comments and imports survived before moving on.

### Hand-maintained inventories in docs drift: guard each with a test

- **Context**: READMEs and `.ctx/` files list stages, packages, roles, containers, and `run.py` commands.
  `tests/unit/test_docs_consistency.py` already cites this lesson in its docstring, but it was never written down.
- **Mistake**: After NAS sub-projects 1-3 the root README still listed retired roles, five registered commands were
  missing from the reference, and `--tags docker` was documented as the way to update the stack.
- **Rule**: When a doc enumerates something the code defines, add a parse-the-table test beside it (and a "parsed zero
  rows" companion). Add the guard in the same change that adds the inventory.

### String-matching Ansible YAML is not verification: run the role

- **Context**: NAS sub-project 3 added per-service secret rendering. Unit tests that read the role's YAML passed.
- **Mistake**: Two real bugs shipped past them: `lookup('fileglob', '.../*/env.j2')` matched nothing (so no secret was
  rendered) and a template used a variable another role defines.
- **Rule**: Exercise role tasks against localhost with `ansible-playbook` and assert on the result
  (`tests/unit/test_services_role.py`). Structural tests only pin wiring, never behavior.

### `--check --diff` of a template prints the old file

- **Context**: A secrets template whose target already holds secrets, run with `--check --diff`.
- **Mistake**: Check mode diffs the current file against the new one, so it prints the existing secret values.
- **Rule**: Set `diff: false` on any task whose target holds secrets, and `no_log` where values could print.

### A tag on `include_role` selects only the include

- **Context**: Every role include in the NAS play carried `configfile`, and `playbooks/README.md` said
  `--tags configfile` ran the whole stow engine.
- **Mistake**: Tasks inside an included role see only its `apply:` tags plus their own, so a tag nothing inside the role
  carries selects the include and nothing else. Only three tasks carried `configfile`.
- **Rule**: Every tag on an include must be the apply tag or be carried by a task in the role
  (`tests/unit/test_nas_playbook.py::TestPlaybookTags`). Prove tag semantics with a real run before documenting them.
