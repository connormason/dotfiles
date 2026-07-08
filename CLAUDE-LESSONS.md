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
