# Subagent Model Router Design

**Date:** 2026-10-29
**Status:** Approved (design); implementation plan pending
**Goal:** Route each `Agent`/`Task` subagent spawn to the cheapest adequate model via a configurable Claude Code hook,
built entirely inside this repo (no external plugin dependency). Inspired by `tzachbon/claude-model-router-hook`.

## Context

The default session posture is Opus 4.8 [1m] at `xhigh`. Subagents without a pinned `model` inherit that, including the
built-in `general-purpose` and `Explore` agents. Custom agents already pin models (`file-searcher` → haiku,
`file-explorer` → sonnet), but the generic agents are where mechanical work runs on the most expensive tier.

### What hooks can and cannot do (verified 2026-10-29)

| Capability                                          | Verdict | Source                                                                                  |
| --------------------------------------------------- | ------- | --------------------------------------------------------------------------------------- |
| `UserPromptSubmit` changes the session model        | No      | Output is limited to `decision: "block"` and `additionalContext`; it cannot rewrite     |
| `PreModelSwitch` / `PostModelSwitch` pick a model   | No      | They can allow/deny/block a requested switch, or observe it                             |
| `PreToolUse` rewrites tool input (`updatedInput`)   | Yes     | Documented generally; **applying to `Agent` is confirmed only by the reference repo's code** |
| Subagent model precedence                           | Known   | `Agent` call `model` param > agent frontmatter > `CLAUDE_CODE_SUBAGENT_MODEL` > parent  |

Consequences:

- The main session cannot be routed per prompt. Scope is **subagent spawns only**.
- The `Agent` call's `model` parameter accepts bare aliases only (`sonnet`, `opus`, `haiku`, `fable`), never full IDs.
- An alias in the same family as the main model resolves to the main model's exact ID (including `[1m]`).
- Because the call parameter outranks frontmatter, the router must skip calls that already set `model`, or it would
  override pinned agents such as `file-searcher`.
- The reference repo's "write the next session's model" feature is **rejected**: it would edit `~/.claude/settings.json`,
  which `scripts/dotfiles/render.py` owns, and the drift guard would fail the next render.

## Scope

In scope (phases 1–2):

1. **Baseline:** `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` in `render/claude.json` (`env`). Frontmatter and per-call params
   still win, so only unpinned agents change. Precedence changed in v2.1.251; confirm on the installed version.
2. **Router:** `PreToolUse` hook on `Agent|Task`, a `PostToolUse` logger, layered JSON config, a decision log, tests.

Out of scope (deferred): prompt-level `UserPromptSubmit` advisory (would replace `delegate-search-nudge.py`, which has
known false positives), the opt-in `claude -p --model haiku` fallback classifier, a `run.py` log-report command.

## Decisions

| Decision               | Choice                                                    | Rationale                                                                        |
| ---------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Classification         | Hybrid: type-map first, keyword rules for generic types   | Type is a strong signal; rules only refine `general-purpose`/`Explore`           |
| Weak signals           | Pass through unchanged                                    | A misroute to a small model on hard work costs more than the saving              |
| Rollout mode           | Ship in `advise`; flip to `enforce` after reviewing logs  | Evidence before behavior change                                                  |
| Config format          | JSON (stdlib-parsable)                                    | Hooks run under bare `python3` whose version is not pinned; `tomllib` needs 3.11 |
| File layout            | One script, `pre`/`post` subcommands                      | Matches flat stdlib hooks; avoids sibling imports behind stow symlinks           |
| Failure mode           | Fail open: exit 0, call unchanged, error logged           | A router must never block work                                                   |
| Settings wiring        | `render/claude.json` fragment, never the live file        | Drift guard refuses renders over hand-edited settings                            |

## Architecture

### Decision flow (per `Agent`/`Task` call; first match wins)

