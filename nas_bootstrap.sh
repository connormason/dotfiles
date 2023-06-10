#!/usr/bin/env bash

# Exit when any command fails
set -e

# Run NAS bootstrap Ansible playbook
ansible-playbook playbooks/nas_bootstrap.yml -i inventory
