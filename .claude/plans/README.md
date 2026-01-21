# Dotfiles Infrastructure Improvement Plans

This directory contains detailed implementation plans for improving the personal dotfiles repository.

## Plan Index

| # | Plan | Priority | Complexity | Dependencies |
|---|------|----------|------------|--------------|
| 01 | [Inventory Submodule Resolution](01-inventory-submodule-resolution.md) | High | Low | None |
| 02 | [Unified Bootstrap Script](02-unified-bootstrap-script.md) | High | Medium | 01 |
| 03 | [Docker Security & Env Vars](03-docker-security-env-vars.md) | High | Medium | None |
| 04 | [Bootstrap Security Hardening](04-bootstrap-security-hardening.md) | Medium | Low | 02 |
| 05 | [Repo Integration Strategy](05-repo-integration-strategy.md) | Medium | High | 01, 02 |
| 06 | [Pre-commit & Code Quality](06-precommit-code-quality.md) | Low | Low | None |
| 07 | [Role Documentation](07-role-documentation-dependencies.md) | Low | Low | None |

## Recommended Execution Order

### Phase 1: Foundation (Quick Wins)
1. **01 - Inventory Submodule** - Resolve the conflicting approaches
2. **03 - Docker Security** - Fix security gaps in NAS configuration
3. **06 - Pre-commit** - Enable commented-out linting

### Phase 2: Bootstrap Consolidation
4. **02 - Unified Bootstrap** - Merge duplicate scripts
5. **04 - Bootstrap Security** - Add validation checks

### Phase 3: Architecture
6. **05 - Repo Integration** - Design personal/work layering
7. **07 - Role Documentation** - Document for maintainability

## Session Planning

Each plan is designed to be completed in a single Claude Code session. For larger plans (02, 05), consider splitting
into phases.

### Single-Session Plans (~30 min each)
- 01, 03, 04, 06, 07

### Multi-Session Plans
- 02: 2 sessions (Phase 1-2, then Phase 3-4)
- 05: 3 sessions (Phase 1, Phase 2, Phase 3-4)

## How to Use These Plans

1. **Review the plan** in your next session
2. **Copy the Implementation Tasks** to your todo list
3. **Work through tasks** checking them off
4. **Validate** using the checklist at the end
5. **Commit** changes with descriptive messages

## Key Decisions Required

Before starting, decide on:

1. **Inventory approach** (Plan 01): Submodule or standalone clone?
2. **Backward compatibility** (Plan 02): Keep old scripts as wrappers?
3. **Network mode** (Plan 03): Can Plex use bridge networking?
4. **Commit conventions** (Plan 06): Enforce conventional commits?

## Files Summary

```
.claude/plans/
├── README.md                           # This file
├── 01-inventory-submodule-resolution.md
├── 02-unified-bootstrap-script.md
├── 03-docker-security-env-vars.md
├── 04-bootstrap-security-hardening.md
├── 05-repo-integration-strategy.md
├── 06-precommit-code-quality.md
└── 07-role-documentation-dependencies.md
```

## Progress Tracking

Mark plans as complete by adding checkmarks:

- [ ] 01 - Inventory Submodule Resolution
- [ ] 02 - Unified Bootstrap Script
- [ ] 03 - Docker Security & Env Vars
- [ ] 04 - Bootstrap Security Hardening
- [ ] 05 - Repo Integration Strategy
- [ ] 06 - Pre-commit & Code Quality
- [ ] 07 - Role Documentation

---

*Generated: 2026-01-21*
