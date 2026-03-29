# Tailscale Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up a self-contained Ansible role for Tailscale on NAS (Debian) and Mac (macOS) with HTTPS reverse proxy via Caddy for Docker services.

**Architecture:** A single `roles/tailscale` role with platform-aware task files dispatched by OS family. Debian tasks handle apt repo/package/systemd. macOS tasks verify brew cask. Shared configuration task uses `tailscale set` + `tailscale login` for idempotency. HTTPS cert provisioning and Caddy reverse proxy are NAS-only, gated by a variable.

**Tech Stack:** Ansible, Tailscale, Caddy, Docker Compose, systemd, Jinja2 templates

**Spec:** `.claude/specs/2026-03-29-tailscale-setup-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `roles/tailscale/defaults/main.yml` | Create | All default variables for the role |
| `roles/tailscale/tasks/main.yml` | Rewrite | Auth key validation, OS detection, dispatch to install/configure/https tasks |
| `roles/tailscale/tasks/install_debian.yml` | Create | Add Tailscale GPG key, apt repo, install package, enable service |
| `roles/tailscale/tasks/install_macos.yml` | Create | Verify Tailscale brew cask is present |
| `roles/tailscale/tasks/configure.yml` | Create | `tailscale set` flags + idempotent `tailscale login` |
| `roles/tailscale/tasks/https_certs.yml` | Create | Cert provisioning, Caddyfile deployment, systemd timer |
| `roles/tailscale/handlers/main.yml` | Create | Restart tailscaled handler |
| `roles/tailscale/templates/Caddyfile.j2` | Create | Caddy reverse proxy config with path-based + dedicated port routing |
| `roles/tailscale/templates/tailscale-cert-renewal.service.j2` | Create | Systemd service: run `tailscale cert` then reload Caddy |
| `roles/tailscale/templates/tailscale-cert-renewal.timer.j2` | Create | Systemd weekly timer for cert renewal |
| `roles/tailscale/README.md` | Rewrite | Setup guide and documentation |
| `roles/docker/files/docker-compose.yml` | Edit | Add Caddy service, move Plex to bridge networking |
| `playbooks/nas_bootstrap.yml` | Edit | Uncomment tailscale role |
| `playbooks/local_bootstrap.yml` | Edit | Add tailscale role |
| `roles/requirements.yml` | Edit | Remove `artis3n.tailscale` dependency |

---

### Task 1: Role defaults and handlers

**Files:**
- Create: `roles/tailscale/defaults/main.yml`
- Create: `roles/tailscale/handlers/main.yml`

- [ ] **Step 1: Create defaults/main.yml**

```yaml
---
# Authentication
tailscale_auth_key: ""                          # Override in vault — role fails if empty

# Node configuration
tailscale_hostname: "{{ inventory_hostname }}"
tailscale_ssh_enabled: true
tailscale_accept_dns: true

# HTTPS (NAS only)
tailscale_https_enabled: false
tailscale_tailnet_name: ""                      # e.g., "tail1234.ts.net"
tailscale_cert_dir: "/etc/tailscale/certs"
tailscale_caddy_config_dir: "/etc/caddy"
tailscale_services: []                          # List of {name, port, path} dicts
tailscale_plex_port: 32443                      # Dedicated Caddy port for Plex

# Platform
tailscale_version: ""                           # Empty = latest available
tailscale_macos_cli: "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
```

- [ ] **Step 2: Create handlers/main.yml**

```yaml
---
- name: Restart tailscaled
  become: true
  ansible.builtin.systemd:
    name: tailscaled
    state: restarted
    enabled: true
  when: ansible_os_family == "Debian"
```

- [ ] **Step 3: Commit**

```bash
git add roles/tailscale/defaults/main.yml roles/tailscale/handlers/main.yml
git commit -m "feat(tailscale): add role defaults and handlers"
```

---

### Task 2: Main entry point with validation and OS dispatch

**Files:**
- Rewrite: `roles/tailscale/tasks/main.yml`

- [ ] **Step 1: Rewrite main.yml**

Replace the existing content (which delegates to `artis3n.tailscale`) with:

```yaml
---
- name: Validate tailscale_auth_key is set
  ansible.builtin.assert:
    that:
      - tailscale_auth_key | length > 0
    fail_msg: >
      tailscale_auth_key is empty. Generate a reusable auth key in the Tailscale admin console
      and add it to your Ansible Vault (inventory/group_vars/all/vault.yml).

