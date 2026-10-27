# Complete Project Documentation Bootstrap Process

Generate comprehensive, GitHub-optimized per-module documentation for a Python project.

## Instructions

1. Load and follow the `docs-bootstrap` skill (read `skills/docs-bootstrap/SKILL.md`)
2. Read the reference files:
   - `skills/docs-bootstrap/references/templates.md` — README templates with Mermaid diagrams, collapsible sections,
     badges, and navigation patterns
   - `skills/docs-bootstrap/references/api-extraction.md` — Python public API extraction methodology
3. Delegate complex module documentation to the `docs-architect` agent
4. Execute the skill's phases systematically, tracking progress with TodoWrite

## Key Requirements

- **Mermaid diagrams**: Class hierarchies, data flows, and module dependency graphs (rendered natively by GitHub)
- **API quick-reference tables**: Every public symbol with signature and one-line description
- **Collapsible sections**: `<details>` for method-level detail and extended examples
- **Breadcrumb navigation**: Every sub-README links back up the directory tree
- **Dependency mapping**: What each module imports AND what imports it (bidirectional)
- **Copy-pasteable examples**: Self-contained with imports and expected output
- **Badges**: Python version, test status, coverage at root README

## Output

A hierarchy of README.md files throughout the project that provides complete, accurate, navigable documentation
optimized for the GitHub web interface. Every directory containing Python code gets a README.
