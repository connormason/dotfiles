#!/usr/bin/env bash
# Provision the home NAS from this machine: a thin wrapper over `run.py nas-provision`, which holds the preflight
# checks and the playbook run. Options pass straight through (see `run.py nas-provision --help`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Validate we're in the right place by checking for required files/directories
if [[ ! -f "${SCRIPT_DIR}/run.py" ]] ||
    [[ ! -f "${SCRIPT_DIR}/nas_bootstrap.sh" ]] ||
    [[ ! -d "${SCRIPT_DIR}/playbooks" ]]; then
    echo "ERROR: This doesn't appear to be the dotfiles directory!" >&2
    echo "Expected to find run.py, nas_bootstrap.sh, and playbooks/ in ${SCRIPT_DIR}" >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv is required to run the Ansible tooling but was not found on PATH." >&2
    echo "Install it (https://docs.astral.sh/uv/getting-started/installation/) and re-run." >&2
    exit 1
fi

exec "${SCRIPT_DIR}/scripts/hooks/uv-public.sh" run python "${SCRIPT_DIR}/run.py" nas-provision "$@"
