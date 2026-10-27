---
name: context-cleanup
description: >-
  Audit and clean up redundancy across .ctx/, CLAUDE.md, and .claude/rules/ context files.
  Runs a full context audit first, then makes direct edits to deduplicate content —
  with confirmation on ambiguous findings. Use after regenerating .ctx/ files, when context
  feels bloated, or when CLAUDE.md has grown too large.
  Triggers on: "clean up context", "deduplicate context files", "context cleanup",
  "reduce context redundancy", "slim down CLAUDE.md", "context files are too big".
---

# Context Cleanup

Audit all context sources for redundancy, then make direct edits to deduplicate — with confirmation on ambiguous
findings. This skill runs the full context-audit analysis first, then proceeds to edits.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Workflow](#workflow)
  - [Phase 1: Audit](#phase-1-audit)
  - [Phase 2: Classify findings by confidence](#phase-2-classify-findings-by-confidence)
  - [Phase 3: Apply edits](#phase-3-apply-edits)
  - [Edit Safety Rules](#edit-safety-rules)
  - [Role Violation Heuristic](#role-violation-heuristic)
  - [Confirmation UX](#confirmation-ux)
  - [Phase 4: Summary](#phase-4-summary)
- [Cross-Project Adaptability](#cross-project-adaptability)
- [Chaining after `.ctx/` regeneration](#chaining-after-ctx-regeneration)

<!-- mdformat-toc end -->

## Workflow<a name="workflow"></a>

### Phase 1: Audit<a name="phase-1-audit"></a>

Run the complete context-audit workflow as defined in the `context-audit` skill:

1. Discover all context sources (`.ctx/`, CLAUDE.md, `.claude/rules/`, CLAUDE-LESSONS.md)
2. Extract topics, code blocks, and key content from each source
3. Cross-compare for redundancy across all 5 detection categories
4. Produce the structured audit report

Print the audit report before proceeding to Phase 2.

### Phase 2: Classify findings by confidence<a name="phase-2-classify-findings-by-confidence"></a>

For each finding from the audit, assign a confidence level:

| Confidence           | Criteria                                                                                                                                                                                                               | Action                                                                                        |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **High (auto-fix)**  | Full duplicate: exact same content in two places. OR clear role violation: >15-line code block in `.ctx/` that exists verbatim in a rules file.                                                                        | Edit immediately without asking.                                                              |
| **Medium (confirm)** | Partial overlap: same topic at different detail levels. OR cross-rule redundancy where the "authoritative" file is ambiguous. OR missing cross-reference where it's unclear which direction to point.                  | Present the finding conversationally and ask "Apply this change? (yes / no / skip remaining)" |
| **Low (flag only)**  | Potential issue requiring human judgment. Content that *might* be redundant but serves a different purpose in each location. OR structural concerns (e.g., CLAUDE.md is too long but nothing is obviously duplicated). | Report the finding but do not edit.                                                           |

### Phase 3: Apply edits<a name="phase-3-apply-edits"></a>

Process findings in order: high-confidence first, then medium (with confirmation), then low (report only).

For each edit, use one of these operations:

#### Operation: Remove Duplicate

Delete the redundant copy entirely. If it was in CLAUDE.md or `.claude/rules/`, optionally add a one-line
cross-reference pointer to the authoritative source.

**When to use:** Full duplicates where the authoritative copy is clear.

**Example:**

- CLAUDE.md has a 40-line "Development Commands" section that duplicates `.ctx/BUILD.md`
- → Remove the 40 lines, replace with compact 6-line quick-reference + "See `.ctx/BUILD.md` for full reference."

#### Operation: Condense

Replace verbose content with a one-line summary that preserves the essence.

**When to use:** Partial overlaps where both copies have value but one is clearly the authority.

**Example (non-generated file):**

- CLAUDE.md has a 6-line "Quality Standards" bulleted list
- `.ctx/CONVENTIONS.md` and `.claude/rules/python-style.md` cover the same info in more detail
- → Replace the CLAUDE.md section with a single-line summary:
  `120-char line length | Python 3.9+ | 67%+ docstring coverage | mypy strict | pre-commit hooks enforced`

**Example (generated `.ctx/` file):**

- `.ctx/CONVENTIONS.md` has a 10-line code block for the optional dependencies pattern
- `.claude/rules/python-style.md` has the same block with additional context
- → Replace the `.ctx/` code block with a one-line summary:
  `**Optional Dependencies** — try/except (ImportError, ModuleNotFoundError) with FEATURE_SUPPORT flag`
- Do **not** add a cross-reference pointer to `.ctx/` files — they are regenerated and the pointer would be lost.

#### Operation: Relocate

Move content from the wrong layer to the correct layer.

**When to use:** Role violations where content is genuinely useful but lives in the wrong place.

**Example:**

- `.claude/rules/build-and-ci.md` contains a 30-line overview of the project's CI philosophy with no actionable patterns
  → Move to `.ctx/ARCHITECTURE.md` or CLAUDE.md as appropriate.

### Edit Safety Rules<a name="edit-safety-rules"></a>

1. **Never delete unique information.** If content exists in only one place, do not remove it — even if it seems like
   it's in the wrong layer. Flag it as a role violation for the user to decide.
2. **Only add cross-references to non-generated files** (CLAUDE.md, `.claude/rules/`). `.ctx/` files are regenerated by
   a `.ctx/` generator — hand-written cross-references will be overwritten.
3. **Respect managed section markers.** If a `.ctx/` file contains `<!-- ctx-managed-section-start/end -->` markers, do
   not edit content within those markers. When markers are absent, treat the entire file as editable.
4. **Preserve structure.** When removing content from a file, ensure the surrounding headings and sections still make
   sense. Don't leave orphaned headers or empty sections.

### Role Violation Heuristic<a name="role-violation-heuristic"></a>

Use these concrete thresholds when classifying role violations during Phase 2:

A `.ctx/` section is a **role violation** if:

- It contains a fenced code block longer than **15 lines**, OR
- It replicates content found **verbatim** (or near-verbatim) in a `.claude/rules/` file

A `.claude/rules/` section is a role violation if it contains only high-level overview content with **no actionable
patterns or code examples** — that content belongs in `.ctx/` or CLAUDE.md instead.

A CLAUDE.md section is a role violation if it contains **detailed reference content** (long command lists, full code
examples, configuration details) that belongs in `.ctx/` or rules.

### Confirmation UX<a name="confirmation-ux"></a>

For medium-confidence findings, present each as a conversational comparison:

```
Found partial overlap:

  Source A — .ctx/CONVENTIONS.md:40-48:
    [show the relevant content block]

  Source B — .claude/rules/python-style.md:149-156:
    [show the relevant content block]

  Recommendation: Condense Source A to a one-line summary (no cross-reference since .ctx/ is generated).

  Apply this change? (yes / no / skip remaining confirmations)
```

If the user says "skip remaining," apply all remaining medium-confidence recommendations automatically.

### Phase 4: Summary<a name="phase-4-summary"></a>

After all edits are applied, print a summary:

```
## Context Cleanup Summary

### Changes Made
  1. [file]: [operation] — [description] (N lines removed)
  2. ...

### Flagged (Not Edited)
  1. [file]:[lines] — [description] — [reason not edited]

### Stats
  - Files modified: N
  - Lines removed: N
  - Lines added: N (cross-references/pointers)
  - Net reduction: N lines from always/auto-loaded context
```

## Cross-Project Adaptability<a name="cross-project-adaptability"></a>

This skill discovers context sources dynamically — no hardcoded paths or project-specific assumptions.

| Sources Found                     | Behavior                                                  |
| --------------------------------- | --------------------------------------------------------- |
| Only `.ctx/`                      | Audit for internal `.ctx/` redundancy and role violations |
| Only CLAUDE.md + `.claude/rules/` | Audit CLAUDE.md ↔ rules overlap                           |
| All three layers                  | Full cross-layer audit                                    |
| No `.ctx/` directory              | Skip `.ctx/` analysis, audit CLAUDE.md ↔ rules only       |
| Fewer than 2 sources              | Report "insufficient sources" and stop                    |

## Chaining after `.ctx/` regeneration<a name="chaining-after-ctx-regeneration"></a>

After regenerating `.ctx/` files, invoke `/context-cleanup` to audit the fresh files against existing CLAUDE.md and
rules, then clean up any new redundancy introduced by the regeneration.
