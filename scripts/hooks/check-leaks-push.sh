#!/usr/bin/env bash
# pre-push leak scan of the commits being pushed: author/committer identities, commit messages, and every line the
# pushed commits add.
#
# cherry-pick, rebase, am, and `git commit --no-verify` bypass the pre-commit and commit-msg hooks, so this is the
# last local gate before content becomes public. The separate check-leaks pre-push hook entry scans the files changed in
# the range as they are at the tip; the patch scan here also catches content that one pushed commit adds and a later one
# removes (the tip is clean, but the commit still publishes it). Only added lines are scanned: a removed line is either
# added earlier in the same range (and caught there) or already public. The paths each commit adds, copies, or renames
# to are appended to the scanned patch, since a leak that lives only in a path (an empty file, a pure rename) has no
# added line. Merge commits are diffed with --cc so a leak introduced by a conflict resolution is seen. Range: PRE_COMMIT_FROM_REF..PRE_COMMIT_TO_REF
# when the from-ref exists locally; otherwise merge-base(to, origin/main)..to; otherwise the tip commit only.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
to="${PRE_COMMIT_TO_REF:-HEAD}"
from="${PRE_COMMIT_FROM_REF:-}"

range=()
if [ -n "$from" ] && git cat-file -e "$from^{commit}" 2>/dev/null; then
    range=("$from..$to")
elif base="$(git merge-base "$to" origin/main 2>/dev/null)"; then
    range=("$base..$to")
else
    range=(-1 "$to")
fi

msgs="$(mktemp "${TMPDIR:-/tmp}/check-leaks-msgs.XXXXXX")"
patch="$(mktemp "${TMPDIR:-/tmp}/check-leaks-patch.XXXXXX")"
trap 'rm -f "$msgs" "$patch"' EXIT

# Findings name the temp patch file, so point at the matching git commands: blanking (not deleting) every line that is
# neither a commit header nor an added line keeps line numbers aligned with the first command's output; the path listing
# of the second command follows it. The awk pattern also admits --cc's "++" / " +" added-line prefixes.
echo "pre-push: scanning ${range[*]}"
git log --format=%B "${range[@]}" >"$msgs"
git log -p -U0 --cc --no-textconv --format='commit %h' --no-color "${range[@]}" |
    awk '/^commit / || /^[ +]?\+/ { print; next } { print "" }' >"$patch"
git log --name-only --diff-filter=ACR --cc --no-textconv --format='commit %h' --no-color "${range[@]}" >>"$patch"

rc=0
git log --format='%an <%ae>%n%cn <%ce>' "${range[@]}" |
    "$here/check-leaks.py" --identities-from - "$msgs" "$patch" || rc=$?
if [ "$rc" -ne 0 ]; then
    echo "pre-push: inspect with: git log -p -U0 --cc --no-textconv --format='commit %h' --no-color ${range[*]}"
    echo "pre-push: and (paths):  git log --name-only --diff-filter=ACR --cc --format='commit %h' --no-color ${range[*]}"
fi
exit "$rc"