- name: Install Tailscale (Debian)
  ansible.builtin.include_tasks: install_debian.yml
  when: ansible_os_family == "Debian"

- name: Install Tailscale (macOS)
  ansible.builtin.include_tasks: install_macos.yml
  when: ansible_os_family == "Darwin"

- name: Configure Tailscale
  ansible.builtin.include_tasks: configure.yml

- name: Set up HTTPS certs and Caddy
  ansible.builtin.include_tasks: https_certs.yml
  when: tailscale_https_enabled
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('roles/tailscale/tasks/main.yml'))"`
Expected: No output (valid YAML)

- [ ] **Step 3: Commit**

```bash
git add roles/tailscale/tasks/main.yml
git commit -m "feat(tailscale): rewrite main.yml with validation and OS dispatch"
```

---

### Task 3: Debian installation tasks

**Files:**
- Create: `roles/tailscale/tasks/install_debian.yml`

- [ ] **Step 1: Create install_debian.yml**

```yaml
---
- name: Install apt-transport-https
  become: true
  ansible.builtin.apt:
    name: apt-transport-https
    state: present

- name: Add Tailscale GPG signing key
  become: true
  ansible.builtin.get_url:
    url: "https://pkgs.tailscale.com/stable/debian/{{ ansible_distribution_release }}.noarmor.gpg"
    dest: /usr/share/keyrings/tailscale-archive-keyring.gpg
    mode: "0644"

- name: Add Tailscale apt repository
  become: true
  ansible.builtin.apt_repository:
    repo: >-
      deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg]
      https://pkgs.tailscale.com/stable/debian {{ ansible_distribution_release }} main
    filename: tailscale
    state: present

- name: Install Tailscale package
  become: true
  ansible.builtin.apt:
    name: "{{ 'tailscale=' + tailscale_version + '*' if tailscale_version else 'tailscale' }}"
    state: present
    update_cache: true

- name: Enable and start tailscaled
  become: true
  ansible.builtin.systemd:
    name: tailscaled
    state: started
    enabled: true
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('roles/tailscale/tasks/install_debian.yml'))"`
Expected: No output (valid YAML)

- [ ] **Step 3: Commit**

```bash
git add roles/tailscale/tasks/install_debian.yml
git commit -m "feat(tailscale): add Debian install tasks (apt repo, package, systemd)"
```

---

### Task 4: macOS installation tasks

**Files:**
- Create: `roles/tailscale/tasks/install_macos.yml`

- [ ] **Step 1: Create install_macos.yml**

```yaml
---
- name: Check if Tailscale is installed
  ansible.builtin.stat:
    path: "{{ tailscale_macos_cli }}"
  register: tailscale_app

- name: Ensure Tailscale is installed via brew cask
  community.general.homebrew_cask:
    name: tailscale
    state: present
  when: not tailscale_app.stat.exists

- name: Remind user to launch Tailscale GUI
  ansible.builtin.debug:
    msg: >
      If this is a fresh install, open Tailscale.app at least once to set up the
      system extension before the CLI will work.
  when: not tailscale_app.stat.exists
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('roles/tailscale/tasks/install_macos.yml'))"`
Expected: No output (valid YAML)

- [ ] **Step 3: Commit**

```bash
git add roles/tailscale/tasks/install_macos.yml
git commit -m "feat(tailscale): add macOS install tasks (brew cask check)"
```

---

### Task 5: Configuration tasks (tailscale set + login)

**Files:**
- Create: `roles/tailscale/tasks/configure.yml`

- [ ] **Step 1: Create configure.yml**

```yaml
---
- name: Set Tailscale CLI path
  ansible.builtin.set_fact:
    _tailscale_cli: "{{ tailscale_macos_cli if ansible_os_family == 'Darwin' else 'tailscale' }}"

- name: Build tailscale set arguments
  ansible.builtin.set_fact:
    _tailscale_set_args: >-
      --hostname={{ tailscale_hostname }}
      --accept-dns={{ "true" if tailscale_accept_dns else "false" }}
      {{ '--ssh' if tailscale_ssh_enabled and ansible_os_family == 'Debian' else '' }}

- name: Apply Tailscale configuration
  become: "{{ ansible_os_family == 'Debian' }}"
  ansible.builtin.command:
    cmd: "{{ _tailscale_cli }} set {{ _tailscale_set_args }}"
  changed_when: false

- name: Check Tailscale backend state
  become: "{{ ansible_os_family == 'Debian' }}"
  ansible.builtin.command:
    cmd: "{{ _tailscale_cli }} status --json"
  register: tailscale_status
  changed_when: false
  failed_when: false

- name: Parse Tailscale backend state
  ansible.builtin.set_fact:
    _tailscale_backend_state: "{{ (tailscale_status.stdout | from_json).BackendState | default('NeedsLogin') }}"

- name: Authenticate with Tailscale
  become: "{{ ansible_os_family == 'Debian' }}"
  ansible.builtin.command:
    cmd: "{{ _tailscale_cli }} login --authkey={{ tailscale_auth_key }}"
  when: _tailscale_backend_state != "Running"
  no_log: true
  changed_when: true
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('roles/tailscale/tasks/configure.yml'))"`
Expected: No output (valid YAML)

