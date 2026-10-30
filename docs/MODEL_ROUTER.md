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

The `post` hook logs the outcome.

### Sonnet baseline

`CLAUDE_CODE_SUBAGENT_MODEL=sonnet` (a key in `env` of [`render/claude.json`](../render/claude.json)) is separate from
the router and takes effect at render time. It moves every subagent that has neither a frontmatter `model` nor a
per-call `model` to Sonnet: `general-purpose` and unpinned plugin reviewers and architects, which inherit the main model
otherwise.

- It is separable: delete that one `env` key to revert (it was added in its own commit).
- During the `advise` period the router only advises, so hard work in unpinned agents runs on Sonnet until `enforce` is
  switched on.
- Precedence is per-call `model` > agent frontmatter > `CLAUDE_CODE_SUBAGENT_MODEL` > main model. Before Claude Code
  v2.1.251 the env var took precedence over both. Verified end to end on 2.1.293: pinned agents stayed on their
  frontmatter model, and an `enforce` rewrite beat the env var.

## Configuration

Layered JSON, later wins: the shipped default, `~/.claude/model-router.json`, `.claude/model-router.json` in the
project. Objects deep-merge, `rules` concatenate with the later layer first, everything else replaces. An invalid layer
disables routing and writes an error record to the log.

| Key               | Meaning                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mode`            | `off`, `advise` (default), or `enforce`                                                                                                                   |
| `opt_out_prefix`  | Prompt or description prefix that skips routing                                                                                                           |
| `classes`         | Class name to model alias (`haiku`, `sonnet`, `opus`, `fable`)                                                                                            |
| `agent_overrides` | `subagent_type` to model alias; checked before rules                                                                                                      |
| `classify_types`  | Agent types whose prompts are matched against `rules`                                                                                                     |
| `rules`           | Ordered `{id?, class, any: [regex]}`; matched case-insensitively against `description` + newline + `prompt`, where `.` matches newlines; first match wins |
| `floor`           | Minimum tier (`haiku` < `sonnet` < `opus`); `null` disables                                                                                               |
| `log`             | Write the decision log                                                                                                                                    |

### Shipped defaults

From [`model-router.default.json`](../stow/claude/.claude/hooks/model-router.default.json):

| Key               | Value                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------- |
| `mode`            | `advise`                                                                                            |
| `opt_out_prefix`  | `~`                                                                                                 |
| `classes`         | `mechanical` → `haiku`, `standard` → `sonnet`, `hard` → `opus` (no shipped rule maps to `standard`) |
| `agent_overrides` | `Plan` → `opus`                                                                                     |
| `classify_types`  | `general-purpose`, `Explore`                                                                        |
| `floor`           | `haiku` (effectively a no-op: it is the lowest tier)                                                |
| `log`             | `true`                                                                                              |

Rules, in order (`hard-keywords` is first so a prompt carrying both signals routes up):

| Rule                  | Class        | Patterns                                                                                                              |
| --------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------- |
| `hard-keywords`       | `hard`       | `\barchitect`, `\bdesign\b.*\btrade-?offs?\b`, `\broot cause\b`, `\bsecurity (review\|audit)\b`, `\brace condition\b` |
| `mechanical-keywords` | `mechanical` | `\brename\b`, `\bgrep\b`, `\blist all\b`, `\bfind (all\|every)\b`, `\bwhere (is\|are)\b`                              |

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

### Before enabling enforce

- `advise` is not a pure dry run: its context nudges the main model to pass `model=` explicitly. Later spawns then show
  up in the log as `preset-agree`/`preset-disagree` passthroughs, and a habit of pinning would also bypass `enforce`.
- Review the advise log for:
  - the `resolved_model` of `Explore` spawns with `requested_model: null` (if built-in `Explore` is pinned to a cheap
    model, classifying `Explore` can only upgrade it);
  - how often the broad `\barchitect` pattern fires on search-style prompts;
  - false positives from `\bgrep\b` and `where (is|are)`, since prompts often instruct the agent to grep.
- Only a foreground `Agent` spawn's `PostToolUse` payload has been captured; for background spawns `resolved_model` may
  be `null`.
- Full context for any record can be recovered from the session transcript via `session_id` and `tool_use_id`.
