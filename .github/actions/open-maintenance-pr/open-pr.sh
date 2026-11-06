#!/usr/bin/env bash
# Commit changes under PATHS to an evergreen branch and open (or refresh) a pull request for it.
#
# Environment: BRANCH PATHS TITLE BODY COMMIT_MESSAGE [BASE_BRANCH=main]
# Requires: git with push access to origin (the caller's checkout supplies the credentials) and gh with GH_TOKEN set.
#
# The job checks out BASE_BRANCH, so the new commit sits directly on top of it and the force-pushed branch is always
# exactly one commit ahead: an evergreen branch that carries only the latest automated change.
set -euo pipefail

: "${BRANCH:?BRANCH is required}"
: "${PATHS:?PATHS is required}"
: "${TITLE:?TITLE is required}"
: "${BODY:?BODY is required}"
: "${COMMIT_MESSAGE:?COMMIT_MESSAGE is required}"
BASE_BRANCH="${BASE_BRANCH:-main}"

read -r -a paths <<<"$PATHS"

if [[ -z "$(git status --porcelain -- "${paths[@]}")" ]]; then
    echo "No changes in ${PATHS}; already up to date"
    exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A -- "${paths[@]}"
git commit --quiet -m "$COMMIT_MESSAGE"
git push --force origin "HEAD:refs/heads/${BRANCH}"

number="$(gh pr list --head "$BRANCH" --base "$BASE_BRANCH" --state open --json number --jq '.[0].number // empty')"
if [[ -n "$number" ]]; then
    echo "Refreshing pull request #${number}"
    gh pr edit "$number" --title "$TITLE" --body "$BODY"
else
    echo "Opening pull request ${BRANCH} -> ${BASE_BRANCH}"
    gh pr create --base "$BASE_BRANCH" --head "$BRANCH" --title "$TITLE" --body "$BODY"
fi