- [ ] **Step 3: Commit**

```bash
git add roles/tailscale/tasks/configure.yml
git commit -m "feat(tailscale): add configuration tasks (set + idempotent login)"
```

---

### Task 6: Caddyfile template

**Files:**
- Create: `roles/tailscale/templates/Caddyfile.j2`

- [ ] **Step 1: Create Caddyfile.j2**

```
# Tailscale HTTPS reverse proxy for NAS services
# Generated by Ansible — do not edit manually

# Path-based services on :443
https://{{ tailscale_hostname }}.{{ tailscale_tailnet_name }} {
    tls /certs/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.crt /certs/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.key

{% for svc in tailscale_services if svc.dedicated_port is not defined and svc.name != 'pihole' %}
{% if svc.strip_prefix | default(false) %}
    handle_path /{{ svc.path }}/* {
        reverse_proxy {{ svc.name }}:{{ svc.port }}
    }
{% else %}
    handle /{{ svc.path }}/* {
        reverse_proxy {{ svc.name }}:{{ svc.port }}
    }
{% endif %}

{% endfor %}
    # PiHole: strip /pihole prefix, rewrite to /admin
    handle_path /pihole/* {
        rewrite * /admin{uri}
        reverse_proxy pihole:80
    }
}

{% for svc in tailscale_services if svc.dedicated_port is defined %}
# {{ svc.name | capitalize }} on dedicated port :{{ svc.dedicated_port }}
https://{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}:{{ svc.dedicated_port }} {
    tls /certs/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.crt /certs/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.key
    reverse_proxy {{ svc.name }}:{{ svc.port }}
}

{% endfor %}
```

**Note:** The `{uri}` in the PiHole rewrite is a Caddy placeholder (not Jinja2). It works because Jinja2 only interprets `{{ }}` with spaces, and `{uri}` has no spaces so it passes through as-is.

- [ ] **Step 2: Commit**

```bash
git add roles/tailscale/templates/Caddyfile.j2
git commit -m "feat(tailscale): add Caddyfile Jinja2 template"
```

---

### Task 7: Systemd cert renewal templates

**Files:**
- Create: `roles/tailscale/templates/tailscale-cert-renewal.service.j2`
- Create: `roles/tailscale/templates/tailscale-cert-renewal.timer.j2`

- [ ] **Step 1: Create tailscale-cert-renewal.service.j2**

```ini
# Tailscale HTTPS cert renewal service
# Generated by Ansible — do not edit manually

[Unit]
Description=Renew Tailscale HTTPS certificates
After=tailscaled.service
Requires=tailscaled.service

[Service]
Type=oneshot
ExecStart=/usr/bin/tailscale cert --cert-file {{ tailscale_cert_dir }}/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.crt --key-file {{ tailscale_cert_dir }}/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.key {{ tailscale_hostname }}.{{ tailscale_tailnet_name }}
ExecStartPost=/usr/bin/docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

- [ ] **Step 2: Create tailscale-cert-renewal.timer.j2**

```ini
# Tailscale HTTPS cert renewal timer (weekly)
# Generated by Ansible — do not edit manually

[Unit]
Description=Weekly Tailscale HTTPS certificate renewal

[Timer]
OnCalendar=weekly
Persistent=true
RandomizedDelaySec=3600

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Commit**

```bash
git add roles/tailscale/templates/tailscale-cert-renewal.service.j2 roles/tailscale/templates/tailscale-cert-renewal.timer.j2
git commit -m "feat(tailscale): add systemd cert renewal service and timer templates"
```

---

### Task 8: HTTPS certs and Caddy deployment tasks

