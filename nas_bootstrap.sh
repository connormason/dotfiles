#!/usr/bin/env bash

# Color definitions
NC="\033[0m"
YELLOW="\033[0;33m"
GREEN="\033[0;32m"
RED="\033[0;31m"

# Exit when any command fails
set -e

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOTFILES_DIR="${SCRIPT_DIR}"

# Validate we're in the right place by checking for required files/directories
if [[ ! -f "${DOTFILES_DIR}/run.py" ]] ||
    [[ ! -f "${DOTFILES_DIR}/nas_bootstrap.sh" ]] ||
    [[ ! -d "${DOTFILES_DIR}/playbooks" ]]; then
    echo -e "${RED}ERROR: This doesn't appear to be the dotfiles directory!${NC}"
    echo -e "${RED}Expected to find: run.py, nas_bootstrap.sh, playbooks/${NC}"
    echo -e "${RED}Current directory: ${DOTFILES_DIR}${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Validated dotfiles directory: ${DOTFILES_DIR}${NC}"

# Install homebrew with checksum verification
if [[ ! $(command -v brew) ]]; then
    echo -e "Installing Homebrew..."

    # Download installer and verify checksum before execution
    BREW_INSTALLER="$(mktemp "${TMPDIR:-/tmp}/brew-install.XXXXXX")"
    trap 'rm -f "$BREW_INSTALLER"' EXIT
    # Pinned to an upstream commit so the content cannot drift when Homebrew edits install.sh on HEAD
    curl -fsSL https://raw.githubusercontent.com/Homebrew/install/09c62fc577ec170172b0a184060f141a2c622dc1/install.sh -o "$BREW_INSTALLER"

    # Expected checksum of the installer at the commit-pinned URL above
    # To update: pick a commit SHA from https://github.com/Homebrew/install/commits/HEAD/install.sh, put it in the URL
    # above (and in bootstrap/50-brew.sh), then edit EXPECTED_CHECKSUM in nas_bootstrap.sh to the SHA-256 of that URL:
    #   curl -fsSL <installer URL> | shasum -a 256
    # Last updated: 2026-10-30
    EXPECTED_CHECKSUM="5f333bbe53bc490e51e7ccb1df8779b3dd6ee73a1a7379efda216edb08ccb148" # pragma: allowlist secret

    # Verify checksum
    ACTUAL_CHECKSUM=$(shasum -a 256 "$BREW_INSTALLER" | awk '{print $1}')
    if [ "$ACTUAL_CHECKSUM" != "$EXPECTED_CHECKSUM" ]; then
        echo -e "${YELLOW}WARNING: Homebrew installer checksum mismatch!${NC}"
        echo -e "Expected: $EXPECTED_CHECKSUM"
        echo -e "Actual:   $ACTUAL_CHECKSUM"
        echo -e ""
        echo -e "This could indicate:"
        echo -e "  1. The Homebrew installer has been updated (normal)"
        echo -e "  2. A security issue (man-in-the-middle attack, DNS hijacking)"
        echo -e ""
        echo -e "To proceed safely:"
        echo -e "  1. Verify the new checksum at https://github.com/Homebrew/install"
        echo -e "  2. Update EXPECTED_CHECKSUM in nas_bootstrap.sh"
        echo -e "  3. Re-run this script"
        exit 1
    fi

    echo -e "${GREEN}✓ Checksum verified${NC}"

    # Execute verified installer
    /bin/bash "$BREW_INSTALLER"

    # Cleanup
    rm -f "$BREW_INSTALLER"
fi

# Install ansible
export PATH="/opt/homebrew/bin:$PATH"
if [[ ! $(command -v ansible-playbook) ]]; then
    echo -e "Installing ansible..."
    brew install ansible
fi

# Run ansible playbook
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv

echo -e "${GREEN}Bootstrapping completed${NC}"
