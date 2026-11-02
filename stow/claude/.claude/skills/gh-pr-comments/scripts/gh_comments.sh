#!/usr/bin/env bash
# Get all comments from a GitHub PR
#
# Fetches all three types of PR comments from GitHub:
#   - Conversation comments (top-level discussion thread)
#   - Reviews (approve/request-changes summaries)
#   - Review comments (inline comments on diff lines)
#
# Auto-detects repo, hostname, and PR number from current directory/branch.
#
# Usage:
#   gh_comments.sh [options]
#
# Options:
#   --pr <number>       PR number (auto-detected from current branch if omitted)
#   --repo <owner/repo> Repository (auto-detected if omitted)
#   --host <hostname>   GitHub hostname (auto-detected from git remote if omitted)
#   --reviewer <user>   Filter comments by GitHub username
#   --no-bots           Exclude bot comments (e.g., Copilot)
#   --context           Include diff context around each inline comment
#   --type <type>       Comment type: all, conversation, reviews, inline (default: all)
#   --verbose, -v       Show debug messages
#
# Examples:
#   gh_comments.sh                          # All comments on current branch's PR
#   gh_comments.sh --pr 7157                # All comments on specific PR
#   gh_comments.sh --pr 7157 --no-bots      # Human comments only
#   gh_comments.sh --reviewer username      # Comments from specific user
#   gh_comments.sh --type inline --context  # Inline comments with diff context
#   gh_comments.sh --pr 123 --repo org/repo # Explicit repo and PR

set -euo pipefail

no_bots=false
reviewer=""
repo=""
pr_number=""
hostname=""
verbose=false
context=false
comment_type="all"

# Parse named arguments
while [[ $# -gt 0 ]]; do
    case $1 in
    --pr)
        pr_number="$2"
        shift 2
        ;;
    --repo)
        repo="$2"
        shift 2
        ;;
    --host)
        hostname="$2"
        shift 2
        ;;
    --reviewer)
        reviewer="$2"
        shift 2
        ;;
    --no-bots)
        no_bots=true
        shift
        ;;
    --context)
        context=true
        shift
        ;;
    --type)
        comment_type="$2"
        if [[ "$comment_type" != "all" && "$comment_type" != "conversation" && "$comment_type" != "reviews" && "$comment_type" != "inline" ]]; then
            echo "Error: --type must be one of: all, conversation, reviews, inline" >&2
            exit 1
        fi
        shift 2
        ;;
    --verbose | -v)
        verbose=true
        shift
        ;;
    --help | -h)
        sed -n '2,30p' "$0" | sed 's/^# \?//'
        exit 0
        ;;
    *)
        echo "Unknown option: $1" >&2
        echo "Use --help for usage information" >&2
        exit 1
        ;;
    esac
done

log() {
    if [ "$verbose" = true ]; then
        echo "$@" >&2
    fi
}