**Files:**
- Create: `roles/tailscale/tasks/https_certs.yml`

- [ ] **Step 1: Create https_certs.yml**

```yaml
---
- name: Create cert directory
  become: true
  ansible.builtin.file:
    path: "{{ tailscale_cert_dir }}"
    state: directory
    mode: "0755"

- name: Create Caddy config directory
  become: true
  ansible.builtin.file:
    path: "{{ tailscale_caddy_config_dir }}"
    state: directory
    mode: "0755"

- name: Provision Tailscale HTTPS certs
  become: true
  ansible.builtin.command:
    cmd: >-
      tailscale cert
      --cert-file {{ tailscale_cert_dir }}/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.crt
      --key-file {{ tailscale_cert_dir }}/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.key
      {{ tailscale_hostname }}.{{ tailscale_tailnet_name }}
    creates: "{{ tailscale_cert_dir }}/{{ tailscale_hostname }}.{{ tailscale_tailnet_name }}.crt"

- name: Deploy Caddyfile
  become: true
  ansible.builtin.template:
    src: Caddyfile.j2
    dest: "{{ tailscale_caddy_config_dir }}/Caddyfile"
    mode: "0644"

- name: Deploy cert renewal systemd service
  become: true
  ansible.builtin.template:
    src: tailscale-cert-renewal.service.j2
    dest: /etc/systemd/system/tailscale-cert-renewal.service
    mode: "0644"

- name: Deploy cert renewal systemd timer
  become: true
  ansible.builtin.template:
    src: tailscale-cert-renewal.timer.j2
    dest: /etc/systemd/system/tailscale-cert-renewal.timer
    mode: "0644"

- name: Enable and start cert renewal timer
  become: true
  ansible.builtin.systemd:
    name: tailscale-cert-renewal.timer
    state: started
    enabled: true
    daemon_reload: true
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('roles/tailscale/tasks/https_certs.yml'))"`
Expected: No output (valid YAML)

- [ ] **Step 3: Commit**

```bash
git add roles/tailscale/tasks/https_certs.yml
git commit -m "feat(tailscale): add HTTPS cert provisioning and Caddy deployment tasks"
```

---

### Task 9: Docker compose changes (Caddy + Plex bridge)

**Files:**
- Modify: `roles/docker/files/docker-compose.yml`

- [ ] **Step 1: Replace the commented-out Caddy service**

In `roles/docker/files/docker-compose.yml`, find the commented-out Caddy block (lines 9-22) and replace it with:

```yaml
  # Caddy - Reverse proxy for Tailscale HTTPS access to services
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "443:443"
      - "32443:32443"
    volumes:
      - /etc/tailscale/certs:/certs:ro
      - /etc/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
```

- [ ] **Step 2: Move Plex from host to bridge networking**

In the Plex service block:
- Remove `network_mode: host` and its `# TODO: Temporary for docker/plex weirdness` comment
- Add a `ports` section
- Add `ADVERTISE_IP` to environment (reads from host env / `.env` file)

The Plex service should become:

```yaml
  # Plex
  plex:
    image: linuxserver/plex
    container_name: plex
    environment:
      - PUID=1000
      - PGID=1000
      - VERSION=docker
      - ADVERTISE_IP
    ports:
      - "32400:32400"
    volumes:
      - /storage/media/config/plex:/config
      - /storage/media/tv:/tv
      - /storage/media/movies:/movies
      - /storage/media/music:/music
    restart: unless-stopped
```

**Note:** `- ADVERTISE_IP` (with no `=`) reads the value from the host environment or the Docker `.env` file. The user must set `ADVERTISE_IP=https://nas.<tailnet>.ts.net:32443` in the `.env` file after deployment. This matches the existing pattern used for `FTLCONF_webserver_api_password` (PiHole).

Also verify the existing `caddy_data: {}` at the bottom of the file's `volumes:` section is still present — do not remove or duplicate it.

- [ ] **Step 3: Verify the compose file is valid YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('roles/docker/files/docker-compose.yml'))"`
Expected: No output (valid YAML)

- [ ] **Step 4: Commit**

```bash
git add roles/docker/files/docker-compose.yml
git commit -m "feat(docker): add Caddy service, move Plex to bridge networking"
```

---

### Task 10: Playbook integration

**Files:**
- Modify: `playbooks/nas_bootstrap.yml`
- Modify: `playbooks/local_bootstrap.yml`
- Modify: `roles/requirements.yml`

