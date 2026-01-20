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
HOME_DIR=$HOME
USERNAME=$(whoami)

# Validate we're in the right place by checking for required files/directories
if [[ ! -f "${DOTFILES_DIR}/run.py" ]] || \
   [[ ! -f "${DOTFILES_DIR}/nas_bootstrap.sh" ]] || \
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
    BREW_INSTALLER="/tmp/brew-install.sh"
    curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$BREW_INSTALLER"

    # Expected checksum - update when Homebrew installer changes
    # To update: curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | shasum -a 256
    # Last updated: 2026-01-11
    EXPECTED_CHECKSUM="b2ffbf7e7f451c6db3b5d1976fc6a9c2faecf58ee5e1dbf6e498643c91f0d3bc"

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
        echo -e "  2. Update EXPECTED_CHECKSUM in bootstrap.sh"
        echo -e "  3. Re-run this script"
        rm -f "$BREW_INSTALLER"
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
