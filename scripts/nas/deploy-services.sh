#!/usr/bin/env bash
# Sync services/ to the NAS and run ~/docker/deploy.sh there. Shared by `run.py nas-deploy` and
# .github/workflows/deploy.yml so the laptop and CI cannot drift apart.
#
# Usage: NAS_HOST=<host> NAS_USER=<user> [NAS_SSH_KEY=<path>] deploy-services.sh [--dry-run] <service|all>
#
#   NAS_HOST     SSH host of the NAS (required)
#   NAS_USER     SSH user on the NAS (required)
#   NAS_SSH_KEY  private key to use, with host-key auto-accept (CI); unset to use the caller's SSH configuration
#
# rsync never deletes, and never ships *.j2 templates or .env files: secrets are rendered on the NAS by the `services`
# Ansible role, not copied from a checkout.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
services_dir="${repo}/services"

die() {
    echo "deploy-services: $*" >&2
    exit 2
}

dry_run=0
if [[ "${1:-}" == "--dry-run" ]]; then
    dry_run=1
    shift
fi
[[ $# -eq 1 ]] || die "usage: deploy-services.sh [--dry-run] <service|all>"
service="$1"

[[ -n "${NAS_HOST:-}" ]] || die "NAS_HOST is not set"
[[ -n "${NAS_USER:-}" ]] || die "NAS_USER is not set"

# A service is a directory under services/; refuse anything that could escape it or reach the remote shell
if [[ "$service" != "all" ]]; then
    [[ "$service" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid service name: ${service}"
    [[ -f "${services_dir}/${service}/compose.yml" ]] || die "no services/${service}/compose.yml"
fi

target="${NAS_USER}@${NAS_HOST}"
ssh_cmd=(ssh)
if [[ -n "${NAS_SSH_KEY:-}" ]]; then
    ssh_cmd+=(-i "$NAS_SSH_KEY" -o StrictHostKeyChecking=accept-new)
fi

rsync_flags=(-avz --exclude='*.j2' --exclude='.env')
if [[ $dry_run -eq 1 ]]; then
    rsync_flags+=(-n)
fi

push() {
    rsync "${rsync_flags[@]}" -e "${ssh_cmd[*]}" "$1" "$2"
}

if [[ "$service" == "all" ]]; then
    push "${services_dir}/" "${target}:~/docker/"
else
    push "${services_dir}/compose.base.yml" "${target}:~/docker/compose.base.yml"
    push "${services_dir}/${service}/" "${target}:~/docker/${service}/"
fi

# The tilde is deliberately unexpanded here: the remote shell expands it
# shellcheck disable=SC2088
remote="~/docker/deploy.sh ${service}"
if [[ $dry_run -eq 1 ]]; then
    echo "dry-run: would run: ${ssh_cmd[*]} ${target} ${remote}"
else
    "${ssh_cmd[@]}" "$target" "$remote"
fi
