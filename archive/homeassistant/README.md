[Project Root](../../README.md) > [Archive](../README.md) > **Home Assistant**

# Home Assistant (archived)

The YAML-based Home Assistant configuration that used to live at `services/homeassistant/config/`, kept as reference
while the NAS instance is rebuilt from scratch with UI-managed integrations.

## Status

- **Frozen and unmaintained.** It no longer loads on current Home Assistant: it references integrations and options that
  have since been removed (`darksky`, `updater`, `discovery`, `map`, `temperature_unit`, the `google_translate` TTS
  platform) plus the long-dead `smartthinq` custom component.
- **Not deployed.** The active service is [`services/homeassistant/`](../../services/homeassistant/compose.yml), whose
  `config/` directory starts empty and is populated by Home Assistant on first boot.
- The NAS's last running copy of this config (including `.storage/` config entries, secrets, and Caseta certs) was moved
  to `~/docker/_archive/homeassistant-old/` on the NAS. It holds real secrets and is intentionally not checked in here.

## What it contains

| Path                                                                                   | Purpose                                                                                  |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| [`config/configuration.yaml`](config/configuration.yaml)                               | Top-level HA config (location, logger, YAML-configured integrations, `!include`s)        |
| [`config/automations.yaml`](config/automations.yaml)                                   | Automations                                                                              |
| [`config/groups.yaml`](config/groups.yaml), [`config/customize.yaml`](config/customize.yaml), [`config/themes.yaml`](config/themes.yaml) | Groups, entity customizations, frontend themes                |
| [`config/secrets.yaml.j2`](config/secrets.yaml.j2)                                     | Ansible template for `secrets.yaml`, filled from the inventory vault                     |
| [`config/scripts/get_lutron_cert.py`](config/scripts/get_lutron_cert.py)               | Generates the Lutron Caseta client key/cert pair                                         |
| [`config/custom_components/`](config/custom_components/)                               | Custom Particle relay-module switch platform (and its device firmware)                   |
| [`ansible-tasks.yml`](ansible-tasks.yml)                                               | The `roles/docker` tasks that rendered `secrets.yaml` and copied the Caseta certs        |
