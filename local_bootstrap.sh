#!/usr/bin/env bash

# Repo URLs
INVENTORY_REPO="git@github.com:connormason/dotfiles-inventory.git"

# Filepath
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
INVENTORY_DIR="$SCRIPT_DIR/inventory"

# Exit when any command fails
set -e

# Clone private dotfiles-inventory repo (or pull latest if we already have it
if [ ! -d "$SCRIPT_DIR/inventory" ]; then
  echo "Cloning inventory repo"
  git clone $INVENTORY_REPO $INVENTORY_DIR
else
  echo "Updating inventory repo"
  cd $INVENTORY_DIR
  git pull
  cd $SCRIPT_DIR
fi
echo ""

# Install homebrew and add to path
if ! [ -f /opt/homebrew/bin/brew/ ]; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  (echo; echo 'eval "$(/opt/homebrew/bin/brew shellenv)"') >> /Users/connormason/.zprofile
  eval "$(/opt/homebrew/bin/brew/ shellenv)"
  echo ""
fi

# Install Ansible requirements
echo "Installing Ansible requirements"
ansible-galaxy install -r roles/requirements.yml
echo ""

# Run NAS bootstrap Ansible playbook
echo "Running local bootstrap Ansible playbook"
ansible-playbook playbooks/local_bootstrap.yml -i inventory -v --ask-pass
echo ""
