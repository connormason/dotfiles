# GitHub PR Comments Skill for Claude Code

This skill enables Claude Code to fetch and display inline code review comments from GitHub pull requests using the `gh`
CLI.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Prerequisites](#prerequisites)
  - [1. Install the GitHub CLI](#1-install-the-github-cli)
  - [2. Authenticate with GitHub](#2-authenticate-with-github)
- [Skill Contents](#skill-contents)
- [Usage Examples](#usage-examples)
- [Script Options](#script-options)
- [Output Format](#output-format)
- [Troubleshooting](#troubleshooting)
  - ["gh: command not found"](#gh-command-not-found)
  - [Authentication errors](#authentication-errors)
  - ["Could not detect repository"](#could-not-detect-repository)
  - ["Could not detect PR"](#could-not-detect-pr)
- [References](#references)

<!-- mdformat-toc end -->

## Prerequisites<a name="prerequisites"></a>

### 1. Install the GitHub CLI<a name="1-install-the-github-cli"></a>

If not already installed, install the `gh` CLI:

```bash
brew install gh
```

### 2. Authenticate with GitHub<a name="2-authenticate-with-github"></a>

```bash
gh auth login
```

For GitHub Enterprise (e.g., github.example.com):

```bash
gh auth login --hostname github.example.com
```

## Skill Contents<a name="skill-contents"></a>

```
gh-pr-comments/
├── README.md               # This file - installation instructions
├── SKILL.md                # Main skill instructions for Claude
└── scripts/
    └── gh_comments.sh      # Script to fetch PR comments
```

## Usage Examples<a name="usage-examples"></a>

Once installed, you can ask Claude to:

- "Get the review comments on this PR"
- "Show me the PR feedback on #1234"
- "What comments did reviewers leave on this PR?"
- "Get review comments from user X on PR #1234"
- "Show me the human review comments (no bots)"

## Script Options<a name="script-options"></a>

The underlying script supports these options:

| Option                | Description                                              |
| --------------------- | -------------------------------------------------------- |
| `--pr <number>`       | PR number (auto-detected from current branch if omitted) |
| `--repo <owner/repo>` | Repository (auto-detected if omitted)                    |
| `--host <hostname>`   | GitHub hostname (auto-detected from git remote)          |
| `--reviewer <user>`   | Filter comments by GitHub username                       |
| `--no-bots`           | Exclude bot comments (e.g., Copilot)                     |
| `--context`           | Include diff context around each comment                 |
| `--verbose`, `-v`     | Show debug messages                                      |

## Output Format<a name="output-format"></a>

Returns a JSON array with the following fields for each comment:

- `path` - File path the comment is on
- `user` - GitHub username of the commenter
- `line` - Line number the comment is attached to
- `start_line` - Start line for multi-line comments
- `body` - The comment text
- `diff_hunk` - (with `--context`) The diff context around the comment

## Troubleshooting<a name="troubleshooting"></a>

### "gh: command not found"<a name="gh-command-not-found"></a>

Install the GitHub CLI: `brew install gh`

### Authentication errors<a name="authentication-errors"></a>

1. Run `gh auth status` to check authentication
2. For GitHub Enterprise, ensure you've authenticated with the correct hostname:
   ```bash
   gh auth login --hostname github.example.com
   ```

### "Could not detect repository"<a name="could-not-detect-repository"></a>

Run the command from within a git repository, or specify `--repo owner/repo` explicitly.

### "Could not detect PR"<a name="could-not-detect-pr"></a>

Ensure your current branch has an associated PR, or specify `--pr <number>` explicitly.

## References<a name="references"></a>

- GitHub CLI: https://cli.github.com/
