---
name: docs-bootstrap
description: >-
  Complete Project Documentation Bootstrap Process. Generates in-depth per-module
  documentation for Python projects in README.md files optimized for GitHub web UI browsing.
  Includes architecture diagrams (Mermaid), API quick-reference tables, collapsible sections,
  breadcrumb navigation, and dependency visualization. Triggers on: "docs-bootstrap",
  "generate documentation", "bootstrap docs", "document this project", "create READMEs".
---

# Documentation Bootstrap Process

Generate comprehensive, GitHub-optimized per-module documentation for Python projects.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Prerequisites](#prerequisites)
- [Phase 1: Project Exploration](#phase-1-project-exploration)
  - [1.1 Create Task Breakdown](#11-create-task-breakdown)
  - [1.2 Structure Analysis](#12-structure-analysis)
  - [1.3 Documentation Planning](#13-documentation-planning)
- [Phase 2: Systematic Documentation Creation](#phase-2-systematic-documentation-creation)
  - [2.1 Documentation Order](#21-documentation-order)
  - [2.2 Per-Module Documentation Process](#22-per-module-documentation-process)
  - [2.3 Agent Delegation Pattern](#23-agent-delegation-pattern)
  - [2.4 Quality Standards](#24-quality-standards)
- [Phase 3: Master Navigation Integration](#phase-3-master-navigation-integration)
  - [3.1 Root README Structure](#31-root-readme-structure)
  - [3.2 Navigation Patterns](#32-navigation-patterns)
- [Phase 4: Quality Assurance](#phase-4-quality-assurance)
  - [4.1 Completeness Check](#41-completeness-check)
  - [4.2 Consistency Review](#42-consistency-review)
  - [4.3 Formatting Pass](#43-formatting-pass)
  - [4.4 Final Metrics](#44-final-metrics)

<!-- mdformat-toc end -->

## Prerequisites<a name="prerequisites"></a>

- Read `references/templates.md` for all README templates and formatting patterns
- Read `references/api-extraction.md` for Python API surface extraction methodology

## Phase 1: Project Exploration<a name="phase-1-project-exploration"></a>

### 1.1 Create Task Breakdown<a name="11-create-task-breakdown"></a>

Use TodoWrite to create the tracking structure:

```
- Explore project structure (full directory tree, file counts, existing docs)
- Document root package (overview, quick start, master ToC)
- Document foundation modules (base classes, core infrastructure)
- Document major module categories (primary functionality)
- Document supporting infrastructure (utilities, errors, testing)
- Create master navigation and cross-references
- Quality assurance pass (links, diagrams, completeness)
```

### 1.2 Structure Analysis<a name="12-structure-analysis"></a>

Delegate to `docs-architect` agent (or `Explore` for initial pass):

```
Task(
    description="Explore project structure for documentation",
    subagent_type="docs-architect",
    prompt="Explore the full structure of [package] to understand all directories and Python modules.

    Provide:
    1. Complete directory tree with file counts per directory
    2. All Python modules (.py files) in each directory
    3. Which directories have actual code vs only __init__.py
    4. Existing README files and their quality/freshness
    5. Module dependency graph (what imports what)
    6. Public API surface: modules with __all__, public classes/functions
    7. Categorize by complexity: large (10+ files), medium (3-9), small (1-2)

    Be thorough — explore all subdirectories recursively."
)
```

### 1.3 Documentation Planning<a name="13-documentation-planning"></a>

Based on exploration results, assign documentation strategy:

| Module Size        | Strategy                                          | Agent                  |
| ------------------ | ------------------------------------------------- | ---------------------- |
| Large (10+ files)  | Break into sub-tasks, document subdirs separately | `docs-architect`       |
| Medium (3-9 files) | Single Task call with full file list              | `docs-architect`       |
| Small (1-2 files)  | Direct Read + Write                               | None (handle directly) |

## Phase 2: Systematic Documentation Creation<a name="phase-2-systematic-documentation-creation"></a>

### 2.1 Documentation Order<a name="21-documentation-order"></a>

1. **Root Package** — Package overview, installation, quick start
2. **Foundation Modules** — Base classes, protocols, core abstractions
3. **Major Categories** — Primary functionality grouped by domain
4. **Supporting Infrastructure** — Utilities, error handling, fixtures
5. **Specialized Modules** — Parsers, transports, platform-specific code
6. **Master Navigation** — Root README with full table of contents

### 2.2 Per-Module Documentation Process<a name="22-per-module-documentation-process"></a>

For each module, the agent MUST:

1. **Read all Python files** in the module — never guess functionality
2. **Extract public API surface** — follow `references/api-extraction.md`
3. **Generate Mermaid diagrams** — class hierarchy and/or data flow
4. **Create README.md** — following templates from `references/templates.md`
5. **Add breadcrumb navigation** — link back up the directory tree
6. **Include dependency info** — what this module imports and what imports it

### 2.3 Agent Delegation Pattern<a name="23-agent-delegation-pattern"></a>

```
Task(
    description="Document [module_name] module",
    subagent_type="docs-architect",
    prompt="Document the [module_name] module at [path].

    Files in this module:
    [list files from exploration]

    Requirements:
    1. Read ALL Python files and extract public API (classes, functions, constants)
    2. Create a Mermaid class diagram showing inheritance and key relationships
    3. Create a quick-reference table of all public symbols (name, signature, description)
    4. Include copy-pasteable usage examples with imports and expected output
    5. Use collapsible <details> sections for method-level detail
    6. Add breadcrumb navigation at the top: [Root](../../README.md) > [Parent](../README.md) > Module
    7. Document dependencies (internal imports and external packages)
    8. Document reverse dependencies (what other modules import from this one)

    Use relative paths from repo root. Do NOT use absolute paths with home directory.
    Follow the templates in the references/ directory for structure and formatting."
)
```

### 2.4 Quality Standards<a name="24-quality-standards"></a>

**Technical Accuracy:**

- Read actual source code — never guess or hallucinate functionality
- Document all public classes with their method signatures
- Include parameter types and return values from type annotations
- Explain complex algorithms and data structures
- Note special requirements, dependencies, or platform constraints

**GitHub Web UI Optimization:**

- Mermaid diagrams render natively — use them liberally
- `<details>` sections keep pages scannable
- Relative links work across branches
- Tables render cleanly for quick-reference content
- Badge images at root README for project metadata

**Code Examples:**

- Every example must be copy-pasteable (include all imports)
- Show expected output in comments or doctest format
- Demonstrate simple usage first, then advanced patterns
- Include error handling for non-obvious failure modes

## Phase 3: Master Navigation Integration<a name="phase-3-master-navigation-integration"></a>

### 3.1 Root README Structure<a name="31-root-readme-structure"></a>

Follow the Root README template from `references/templates.md`. Must include:

- Project badges (Python version, test status, coverage)
- One-paragraph project description
- Quick start with installation + basic usage
- Architecture overview with top-level Mermaid diagram
- Complete module directory with descriptions and file counts
- Development setup instructions

### 3.2 Navigation Patterns<a name="32-navigation-patterns"></a>

**Breadcrumbs** — Every sub-README starts with:

```markdown
[Project Root](../../README.md) > [Category](../README.md) > **This Module**
```

**Master ToC** — Root README links every module:

```markdown
| Module | Description | Files |
|---|---|---|
| [`module_name`](./path/to/README.md) | One-line description | 12 |
```

**Anchor Links** — Long READMEs use internal anchors:

```markdown
## Table of Contents
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Examples](#examples)
```

## Phase 4: Quality Assurance<a name="phase-4-quality-assurance"></a>

### 4.1 Completeness Check<a name="41-completeness-check"></a>

After all modules are documented:

1. Verify every directory with `.py` files has a README.md
2. Confirm all Mermaid diagrams render correctly (valid syntax)
3. Check all relative links point to existing files
4. Validate breadcrumb chains are complete
5. Ensure API tables cover all `__all__` exports

### 4.2 Consistency Review<a name="42-consistency-review"></a>

- Heading hierarchy is uniform across all READMEs
- Mermaid diagram style is consistent (same direction, styling)
- Code examples all include imports and are self-contained
- Terminology is consistent (don't mix "module"/"package"/"component")
- Collapsible sections used uniformly for method-level detail

### 4.3 Formatting Pass<a name="43-formatting-pass"></a>

If the project uses `mdformat` (check `.pre-commit-config.yaml` or `prek.toml`), run it on all created/modified README
files as a final step:

```bash
uv run mdformat <list of README.md files>
```

This ensures all generated documentation conforms to the project's markdown formatting standards before commit.

### 4.4 Final Metrics<a name="44-final-metrics"></a>

Report on completion:

- Total README files created
- Total Python modules documented
- Coverage percentage (dirs with docs / dirs with code)
- Mermaid diagrams created
- API symbols documented
