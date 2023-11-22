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

# Create/enter python virtual environment for installation
if [ ! -d "$SCRIPT_DIR/venv" ]; then
  echo "Creating/entering python virtual environment"
  python3 -m venv venv/
  echo ""
fi

echo "Entering python virtual environment"
source venv/bin/activate
echo ""

# Install python packages required for installation
echo "Installing Python requirements"
pip install -r requirements.txt
echo ""

# Install Ansible requirements
echo "Installing Ansible requirements"
ansible-galaxy install -r roles/requirements.yml
echo ""

# Run NAS bootstrap Ansible playbook
echo "Running NAS bootstrap Ansible playbook"
ansible-playbook playbooks/nas_bootstrap.yml -i inventory -v
echo ""
