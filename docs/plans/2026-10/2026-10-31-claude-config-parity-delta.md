# Claude Code Config Parity: Work vs. Personal Delta Report

**Date:** 2026-10-31
**Scope:** user-level Claude Code configuration only (`~/.claude` files and rendered `settings.json`).
**Companion docs:** [design](2026-10-31-claude-config-parity-design.md), [plan](2026-10-31-claude-config-parity-plan.md)

Employer-internal items are described generically; this repo is public.

## Ported in this change

| Item                        | Notes                                                                                                                  |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Statusline                  | Clean-room Python renderer reading the shared `statusLineConfig`; `todos` dropped                                      |
| claude-devtools config      | Stowed; the cask was already in the base Brewfile                                                                      |
| `claude-session-logs` skill | Invokes its script through `uv run --script` (base permissions deny `python3`)                                         |
| `gh-pr-comments` skill      | GitHub Enterprise example and a usage-example username genericized; `env bash` shebang                                 |
| `shell-scripting` skill     | Copied unchanged                                                                                                       |
| Public plugins              | Eight official-marketplace plugins added beside the existing `pyright-lsp`                                             |

## Already at parity (no change needed)

Generic permission allow/deny lists, `spinnerVerbs`, `statusLineConfig`, `attribution`, `autoMemoryEnabled`,
`effortLevel`, `theme`, `verbose`, `worktree.baseRef`, `skipWorkflowUsageWarning`, the shared hook set (personal uses
`$HOME` paths), rules, commands, the other skills, and the agents. The personal copies of `file-searcher`,
`ansible-devops-engineer`, `CLAUDE.md`, `dotclaude-cleanup`, and the hook scripts are the generalized versions; the
work copies differ only by employer wording, `#!/bin/bash` shebangs, and employer-specific cleanup sections.

## Deliberately not ported (employer-specific)

| Item                                                          | Reason                                                            |
| ------------------------------------------------------------- | ----------------------------------------------------------------- |
| API key helper, available-models list and its hash            | Tied to the employer's model gateway                              |
| Company announcements                                         | Employer content                                                  |
| Internal marketplaces, strict-marketplace list, their plugins | Internal sources, unreachable off the corporate network           |
| MCP servers and their permission entries                      | Internal services                                                 |
| Gateway, registry, and index env vars; shell-prefix wrapper   | Internal infrastructure                                           |
| Disabled CLI commands, autoupdater, and sandbox toggles       | Managed-install policy                                            |
| Message-display and tool-call-monitor hooks                   | Part of the managed install                                       |
| Permission-review hook                                        | Built entirely on the internal AI gateway and its auth            |
| Managed-install config tree and its skill                     | Managed-install internals                                         |
| VM-management skill and test-framework agent                  | Internal tools                                                    |
| Bug-tracker branch-workflow section of the global CLAUDE.md   | Internal tool                                                     |
| Extra CA bundle export in `32-claude.zsh`                     | Corporate TLS                                                     |
| Internal entries in `autoMode` and one spinner verb           | Employer references                                               |
| Internal npm statusline package and its bash fallback         | Unlicensed internal package (replaced by the clean-room renderer) |

## Skipped as redundant

- `modelSettings` effort `high` for Sonnet: equal to the global `effortLevel`.

## Personal-only (candidates to bring to work)

- `model-router` hooks and `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`.
- The `dotclaude-cleanup.d/` drop-in extension mechanism and `#!/usr/bin/env bash` shebangs.
- The clean-room statusline (it runs anywhere `uv` is installed).
- iTerm2 `cc-status` hooks (personal-mac overlay).

## Follow-ups

- After merge, on the personal Mac: run `95-dotfiles` and `97-render`, install the new plugins, and confirm that
  `python3 run.py render --check claude` exits 0 and the statusline renders.
- Decide separately whether to rebuild a permission-review hook against a personal API key.
