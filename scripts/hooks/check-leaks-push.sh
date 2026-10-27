#!/usr/bin/env bash
# pre-push leak scan of the commits being pushed: author/committer identities and commit messages.
#
# cherry-pick, rebase, am, and `git commit --no-verify` bypass the pre-commit and commit-msg hooks, so this is the
# last local gate before content becomes public. File contents in the pushed range are scanned by the separate
# check-leaks pre-push hook entry. Range: PRE_COMMIT_FROM_REF..PRE_COMMIT_TO_REF when the from-ref exists locally;
# otherwise merge-base(to, origin/main)..to; otherwise the tip commit only.
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
trap 'rm -f "$msgs"' EXIT
git log --format=%B "${range[@]}" >"$msgs"
git log --format='%an <%ae>%n%cn <%ce>' "${range[@]}" |
    "$here/check-leaks.py" --identities-from - "$msgs"
