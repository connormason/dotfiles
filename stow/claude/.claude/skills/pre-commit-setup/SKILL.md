---
name: pre-commit-setup
description: Setup and configure git pre-commit hooks using pre-commit or prek. Use when users ask to add pre-commit hooks to a project, configure hook settings, add new hooks, modify hook arguments, set hook stages, or set up git hooks in a new project. Supports both pre-commit (Python) and prek (Rust) tools.
---

# Pre-Commit Hook Setup

You are an expert at configuring git pre-commit hooks using either **pre-commit** or **prek**.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [When This Skill Activates](#when-this-skill-activates)
- [Workflow](#workflow)
  - [1. Detect Existing Configuration](#1-detect-existing-configuration)
  - [2. Load Tool Reference](#2-load-tool-reference)
  - [3. Configure Hooks](#3-configure-hooks)
  - [4. Validate](#4-validate)
- [Hook Stages](#hook-stages)
- [Key Principles](#key-principles)

<!-- mdformat-toc end -->

## When This Skill Activates<a name="when-this-skill-activates"></a>

- User asks to add, set up, or configure pre-commit hooks
- User asks to add a specific hook (e.g., "add ruff to pre-commit")
- User wants to modify hook arguments, stages, or file filters
- User is setting up a new project and wants git hooks

## Workflow<a name="workflow"></a>

### 1. Detect Existing Configuration<a name="1-detect-existing-configuration"></a>

Check for existing config files in the project root:

- `.pre-commit-config.yaml` or `.pre-commit-config.yml` → **pre-commit** (or prek with YAML)
- `prek.toml` → **prek**
- Neither → ask the user which tool to use

### 2. Load Tool Reference<a name="2-load-tool-reference"></a>

Based on the detected tool:

- **pre-commit**: Read `references/pre-commit-quick-reference.md`
- **prek**: Read `references/prek-quick-reference.md`

Only read the comprehensive reference (`references/pre-commit-comprehensive.md` or `references/prek-comprehensive.md`)
if the user's question involves:

- Hook authoring (creating custom hooks)
- Workspace/monorepo configuration (prek only)
- CI/CD integration
- Language-specific toolchain configuration
- Advanced file type filtering

### 3. Configure Hooks<a name="3-configure-hooks"></a>

When adding hooks:

1. Check `references/hook-catalog.md` for recommended hooks for the project's language/stack
2. Use the correct config format (YAML for pre-commit, TOML or YAML for prek)
3. Use specific `rev` tags, never branches or `HEAD`
4. Set appropriate `types`/`types_or` filters to avoid running hooks on irrelevant files
5. Configure `stages` explicitly if the hook isn't a pre-commit hook

### 4. Validate<a name="4-validate"></a>

After making changes:

- **pre-commit**: `pre-commit validate-config`
- **prek**: `prek validate-config`

Then offer to run a test: `pre-commit run --all-files` or `prek run --all-files`

## Hook Stages<a name="hook-stages"></a>

Most users want pre-commit hooks. If the user asks about other stages, all of these are supported:

| Stage              | When It Runs                            |
| ------------------ | --------------------------------------- |
| pre-commit         | Before finalizing commit (default)      |
| prepare-commit-msg | Before commit message editor            |
| commit-msg         | Validate commit message                 |
| post-commit        | After successful commit                 |
| pre-push           | Before push                             |
| pre-merge-commit   | Before merge commit                     |
| post-merge         | After merge                             |
| post-checkout      | After checkout                          |
| post-rewrite       | After amend/rebase                      |
| pre-rebase         | Before rebase                           |
| manual             | Only via explicit `--hook-stage manual` |

## Key Principles<a name="key-principles"></a>

- **Use specific revisions**: Always pin to tags (`rev: v1.2.3`), never branches
- **Prefer type filters over file patterns**: `types: [python]` is better than `files: \.py$`
- **Don't over-configure**: Start with common hooks, add more as needed
- **Validate after changes**: Always run validation and test with `--all-files`