- [ ] **Step 1: Uncomment tailscale role in nas_bootstrap.yml**

In `playbooks/nas_bootstrap.yml`, uncomment lines 86-92 so the tailscale block looks like:

```yaml
    # Tasks for Tailscale configuration
    - include_role:
        name: roles/tailscale
        apply:
          tags: tailscale
      tags:
        - tailscale
        - configfile
```

- [ ] **Step 2: Add tailscale role to local_bootstrap.yml**

In `playbooks/local_bootstrap.yml`, add after the python role block (after line 106):

```yaml

    # Tasks for Tailscale configuration
    - include_role:
        name: roles/tailscale
        apply:
          tags: tailscale
      tags:
        - tailscale
```

- [ ] **Step 3: Remove artis3n.tailscale from requirements.yml**

In `roles/requirements.yml`, remove the line `  - name: artis3n.tailscale` from the roles section.

The file should become:

```yaml
---
roles:
  - name: elliotweiser.osx-command-line-tools

collections:
  - name: ansible.posix
  - name: community.general
  - name: geerlingguy.mac
```

- [ ] **Step 4: Verify YAML syntax for all changed files**

Run: `python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['playbooks/nas_bootstrap.yml', 'playbooks/local_bootstrap.yml', 'roles/requirements.yml']]"`
Expected: No output (valid YAML)

- [ ] **Step 5: Commit**

```bash
git add playbooks/nas_bootstrap.yml playbooks/local_bootstrap.yml roles/requirements.yml
git commit -m "feat: integrate tailscale role into both playbooks, remove Galaxy dependency"
```

---

### Task 11: Inventory variable configuration

**Files:**
- Edit: `inventory/group_vars/all/vault.yml` (encrypted, separate repo)
- Edit: `inventory/host_vars/nas/vars.yml` (separate repo)

**Note:** The `inventory/` directory is a separate git repo cloned into this project (not a submodule). These files cannot be committed to the main dotfiles repo. The inventory must be set up first via `python3 run.py update-inventory`.

- [ ] **Step 1: Add Tailscale variables to shared vault**

Run: `ansible-vault edit inventory/group_vars/all/vault.yml`

Add these variables (replace with your actual values):

```yaml
tailscale_auth_key: "tskey-auth-XXXXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
tailscale_tailnet_name: "your-tailnet.ts.net"
```

