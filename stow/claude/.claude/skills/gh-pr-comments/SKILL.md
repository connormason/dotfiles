---
name: gh-pr-comments
description: >-
  Fetch all comments from a GitHub PR — conversation comments, review summaries,
  and inline code review comments. Use when user asks to get comments or review
  feedback on a PR.
allowed-tools: Bash(bash */scripts/gh_comments.sh*)
---

# GitHub PR Comments

Fetch all comments from GitHub PRs: conversation thread, review summaries (approve/request changes), and inline code
review comments.

## Usage

```bash
bash {baseDir}/scripts/gh_comments.sh [options]
```

## Options

| Option                | Description                                                               |
| --------------------- | ------------------------------------------------------------------------- |
| `--pr <number>`       | PR number (auto-detected from branch if omitted)                          |
| `--repo <owner/repo>` | Repository (auto-detected if omitted)                                     |
| `--host <hostname>`   | GitHub hostname (auto-detected from git remote if omitted)                |
| `--reviewer <user>`   | Filter by GitHub username                                                 |
| `--no-bots`           | Exclude bot comments (Copilot, etc.)                                      |
| `--context`           | Include diff context around each inline comment                           |
| `--type <type>`       | Comment type: `all`, `conversation`, `reviews`, `inline` (default: `all`) |
| `--verbose`, `-v`     | Show debug messages                                                       |

## Examples

```bash
# All comments on current branch's PR
bash {baseDir}/scripts/gh_comments.sh

# All comments on specific PR, with diff context for inline comments
bash {baseDir}/scripts/gh_comments.sh --pr 1234 --context

# Only inline code review comments
bash {baseDir}/scripts/gh_comments.sh --pr 1234 --type inline
```

## Output

With `--type all` (default), returns a JSON object with three sections:

```json
{
  "conversation": [
    {
      "user": "...",
      "body": "...",
      "created_at": "...",
      "html_url": "..."
    }
  ],
  "reviews": [
    {
      "id": 123,
      "user": "...",
      "state": "APPROVED",
      "body": "...",
      "submitted_at": "..."
    }
  ],
  "review_comments": [
    {
      "path": "...",
      "user": "...",
      "line": 42,
      "start_line": null,
      "body": "...",
      "created_at": "...",
      "review_id": 123,
      "in_reply_to_id": null
    }
  ]
}
```

- **conversation**: Top-level discussion thread comments
- **reviews**: Review summaries (only those with non-empty body text); `state` is `APPROVED`, `CHANGES_REQUESTED`,
  `COMMENTED`, or `DISMISSED`
- **review_comments**: Inline comments on diff lines; `review_id` links to the parent review's `id`; `in_reply_to_id`
  identifies threaded replies

With `--type conversation|reviews|inline`, returns just that section's array.
