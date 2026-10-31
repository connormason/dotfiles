#!/usr/bin/env bash
# Lint the NAS playbook and roles with ansible-lint (check only: never --fix). Used by the prek hook and the CI job.
#
# ansible.cfg points vault_password_file at vault_password.txt, which exists only on a provisioning machine; without it
# ansible-lint's syntax check aborts. A throwaway password file stands in, since linting decrypts nothing. --offline
# keeps ansible-lint from installing collections itself: install them first with
#   scripts/hooks/uv-public.sh run ansible-galaxy collection install -r roles/requirements.yml
set -euo pipefail

ANSIBLE_LINT_VERSION="25.6.1"

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$repo"

vault_pass="$(mktemp "${TMPDIR:-/tmp}/ansible-lint-vault.XXXXXX")"
trap 'rm -f "$vault_pass"' EXIT
printf 'unused\n' >"$vault_pass"

ANSIBLE_VAULT_PASSWORD_FILE="$vault_pass" "$repo/scripts/hooks/uv-public.sh" tool run \
    --from "ansible-lint==${ANSIBLE_LINT_VERSION}" ansible-lint --offline playbooks/ roles/ "$@"
