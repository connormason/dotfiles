---
name: context-audit
description: >-
  Analyze project context files for redundancy across .ctx/, CLAUDE.md, and .claude/rules/.
  Detects duplicated content, role violations, and missing cross-references between context layers.
  Use when context files feel bloated, after regenerating .ctx/ files, when adding new rules files,
  or when you want to understand what's duplicated across context sources.
  Triggers on: "audit context", "check for context redundancy", "context files overlap",
  "what's duplicated in my rules", "analyze my CLAUDE.md", "context audit".
---

# Context Audit

Analyze all context sources in the current project for redundancy, role violations, and missing cross-references.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Context Layer Roles](#context-layer-roles)
- [Discovery](#discovery)
  - [Step 1: Discover context sources](#step-1-discover-context-sources)
  - [Step 2: Extract topics from each source](#step-2-extract-topics-from-each-source)
  - [Step 3: Cross-compare for redundancy](#step-3-cross-compare-for-redundancy)
- [Analysis Steps](#analysis-steps)
- [Detection Categories](#detection-categories)
  - [1. Full Duplicates](#1-full-duplicates)
  - [2. Partial Overlaps](#2-partial-overlaps)
  - [3. Cross-Rule Redundancy](#3-cross-rule-redundancy)
  - [4. Role Violations](#4-role-violations)
  - [5. Missing Cross-References](#5-missing-cross-references)
- [Report Format](#report-format)

<!-- mdformat-toc end -->

## Context Layer Roles<a name="context-layer-roles"></a>

These roles are the foundation of every audit finding. Content in the wrong layer wastes context window tokens.

| Layer                 | Role                                            | Loading                                            | Implication                                                                |
| --------------------- | ----------------------------------------------- | -------------------------------------------------- | -------------------------------------------------------------------------- |
| **CLAUDE.md**         | Workflow orchestration, compact quick-reference | Always loaded (system prompt)                      | Every line costs tokens on every turn — minimize size                      |
| **`.claude/rules/`**  | Authoritative detailed code patterns            | Auto-loaded contextually via `globs:` front matter | Only loaded when working on matching files — OK to be detailed             |
| **`.ctx/`**           | Broad overview and symbol discovery             | Read on demand (never auto-loaded)                 | Only read when explicitly needed — good for reference, bad for duplication |
| **CLAUDE-LESSONS.md** | Corrections and behavioral rules                | Loaded as memory file                              | Distinct from patterns — should not duplicate rules content                |

## Discovery<a name="discovery"></a>

Find all context sources in the project. Use Glob and Read to check for each — skip any that don't exist.

### Step 1: Discover context sources<a name="step-1-discover-context-sources"></a>

Check for these files/directories (all paths relative to project root):

1. **`.ctx/` files** — Glob for `.ctx/*.md`. For MAP.md specifically, read only the first 30 lines (header/stats). Read
   all other `.ctx/*.md` files fully.
2. **`CLAUDE.md`** — Read the project root CLAUDE.md if it exists.
3. **`.claude/rules/*.md`** — Glob for all markdown files in `.claude/rules/`. Read each fully. Note the `globs:` front
   matter in each — this tells you when the rule auto-loads.
4. **`CLAUDE-LESSONS.md`** — Read if it exists at the project root.

Record which sources were found. If fewer than 2 sources exist, report "insufficient context sources for cross-layer
audit" and stop.

### Step 2: Extract topics from each source<a name="step-2-extract-topics-from-each-source"></a>

For each file read, extract:

- **Section headings** (h2 and h3 level)
- **Code blocks** (count, language, and first line of each)
- **Key topics** covered (e.g., "build commands", "optional dependencies", "docstring style")
- **Approximate line count** per section

### Step 3: Cross-compare for redundancy<a name="step-3-cross-compare-for-redundancy"></a>

Compare every pair of sources. For each potential match, classify into one of 5 categories.

## Analysis Steps<a name="analysis-steps"></a>

Follow this procedure to systematically identify redundancy:

1. **Build a topic inventory.** For each source file, list every distinct topic it covers (e.g., "build commands",
   "optional dependencies pattern", "docstring style", "CI/CD pipeline"). Use section headings as the primary signal.

2. **Find topic overlaps.** For each topic that appears in 2+ sources, note which files cover it and at what detail
   level (one-line mention, paragraph summary, or full code example).

3. **Compare overlapping content.** For each overlap, read both sections side-by-side and classify the relationship:

   - Same content, same detail → Full Duplicate
   - Same topic, different detail → Partial Overlap
   - Same code block in 2+ rules files → Cross-Rule Redundancy
   - Content in wrong layer for its detail level → Role Violation
   - Duplicate with no pointer to the authority → Missing Cross-Reference

4. **Score confidence.** For each finding, assess how certain the classification is. Exact text matches are high
   confidence. Topical similarity with different framing is lower confidence.

5. **Compile the report.** Group findings by category and format per the Report Format template below.

## Detection Categories<a name="detection-categories"></a>

### 1. Full Duplicates<a name="1-full-duplicates"></a>

Same information appears in multiple places with no meaningful difference.

**Detection:** Two sections cover the same topic with the same level of detail, same examples, or same lists.

**Examples:**

- A package-by-package feature list in both `.ctx/ARCHITECTURE.md` and `.claude/rules/project-structure.md`
- Build commands listed in both CLAUDE.md and `.ctx/BUILD.md`
- CI/CD pipeline info repeated across CLAUDE.md, `.ctx/BUILD.md`, and `.claude/rules/build-and-ci.md`

**Recommendation:** Remove from the lower-priority layer. Priority order: rules (keep) > `.ctx/` > CLAUDE.md (for
detailed content). For workflow/command content: CLAUDE.md (keep compact version) > `.ctx/BUILD.md` (keep full version)
\> rules.

### 2. Partial Overlaps<a name="2-partial-overlaps"></a>

Similar content at different detail levels across layers.

**Detection:** Both sources cover the same topic, but one is a brief summary and the other has full examples/code.

**Examples:**

- CLAUDE.md has a 6-line quality standards section; CONVENTIONS.md has the same info plus ruff rule sets
- `.ctx/CONVENTIONS.md` has a code example for a pattern; `.claude/rules/python-style.md` has the same example with more
  context around it

**Recommendation:** Keep the detailed version in its appropriate layer. Condense the brief version to a one-liner with a
pointer.

### 3. Cross-Rule Redundancy<a name="3-cross-rule-redundancy"></a>

The same pattern or code example appears in multiple `.claude/rules/` files.

**Detection:** A code block, pattern description, or configuration example appears in 2+ rules files.

**Examples:**

- The optional dependencies `try/except` pattern in project-structure.md, python-style.md, AND conventions.md
- Import ordering rules described in both python-style.md and a separate imports rule file

**Recommendation:** Keep in the most specific/authoritative rules file. Remove from others with a cross-reference if
needed.

### 4. Role Violations<a name="4-role-violations"></a>

Content that belongs in a different layer based on its detail level and loading behavior.

**Detection heuristics:**

- A `.ctx/` file contains a fenced code block longer than **15 lines** → belongs in `.claude/rules/`
- A `.ctx/` file replicates content found **verbatim** in a `.claude/rules/` file → remove from `.ctx/`
- A `.claude/rules/` file contains only overview content with no actionable patterns → belongs in `.ctx/` or CLAUDE.md
- CLAUDE.md contains detailed code examples or long reference lists → belongs in `.ctx/` or rules

**Recommendation:** Relocate content to the correct layer, or condense and add a pointer.

### 5. Missing Cross-References<a name="5-missing-cross-references"></a>

A layer duplicates content that could be replaced with a pointer to the authoritative source.

**Detection:** Content exists in a non-authoritative layer AND the authoritative source exists, but there is no
cross-reference pointing to it.

**Recommendation:** Add a cross-reference in the format:

- In CLAUDE.md: `See .ctx/BUILD.md for full reference.`
- In CLAUDE.md or `.ctx/`: `See .claude/rules/python-style.md for details.`
- **Never add cross-references to `.ctx/` files** — they are regenerated and edits will be lost.

## Report Format<a name="report-format"></a>

After analysis, print a structured report to the console:

```
## Context Audit Report

### Sources Scanned
  - .ctx/: ARCHITECTURE.md, BUILD.md, CONVENTIONS.md, MAP.md (header)
  - CLAUDE.md (N lines)
  - .claude/rules/: python-style.md, testing.md, build-and-ci.md, ... (M files)
  - CLAUDE-LESSONS.md (present/absent)

### Full Duplicates (N found)
  1. [Topic]: [file_a]:[lines] ↔ [file_b]:[lines]
     → [recommendation]

### Partial Overlaps (N found)
  1. [Topic]: [file_a]:[lines] (brief) ↔ [file_b]:[lines] (detailed)
     → [recommendation]

### Cross-Rule Redundancy (N found)
  1. [Pattern]: appears in [file_a], [file_b], [file_c]
     → Keep in [authoritative_file], remove from others

### Role Violations (N found)
  1. [file]:[lines] — [violation description]
     → [recommendation]

### Missing Cross-References (N found)
  1. [file]:[lines] duplicates [authoritative_file]:[lines] with no pointer
     → Add cross-reference or condense

### Summary
  - N findings across M categories
  - Estimated ~X lines removable from always/auto-loaded context
  - Files with most redundancy: [list top 3]
```

If no findings in a category, omit that section entirely.
