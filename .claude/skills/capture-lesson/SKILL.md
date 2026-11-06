---
name: capture-lesson
description: Append a lesson to CLAUDE-LESSONS.md in the required Context / Mistake / Rule format, after checking for an existing lesson on the same topic. Use when a mistake, correction, or surprising failure should be recorded to prevent recurrence.
disable-model-invocation: true
argument-hint: [short description of the lesson]
---

# Capture Lesson

Records one lesson in [`CLAUDE-LESSONS.md`](../../../CLAUDE-LESSONS.md), the repository's log of mistakes and the rules
that prevent them. `$ARGUMENTS` is a short description; when empty, derive the lesson from the current conversation
(what went wrong, how it was caught, what the fix revealed).

## Format

Every entry under `## Lessons` follows this shape (copy the heading style of the existing entries):

```markdown
### <Imperative or declarative title stating the rule's subject>

- **Context**: What was happening, naming the concrete files, commands, or PRs involved.
- **Mistake**: What went wrong and why it was not obvious, including any misleading signal (a passing test, a clean
  dry run).
- **Rule**: The rule that prevents recurrence, phrased so a future session can apply it without the backstory.
```

Bullets wrap at 120 columns, with continuation lines indented two spaces under the bullet text.

## Procedure

1. **Read `CLAUDE-LESSONS.md` in full.** If an existing lesson already covers the topic, extend that entry (a sharper
   Rule, an extra Context line) rather than adding a near-duplicate, and say so.
2. **Check that it belongs here.** A lesson is a transferable rule learned from a mistake. Do not record a one-off bug
   fix (the commit message holds that), a task status, or anything already stated in `CLAUDE.md`, `.ctx/`, or
   `.claude/rules/`. If it fails this test, say why and stop.
3. **Draft the entry** from verified facts only: cite real paths, commands, and PR numbers from the conversation or
   `git log`, never reconstructed from memory.
4. **Append it** at the end of the file, after the last lesson, separated by one blank line. Keep the file's existing
   order (chronological, newest last).
5. **Format**: run `uv run python run.py run-hooks --files CLAUDE-LESSONS.md` so `mdformat` normalises it, then confirm
   the diff touches only the new or extended entry.
6. **Report** the title of the entry and whether it was new or an extension. Do not commit unless asked.
