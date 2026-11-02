---
name: claude-session-logs
description: >-
  Extract and analyze Claude Code session logs for debugging agent/subagent behavior.
  Use when user asks to debug session logs, extract subagent logs, analyze agent errors,
  view agent thought process, investigate why an agent did something, or debug Claude Code sessions.
allowed-tools: Bash(uv run --script */scripts/extract.py *)
---

# Session Log Analysis

Extract and analyze Claude Code session logs, particularly for debugging subagent behavior.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Session Log Location](#session-log-location)
  - [Subagent Log Files](#subagent-log-files)
- [Session References](#session-references)
- [Quick Commands](#quick-commands)
- [Debugging Workflow](#debugging-workflow)
  - [1. Find the session](#1-find-the-session)
  - [2. Quick overview - hierarchy and subagent status](#2-quick-overview---hierarchy-and-subagent-status)
  - [3. Scan for errors](#3-scan-for-errors)
  - [4. View timeline of events](#4-view-timeline-of-events)
  - [5. Compare working vs failing sessions](#5-compare-working-vs-failing-sessions)
  - [6. Extract detailed content](#6-extract-detailed-content)
- [JSONL Structure](#jsonl-structure)
  - [Progress Message Structure](#progress-message-structure)
- [Manual Grep Patterns](#manual-grep-patterns)
- [Finding Agent IDs](#finding-agent-ids)
- [Tips](#tips)

<!-- mdformat-toc end -->

## Session Log Location<a name="session-log-location"></a>

```
~/.claude/projects/<encoded-project-path>/<session-id>.jsonl
```

Project paths are encoded with dashes (e.g., `/Users/username/Developer/myapp` -> `-Users-username-Developer-myapp`).

### Subagent Log Files<a name="subagent-log-files"></a>

When subagents are spawned during a session, their full transcripts are stored separately:

```
~/.claude/projects/<encoded-project-path>/<session-id>/subagents/agent-<agent-id>.jsonl
```

These subagent log files contain the complete activity of that agent (user prompt, assistant responses, tool calls) and
are automatically used when you specify `--agent <id>` with extract/export commands.

## Session References<a name="session-references"></a>

Commands accept session references in multiple formats:

- **Full path**: `/Users/username/.claude/projects/-Users-username-Developer-myapp/abc123.jsonl`
- **Just the UUID**: `abc123-def4-5678-90ab-cdef12345678` (auto-searches all projects)
- **Filename**: `abc123.jsonl` (auto-searches all projects)
- **Agent ID**: `af1f466` (auto-searches subagent folders to find the agent's log file)

The `sessions` command outputs full paths that can be directly copy-pasted to other commands.

## Quick Commands<a name="quick-commands"></a>

```bash
# List projects
uv run --script {baseDir}/scripts/extract.py projects

# Find project by name
uv run --script {baseDir}/scripts/extract.py projects myapp

# List recent sessions for a project
uv run --script {baseDir}/scripts/extract.py sessions myapp

# Find all errors in a session
uv run --script {baseDir}/scripts/extract.py errors <session-file>

# Find specific errors (e.g., "No such tool")
uv run --script {baseDir}/scripts/extract.py errors <session-file> --pattern "No such tool"

# List agent IDs in a session (shows which have separate log files)
uv run --script {baseDir}/scripts/extract.py agents <session-file>

# List subagent log files for a session
uv run --script {baseDir}/scripts/extract.py subagent-files <session-file>

# Show agent spawn hierarchy (who spawned whom)
uv run --script {baseDir}/scripts/extract.py hierarchy <session-file>

# Show subagent summary with status/duration
uv run --script {baseDir}/scripts/extract.py subagents <session-file>

# Show timeline of events with agent context
uv run --script {baseDir}/scripts/extract.py timeline <session-file>

# Compare two sessions
uv run --script {baseDir}/scripts/extract.py compare <session1> <session2>

# Extract full session content (debug format with line numbers)
uv run --script {baseDir}/scripts/extract.py extract <session-file>

# Extract specific agent's activity (auto-uses subagent log file if available)
uv run --script {baseDir}/scripts/extract.py extract <session-file> --agent abc123

# Extract directly using just agent ID (searches all subagent folders)
uv run --script {baseDir}/scripts/extract.py extract af1f466 -v

# Extract with verbose output
uv run --script {baseDir}/scripts/extract.py extract <session-file> -v

# Extract specific line range
uv run --script {baseDir}/scripts/extract.py extract <session-file> --range 30-50

# Export as human-readable transcript (like /export)
uv run --script {baseDir}/scripts/extract.py export <session-file>

# Export specific agent's transcript (auto-uses subagent log file if available)
uv run --script {baseDir}/scripts/extract.py export <session-file> --agent abc123

# Export to file
uv run --script {baseDir}/scripts/extract.py export <session-file> -o transcript.txt
```

## Debugging Workflow<a name="debugging-workflow"></a>

### 1. Find the session<a name="1-find-the-session"></a>

```bash
uv run --script {baseDir}/scripts/extract.py sessions <project-name>
```

### 2. Quick overview - hierarchy and subagent status<a name="2-quick-overview---hierarchy-and-subagent-status"></a>

```bash
# See who spawned whom
uv run --script {baseDir}/scripts/extract.py hierarchy <session-file>

# See all subagents with status (success/failed), duration, tool counts
uv run --script {baseDir}/scripts/extract.py subagents <session-file>

# List subagent log files (shows which agents have separate full transcripts)
uv run --script {baseDir}/scripts/extract.py subagent-files <session-file>
```

Example agents output:

```
af1f466  [log: 47.0KB]
b2c3d4e
```

Agents with `[log: ...]` have separate log files with their complete transcript.

Example subagent-files output:

```
Agent ID     Size         Path
--------------------------------------------------------------------------------
af1f466      47.0KB       /path/to/session/subagents/agent-af1f466.jsonl
```

Example hierarchy output:

```
Main conversation
└── code-reviewer (a9f97ce) [✓]
    ├── cr-claude-compliance (a1b2c3d) [✓]
    ├── cr-diff-bugs (a2c3d4e) [✓]
    └── cr-intent-context [spawn attempted, no agent created]
```

Example subagents output:

```
Agent                Spawned By   Status     Duration   Tools
----------------------------------------------------------------------
code-reviewer        main         ✓ success  45.2s      12
cr-claude-compliance a9f97ce      ✓ success  8.3s       5
cr-diff-bugs         a9f97ce      ✗ FAILED   0.1s       1     (No such tool avail...)
```

### 3. Scan for errors<a name="3-scan-for-errors"></a>

```bash
# All errors
uv run --script {baseDir}/scripts/extract.py errors <session-file>

# Filter by pattern
uv run --script {baseDir}/scripts/extract.py errors <session-file> --pattern "No such tool"
```

### 4. View timeline of events<a name="4-view-timeline-of-events"></a>

```bash
uv run --script {baseDir}/scripts/extract.py timeline <session-file>
```

Example output:

```
[15:56:06] MAIN: Task(code-reviewer: Review branch changes)
[15:56:11] a9f97ce: Bash(git --no-pager diff HEAD --stat...)
[15:56:22] a9f97ce: Task(cr-claude-compliance) (bg)
[15:56:22] a9f97ce: Task(cr-diff-bugs) (bg)
[15:56:25] a9f97ce: ❌ ERROR: No such tool available: Task
```

### 5. Compare working vs failing sessions<a name="5-compare-working-vs-failing-sessions"></a>

```bash
uv run --script {baseDir}/scripts/extract.py compare <working-session> <failing-session>
```

Shows differences in:

- Agents spawned and their status
- Errors encountered
- Tool usage counts

### 6. Extract detailed content<a name="6-extract-detailed-content"></a>

```bash
# Full session
uv run --script {baseDir}/scripts/extract.py extract <session-file> -v

# Specific agent only
uv run --script {baseDir}/scripts/extract.py extract <session-file> --agent <id> -v

# Specific line range around an error
uv run --script {baseDir}/scripts/extract.py extract <session-file> --range 25-40 -v
```

## JSONL Structure<a name="jsonl-structure"></a>

Each line is a JSON object. Key types:

| Type        | Description                                        |
| ----------- | -------------------------------------------------- |
| `progress`  | Agent activity (most useful for subagent analysis) |
| `user`      | User messages                                      |
| `assistant` | Assistant responses                                |

### Progress Message Structure<a name="progress-message-structure"></a>

```json
{
  "type": "progress",
  "parentToolUseID": "toolu_bdrk_xxx",
  "data": {
    "agentId": "abc123",
    "prompt": "original prompt to agent",
    "message": {
      "message": {
        "content": [
          {"type": "text", "text": "reasoning..."},
          {"type": "tool_use", "name": "Bash", "id": "...", "input": {...}},
          {"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": true}
        ]
      }
    }
  }
}
```

## Manual Grep Patterns<a name="manual-grep-patterns"></a>

When you need more control than the script provides:

```bash
# Find tool errors
grep -n '"is_error":true' <session>.jsonl

# Find specific error messages
grep -n "No such tool available" <session>.jsonl
grep -n "tool_use_error" <session>.jsonl

# Find specific tool usage
grep -n '"name":"Task"' <session>.jsonl
grep -n '"name":"Bash"' <session>.jsonl

# Find claude CLI usage (problematic in agents)
grep -n 'claude -p\|claude --model' <session>.jsonl

# Find all unique agent IDs
grep -o '"agentId":"[^"]*"' <session>.jsonl | sort -u

# Trace parent relationships
grep -o '"parentToolUseID":"[^"]*"' <session>.jsonl | sort -u
```

## Finding Agent IDs<a name="finding-agent-ids"></a>

When skills spawn subagents via Task tool, the completion message includes:

```
agentId: ad6d3a3 (for resuming...)
```

Use this ID with `--agent` flag to extract just that subagent's activity.

## Tips<a name="tips"></a>

- **Subagent log files**: When an agent has a separate log file (shown by `agents` or `subagent-files`), the `extract`
  and `export` commands automatically read from that file, giving you the complete transcript instead of just progress
  messages from the main session
- **Direct agent access**: You can use just the agent ID (e.g., `af1f466`) as the session argument - it will search all
  subagent folders to find the log file
- **Large sessions**: Use `--range` to focus on specific lines
- **Parallel tool calls**: Multiple tool_use items appear in the same content array
- **Nested agents**: `parentToolUseID` traces the call hierarchy - use `hierarchy` command to visualize
- **Agent prompts**: The `prompt` field shows what was passed to the subagent
- **Failed spawns**: The `hierarchy` command shows spawn attempts that didn't create agents (e.g., "No such tool"
  errors)
- **Comparing sessions**: Use `compare` to quickly spot differences between working and failing sessions
