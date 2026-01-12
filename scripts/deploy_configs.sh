#!/usr/bin/env bash

# Deploy all configuration files (tasks tagged with "configfile")
ansible-playbook playbooks/nas_bootstrap.yml -i inventory --tags configfile