# Auto-detect hostname from git remote (required for GitHub Enterprise)
if [ -z "$hostname" ]; then
    remote_url=$(git remote get-url origin 2>/dev/null) || true
    if [ -n "$remote_url" ]; then
        # Extract hostname from SSH (git@host:...) or HTTPS (https://host/...) URLs
        if [[ "$remote_url" =~ ^git@ ]]; then
            hostname=$(echo "$remote_url" | sed -E 's/^git@([^:]+):.*/\1/')
        elif [[ "$remote_url" =~ ^https:// ]]; then
            hostname=$(echo "$remote_url" | sed -E 's|^https://([^/]+)/.*|\1|')
        fi
        # Only use --hostname for non-github.com hosts
        if [ "$hostname" = "github.com" ]; then
            hostname=""
        fi
    fi
fi

# Auto-detect repo if not provided
if [ -z "$repo" ]; then
    repo=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || true
    if [ -z "$repo" ]; then
        echo "Error: Could not detect repository. Use --repo <owner/repo>" >&2
        exit 1
    fi
    log "Detected repo: $repo"
fi

# Auto-detect PR number if not provided
if [ -z "$pr_number" ]; then
    pr_number=$(gh pr view --json number -q .number 2>/dev/null) || true
    if [ -z "$pr_number" ]; then
        echo "Error: Could not detect PR. Use --pr <number>" >&2
        exit 1
    fi
    log "Detected PR: #$pr_number"
fi

[ -n "$hostname" ] && log "Host: $hostname"
[ -n "$reviewer" ] && log "Reviewer: $reviewer"
[ "$no_bots" = true ] && log "Filtering: humans only"
log "Type: $comment_type"

# Build gh api command prefix (safe for arguments with spaces)
gh_api_cmd=(gh api --paginate)
if [ -n "$hostname" ]; then
    gh_api_cmd+=(--hostname "$hostname")
fi

# --- User filter (shared across all types) ---
user_filter=""
if [ "$no_bots" = true ]; then
    if [ -n "$reviewer" ]; then
        # $user is a jq variable, not a shell variable
        # shellcheck disable=SC2016
        user_filter='select(.user.type == "User" and .user.login == $user) |'
    else
        user_filter='select(.user.type == "User") |'
    fi
elif [ -n "$reviewer" ]; then
    # $user is a jq variable, not a shell variable
    # shellcheck disable=SC2016
    user_filter='select(.user.login == $user) |'
fi

run_jq() {
    local filter="$1"
    if [ -n "$reviewer" ]; then
        jq -s 'add // []' | jq --arg user "$reviewer" "$filter"
    else
        jq -s 'add // []' | jq "$filter"
    fi
}

# --- Fetch conversation comments ---
fetch_conversation() {
    log "Fetching conversation comments..."
    "${gh_api_cmd[@]}" "repos/$repo/issues/$pr_number/comments" |
        run_jq "[ .[] | $user_filter { user: .user.login, body, created_at, html_url } ]"
}

# --- Fetch reviews (only those with non-empty body) ---
fetch_reviews() {
    log "Fetching reviews..."
    # Reviews use .user for the author, same as comments
    local review_user_filter=""
    if [ "$no_bots" = true ]; then
        if [ -n "$reviewer" ]; then
            # $user is a jq variable, not a shell variable
            # shellcheck disable=SC2016
            review_user_filter='select(.user.type == "User" and .user.login == $user) |'
        else
            review_user_filter='select(.user.type == "User") |'
        fi
    elif [ -n "$reviewer" ]; then
        # $user is a jq variable, not a shell variable
        # shellcheck disable=SC2016
        review_user_filter='select(.user.login == $user) |'
    fi

    "${gh_api_cmd[@]}" "repos/$repo/pulls/$pr_number/reviews" |
        run_jq "[ .[] | select(.body | length > 0) | $review_user_filter { id, user: .user.login, state, body, submitted_at } ]"
}

# --- Fetch inline review comments ---
fetch_inline() {
    log "Fetching inline review comments..."
    local fields
    if [ "$context" = true ]; then
        fields="{ path, user: .user.login, line, start_line, diff_hunk, body, created_at, review_id: .pull_request_review_id, in_reply_to_id }"
    else
        fields="{ path, user: .user.login, line, start_line, body, created_at, review_id: .pull_request_review_id, in_reply_to_id }"
    fi

    "${gh_api_cmd[@]}" "repos/$repo/pulls/$pr_number/comments" |
        run_jq "[ .[] | $user_filter $fields ]"
}

# --- Build consolidated output ---
case "$comment_type" in
all)
    conversation=$(fetch_conversation)
    reviews=$(fetch_reviews)
    inline=$(fetch_inline)
    jq -n \
        --argjson conversation "$conversation" \
        --argjson reviews "$reviews" \
        --argjson review_comments "$inline" \
        '{ conversation: $conversation, reviews: $reviews, review_comments: $review_comments }'
    ;;
conversation)
    fetch_conversation
    ;;
reviews)
    fetch_reviews
    ;;
inline)
    fetch_inline
    ;;
esac