To find your tailnet name: visit [Tailscale admin console](https://login.tailscale.com/admin/settings/general) > Settings > General > "Tailnet name".

- [ ] **Step 2: Add NAS-specific variables**

Edit `inventory/host_vars/nas/vars.yml` and add:

```yaml
tailscale_https_enabled: true
tailscale_services:
  - { name: sonarr, port: 8989, path: sonarr }
  - { name: radarr, port: 7878, path: radarr }
  - { name: transmission, port: 9091, path: transmission }
  - { name: prowlarr, port: 9696, path: prowlarr }
  - { name: pihole, port: 80, path: pihole }
  - { name: glance, port: 8080, path: glance, strip_prefix: true }
  - { name: plex, port: 32400, dedicated_port: 32443 }
```

- [ ] **Step 3: Commit inventory changes**

```bash
cd inventory && git add -A && git commit -m "feat: add Tailscale variables for NAS" && cd ..
```

---

### Task 12: README documentation

**Files:**
- Rewrite: `roles/tailscale/README.md`

- [ ] **Step 1: Rewrite README.md**

```markdown
# tailscale

Sets up [Tailscale VPN](https://tailscale.com/) on Debian and macOS systems.

## Features

- Installs Tailscale from official apt repository (Debian) or verifies brew cask (macOS)
- Configures Tailscale with idempotent `tailscale set` + `tailscale login`
- Enables Tailscale SSH on Linux hosts
- Provisions HTTPS certificates via `tailscale cert` (NAS only)
- Deploys Caddy reverse proxy for Docker services (NAS only)
- Automatic weekly cert renewal via systemd timer

## Prerequisites

1. **Tailscale account** with a tailnet configured
2. **Reusable auth key** generated in [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)
   - Note: Reusable auth keys expire after ~90 days and must be regenerated
3. **HTTPS certificates enabled** in Tailscale admin console (for HTTPS feature)
4. **macOS only:** Launch Tailscale.app at least once to set up the system extension

## Required Variables

Set these in your Ansible Vault (`inventory/group_vars/all/vault.yml`):

```yaml
tailscale_auth_key: "tskey-auth-..."
tailscale_tailnet_name: "your-tailnet.ts.net"
```

## Optional Variables

See `defaults/main.yml` for all available variables and their defaults.

Key overrides for NAS (`inventory/host_vars/nas/vars.yml`):

```yaml
tailscale_https_enabled: true
tailscale_services:
  - { name: sonarr, port: 8989, path: sonarr }
  - { name: radarr, port: 7878, path: radarr }
  - { name: transmission, port: 9091, path: transmission }
  - { name: prowlarr, port: 9696, path: prowlarr }
  - { name: pihole, port: 80, path: pihole }
  - { name: glance, port: 8080, path: glance, strip_prefix: true }
  - { name: plex, port: 32400, dedicated_port: 32443 }
```

## Service Routing

Services are accessible via `https://nas.<tailnet>.ts.net/<path>`:

| Service | URL | Notes |
|---|---|---|
| Sonarr | `/sonarr` | Requires `UrlBase = /sonarr` in app settings |
| Radarr | `/radarr` | Requires `UrlBase = /radarr` in app settings |
| Prowlarr | `/prowlarr` | Requires `UrlBase = /prowlarr` in app settings |
| Transmission | `/transmission` | Requires `rpc-url = /transmission/` in settings.json |
| PiHole | `/pihole` | Automatically rewrites to `/admin` |
| Glance | `/glance` | No app config needed |
| Plex | `:32443` (dedicated port) | Access via `https://nas.<tailnet>.ts.net:32443` |

## Post-Deployment Steps

After first playbook run:

1. Set URL base paths in each service's web UI (see table above)
2. Set `ADVERTISE_IP=https://nas.<tailnet>.ts.net:32443` in the Docker `.env` file for Plex
3. Restart the Docker stack: `docker compose up -d`
4. Verify access from a device on your tailnet

## Running

```bash
# Full NAS bootstrap
./nas_bootstrap.sh

# Tailscale only
ansible-playbook playbooks/nas_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags tailscale

# Mac bootstrap
./local_bootstrap.sh

# Tailscale only (Mac)
ansible-playbook playbooks/local_bootstrap.yml -i inventory/inventory.yml --ask-become-pass -vv --tags tailscale
```

## Cert Renewal

Certs are automatically renewed weekly via a systemd timer. To check status:

```bash
# Timer status
systemctl status tailscale-cert-renewal.timer

# Last renewal run
journalctl -u tailscale-cert-renewal.service --no-pager -n 20

# Manual renewal
sudo systemctl start tailscale-cert-renewal.service
```
```

- [ ] **Step 2: Commit**

```bash
git add roles/tailscale/README.md
git commit -m "docs(tailscale): rewrite README with full setup guide"
```

---

### Task 13: Final review and validation

**Prerequisite:** The docker role must have been run before `--tags tailscale` will fully work on the NAS, because the cert renewal service runs `docker exec caddy caddy reload` which requires the Caddy container to exist.

- [ ] **Step 1: Verify all role files exist**

Run: `ls -la roles/tailscale/defaults/main.yml roles/tailscale/tasks/main.yml roles/tailscale/tasks/install_debian.yml roles/tailscale/tasks/install_macos.yml roles/tailscale/tasks/configure.yml roles/tailscale/tasks/https_certs.yml roles/tailscale/handlers/main.yml roles/tailscale/templates/Caddyfile.j2 roles/tailscale/templates/tailscale-cert-renewal.service.j2 roles/tailscale/templates/tailscale-cert-renewal.timer.j2 roles/tailscale/README.md`
Expected: All 11 files listed, no errors

- [ ] **Step 2: Validate all YAML files parse correctly**

Run: `python3 -c "import yaml, glob; [yaml.safe_load(open(f)) for f in glob.glob('roles/tailscale/**/*.yml', recursive=True)]"`
Expected: No output (all valid YAML)

- [ ] **Step 3: Verify playbook changes**

Run: `grep -A 6 'tailscale' playbooks/nas_bootstrap.yml playbooks/local_bootstrap.yml`
Expected: Both playbooks show uncommented tailscale role blocks

- [ ] **Step 4: Verify requirements.yml has no artis3n reference**

Run: `grep artis3n roles/requirements.yml`
Expected: No output (dependency removed)

- [ ] **Step 5: Run pre-commit hooks**

Run: `pre-commit run --all-files`
Expected: All checks pass