1. Mode `off`, or prompt carries the opt-out prefix → pass through.
2. `model` already set on the call → pass through; log a disagreement if the router would have chosen differently.
3. `subagent_type` in `agent_overrides` → use that model.
4. `subagent_type` in `classify_types` (default `general-purpose`, `Explore`) → evaluate ordered `rules` against
   `description` + `prompt`; the first matching rule yields a class, mapped to a model via `classes`.
5. Otherwise → pass through.

The `floor` setting prevents nested delegation from dropping below a minimum tier. `advise` mode emits a message only;
`enforce` mode returns `updatedInput` with `model` set. The hook never denies a call.

### Config

Layered, project wins: repo default (`model-router.default.json`, shipped beside the script) → `~/.claude/model-router.json`
→ `.claude/model-router.json`. Objects deep-merge; `rules` concatenate with project rules evaluated first. Employer- or
project-specific rules belong in the user/project layers or the work overlay, never the public default.

```json
{
  "mode": "advise",
  "opt_out_prefix": "~",
  "classes": {"mechanical": "haiku", "standard": "sonnet", "hard": "opus"},
  "agent_overrides": {"Plan": "opus"},
  "classify_types": ["general-purpose", "Explore"],
  "rules": [
    {"class": "mechanical", "any": ["\\brename\\b", "\\bgrep\\b", "\\blist all\\b"]},
    {"class": "hard", "any": ["\\barchitect", "\\bdesign\\b.*\\btrade-?off"]}
  ],
  "floor": "haiku",
  "log": true
}
```

### Components and wiring

- `stow/claude/.claude/hooks/model-router.py` — config load/merge, pure `decide()` (plain dicts in/out), hook I/O
  wrappers, log writer. Invoked as `model-router.py pre` or `model-router.py post`.
- `stow/claude/.claude/hooks/model-router.default.json` — shipped defaults.
- `render/claude.json` — `PreToolUse` and `PostToolUse` entries (matcher `Agent|Task`) plus the `env` baseline.
- Docs — `stow/README.md` package table and a hook README entry (`tests/unit/test_docs_consistency.py` checks the table).

### Decision log

`${XDG_STATE_HOME:-~/.local/state}/dotfiles/model-router/decisions.jsonl`, rotated once at ~1 MB.

- Pre record: timestamp, `session_id`, `tool_use_id`, `subagent_type`, requested model, decided model, class, matched
  rule id, mode, action (`passthrough` | `advise` | `rewrite`).
- Post record: same `tool_use_id`, plus the resolved model if the payload carries it.
- Prompt text is never logged; only the rule id and prompt length.

## Error handling

Malformed stdin, unreadable or invalid config, or any exception → exit 0, call unchanged, error appended to the log.
Open risk: if another `PreToolUse` hook also rewrites the same `Agent` call, the winner depends on Claude Code's merge
order, which is undocumented. The base layer has no other `Agent` matchers today; revisit if one is added.

## Testing and verification

**Spike first (manual, in a live session; pytest cannot exercise it):**

1. `updatedInput` actually changes the model on an `Agent` call on the installed version. If this fails, the design
   degrades to advise-only and must be revised before further work.
2. Contents of the `PostToolUse` payload for `Agent` (decides whether a "resolved model" log field is possible).
3. Which `python3` the hook runner resolves, so the script targets a compatible version.

**Unit tests** (`tests/unit/test_model_router.py`, script loaded by file path as existing hook tests do):

- decision table, parametrized: opt-out, preset model, override, classified, unmatched, floor
- config layering and rule precedence
- hook output JSON shape for `advise` vs `enforce`
- fail-open on malformed stdin and invalid config
- log write and rotation

**Rollout:** ship in `advise`; after about a week of logs, review disagreements before enabling `enforce`.

## Open questions

- Exact `PostToolUse` fields for `Agent` (resolved by spike item 2).
- Whether `Task` is still a distinct tool name on the installed version, or only `Agent` (matcher `Agent|Task` covers both).
