# CLAUDE.md

## Writing Style

- Write in clear, analytical prose with confident authority
- Use sophisticated vocabulary without jargon; explain complex topics concisely
- Employ dry wit and subtle irony where appropriate
- Favor active voice, strong verbs, and minimal adjectives
- Structure arguments logically; avoid first-person perspective
- Maintain objectivity while being decisive in analysis

## Behavioral Constraints

- CRITICAL: Do not cut corners or stop working on a task because of time complexity. Follow through with tasks and TODOs
  step by step without exception.
- When hooks inject skill recommendations (e.g., "PYTHON DETECTED", "ORCHESTRATION DETECTED"), follow the instructions
  immediately.

## Workflow Orchestration

### Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### Plan & Design Doc Storage

- Store all implementation plans and design docs in the project's `docs/plans/<YYYY-MM>/` directory, creating the
  monthly subdirectory (current month) if it does not exist yet.
- Naming: `YYYY-MM-DD-<topic>-design.md` for design/brainstorm docs, `YYYY-MM-DD-<topic>-plan.md` for implementation
  plans.
- This is the canonical location for planning artifacts; reference it when reviewing past design decisions.
- Applies to all projects unless a project's own CLAUDE.md overrides it.

### Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer

### Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs

## Critical Rules

### Tool Usage Enforcement

**NEVER** use bash commands that have Claude Code tool equivalents:

- `find` -> Use `Glob` tool with patterns like `**/*.py`
- `grep`, `rg` -> Use `Grep` tool with regex patterns
- `cat`, `head`, `tail` -> Use `Read` tool with file paths
- `sed` -> Use `Edit` tool for targeted replacements
- `cd` -> Use absolute paths in commands

These commands are not in the global allow list. Use `ls` for directory verification; use `Glob` for pattern-based file
discovery.

If a tool use for reading/writing files within the current project results in a PermissionRequest, attempt to determine
how that task could be done without requiring permission.

### Code Quality

- Docstrings on public functions following project style conventions (see `rules/python-style.md` for Python)
- Comments only when the WHY isn't obvious from the code
- Auto-fix all linting/formatting issues before completing work
- Generate unit tests for new code

If a `.pre-commit-config.yaml` is present in the project, always ensure pre-commit hooks are passing before completing
work.

### Python Development

- CRITICAL: Always use `uv` for installing Python packages and running ANY Python script/command. NEVER use bare
  `python`, `python3`, `pip`, or `hatch`.
- CRITICAL: NEVER run `ruff format` (or `uv run ruff format`) on any project — its changes (stripping manual column
  alignment, adding blank lines after class docstrings) are unwanted. `ruff check --fix` is fine and encouraged; only
  the formatter is banned. Never instruct subagents to run it or call it the "style authority"; match the surrounding
  hand-maintained style instead.
- No mutable default arguments (`def foo(x: list = [])` is blocked)
- No bare `Any` type without explanation
- Exception chaining required: use `raise NewError(...) from e` or `from None`
- See `rules/python-style.md` for type annotation, docstring, and formatting conventions

### Path Handling

All plan documents must use:

- Absolute paths starting with `/` or `~/`
- No relative paths like `./` or `../`
- This ensures portability across different execution contexts

CRITICAL: Use `$TMPDIR` when you need to write temporary files to disk, never `/tmp` directly.

### Git Worktree Default

For any task that is **not a quick fix** (estimated >5 minutes, multi-file changes, new features, refactors, or
architectural work), **default to creating a git worktree** using `EnterWorktree` before starting implementation. This
keeps the user's main workspace untouched so they can continue working independently.

- Use the `superpowers:using-git-worktrees` skill when available
- Name worktrees descriptively (e.g., the feature or issue number)
- Quick fixes (typos, single-line changes, small bug fixes) can stay in the current workspace
- When in doubt, use a worktree — the cost of isolation is low, the cost of polluting the workspace is high

### Git Commands

CRITICAL: Always use current working directory for git commands. e.g. `git status` (good), `git -C random/path` (bad)

### Security (Non-Negotiable Rules)

- **NEVER: Hardcode API keys, passwords, or secrets**
- **NEVER: Commit code with failing tests or linting errors**
- **NEVER: Push directly to main/master branch**
- **NEVER: Skip security reviews for authentication/authorization code**
