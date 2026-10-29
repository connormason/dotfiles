[Project Root](../README.md) > [Docs](README.md) > **Model Router**

# Model Router

A Claude Code hook pair that routes subagent spawns (`Agent`/`Task` tool calls) to the cheapest adequate model. Hooks
cannot change the main session's model, so only subagents are routed. Rationale and rejected alternatives:
[design](plans/2026-10/2026-10-29-model-router-design.md).

Source: [`stow/claude/.claude/hooks/model-router.py`](../stow/claude/.claude/hooks/model-router.py), defaults in
[`model-router.default.json`](../stow/claude/.claude/hooks/model-router.default.json), wired through
[`render/claude.json`](../render/claude.json).

## Behavior

For each `Agent`/`Task` call the `pre` hook applies the first matching step:

1. `mode` is `off`, or the prompt or description starts with `opt_out_prefix` (default `~`): do nothing.
2. `subagent_type` is in `agent_overrides`: use that model.
3. `subagent_type` is in `classify_types` (default `general-purpose`, `Explore`): the first rule whose regex matches the
   description plus prompt picks a class, and `classes` maps it to a model.
4. Otherwise do nothing.

A call that already sets `model` is never changed; a disagreement is only logged. `floor` lifts a chosen model to a
minimum tier. In `advise` mode the hook adds context suggesting the model; in `enforce` mode it rewrites `model`. The
hook never denies a call and fails open on any error.

The `post` hook logs the outcome. A `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` baseline in `render/claude.json` separately
moves unpinned subagents to Sonnet.

## Configuration

Layered JSON, later wins: the shipped default, `~/.claude/model-router.json`, `.claude/model-router.json` in the
project. Objects deep-merge, `rules` concatenate with the later layer first, everything else replaces. An invalid layer
disables routing and writes an error record to the log.

| Key               | Meaning                                                                  |
| ----------------- | ------------------------------------------------------------------------ |
| `mode`            | `off`, `advise` (default), or `enforce`                                  |
| `opt_out_prefix`  | Prompt or description prefix that skips routing                          |
| `classes`         | Class name to model alias (`haiku`, `sonnet`, `opus`, `fable`)           |
| `agent_overrides` | `subagent_type` to model alias; checked before rules                     |
| `classify_types`  | Agent types whose prompts are matched against `rules`                    |
| `rules`           | Ordered `{id?, class, any: [regex]}`; case-insensitive; first match wins |
| `floor`           | Minimum tier (`haiku` < `sonnet` < `opus`); `null` disables              |
| `log`             | Write the decision log                                                   |

## Decision log

`${XDG_STATE_HOME:-~/.local/state}/dotfiles/model-router/decisions.jsonl`, rotated once to `decisions.jsonl.1` above
about 1 MB. One JSON object per line; `pre` and `post` records share a `tool_use_id`. Prompt text is never logged, only
`prompt_len` and the matched `rule`. Error records (`event: error`) are written even when `log` is false, and carry no
session or tool-use id. `post` records carry `resolved_model`, read from the payload's `tool_response.resolvedModel`;
the payload's `tool_input` already holds the rewritten `model`, so correlate with the `pre` record (same `tool_use_id`)
to see what the caller originally chose.

```bash
# Where would enforce have changed the model?
jq -c 'select(.event == "pre" and .action != "passthrough")' ~/.local/state/dotfiles/model-router/decisions.jsonl
# Calls where the caller's model disagreed with the router
jq -c 'select(.reason == "preset-disagree")' ~/.local/state/dotfiles/model-router/decisions.jsonl
```

## Rollout

The hook ships in `advise`. After about a week of logs, review the `advise` and `preset-disagree` records; when the
suggestions look right, set `{"mode": "enforce"}` in `~/.claude/model-router.json`.
