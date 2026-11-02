# Claude Session Logs Skill for Claude Code

This skill enables Claude Code to extract and analyze its own session logs, particularly useful for debugging subagent
behavior.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Prerequisites](#prerequisites)
- [Usage Examples](#usage-examples)
- [Skill Contents](#skill-contents)
- [How It Works](#how-it-works)
- [Troubleshooting](#troubleshooting)
  - ["No projects directory found"](#no-projects-directory-found)
  - [Script not found](#script-not-found)

<!-- mdformat-toc end -->

## Prerequisites<a name="prerequisites"></a>

This skill uses a Python script included in the skill directory. No external CLI tool is required.

**Requirements:**

- [uv](https://docs.astral.sh/uv/), which runs the stdlib-only script with any installed Python 3.9+

## Usage Examples<a name="usage-examples"></a>

Once installed, you can ask Claude to:

- "Debug why that subagent failed"
- "Show me the errors from my last session"
- "Extract the logs for agent abc123"
- "Export my session as a transcript"
- "What did the Explore agent do?"

## Skill Contents<a name="skill-contents"></a>

```
claude-session-logs/
├── README.md               # This file - installation instructions
├── SKILL.md                # Main skill instructions for Claude
└── scripts/
    └── extract.py          # Log extraction and analysis script
```

## How It Works<a name="how-it-works"></a>

Claude Code stores session logs as JSONL files at:

```
~/.claude/projects/<encoded-project-path>/<session-id>.jsonl
```

The `extract.py` script parses these logs and provides:

- **projects**: List all projects with session logs
- **sessions**: List recent sessions for a project
- **errors**: Find all tool errors in a session
- **agents**: List unique agent IDs (for subagent debugging)
- **extract**: Parse and format session content with line numbers
- **export**: Generate human-readable transcripts (like `/export`)

## Troubleshooting<a name="troubleshooting"></a>

### "No projects directory found"<a name="no-projects-directory-found"></a>

This means no Claude Code sessions have been saved yet. Run a few Claude Code sessions first.

### Script not found<a name="script-not-found"></a>

Verify the script exists and is executable:

```bash
ls -la ~/.claude/skills/claude-session-logs/scripts/extract.py
```
