#!/usr/bin/env bash
# 20-ssh-key: ensure an SSH keypair exists and is registered with GitHub.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh disable=SC1091
source "$HERE/lib.sh"

SSH_DIR="$HOME/.ssh"
KEY="$SSH_DIR/id_ed25519"
GITHUB="git@github.com"

run mkdir -p "$SSH_DIR"
run chmod 700 "$SSH_DIR"

# If SSH auth to GitHub already works, we are done.
# `ssh -T` to GitHub exits non-zero even on success ("does not provide shell access"), and we run under
# `set -o pipefail`, so capture the output first rather than piping ssh into grep (ssh's non-zero exit would mask a
# successful match). A dry run must not write known_hosts, so it probes with a throwaway known-hosts file.
probe_opts=(-o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=10)
if [ "${BOOTSTRAP_DRY_RUN}" = "1" ]; then
    probe_opts+=(-o UserKnownHostsFile=/dev/null)
fi
auth_out="$(ssh "${probe_opts[@]}" -T "$GITHUB" 2>&1 || true)"
if printf '%s' "$auth_out" | grep -qi "successfully authenticated\|does not provide shell"; then
    log "SSH auth to github.com already works"
    exit 0
fi

if [ ! -f "$KEY" ] && [ ! -f "$SSH_DIR/id_rsa" ]; then
    log "generating ed25519 SSH key"
    run ssh-keygen -t ed25519 -f "$KEY" -N "" -C "$(whoami)@$(hostname)"
fi

pub="${KEY}.pub"
if [ ! -f "$pub" ] && [ -f "$SSH_DIR/id_rsa.pub" ]; then
    pub="$SSH_DIR/id_rsa.pub"
fi
log "register this public key with GitHub (https://github.com/settings/ssh/new):"
if [ -f "$pub" ]; then
    cat "$pub"
fi
log "or, once gh is installed and authenticated (stage 50-brew): gh ssh-key add $pub"
warn "after registering, verify with: ssh -T $GITHUB"

if [ "${BOOTSTRAP_DRY_RUN}" != "1" ]; then
    confirm "Has the key been registered and verified?" || die "register the SSH key, then re-run --from 20-ssh-key"
fi
log "ssh-key OK"
