#!/usr/bin/env bash

# Exit when any command fails
set -e

# Install Ansible requirements
ansible-galaxy install -r roles/requirements.yml

# Run NAS bootstrap Ansible playbook
ansible-playbook playbooks/nas_bootstrap.yml -i inventory -v
