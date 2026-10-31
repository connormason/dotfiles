# TODOs

- Use Watchtower for automating Docker container updates (https://containrrr.dev/watchtower/)
- Portainer? (https://www.portainer.io)
- lazydocker
- install brew on linux too?
- Glances (https://github.com/nicolargo/glances)
- Symlink pihole/dnsmasq config files?
- Update docker-compose.yml schema version?
- remove requirements.txt?

## Personal MacBook bootstrap

- Root-cause the intermittent 109-byte interactive-shell startup output seen once on the first real run
- Phase B step B5: public plugin set in `profiles/personal-mac/render/claude.json`, multi-day VS Code drift check,
  `--settings` layering probe

## Docker Services Modularization

Remaining manual steps (require NAS/GitHub access):

1. Audit existing NAS .env for extra variables
2. Migrate ~/docker/shared/ to ~/docker/homeassistant/shared/ on NAS
3. Set up 5 GitHub secrets (Tailscale OAuth, SSH key, NAS host, user)
4. Run Ansible bootstrap once on NAS
5. End-to-end test: push a config change, verify auto-deploy

## Home Assistant OS VM

- Remote access for the HAOS VM (Caddy dedicated port with an `upstream` override, or the Tailscale app) — see
  `vms/haos/README.md` "Remote access"
- Fold `vms/haos/` scripts into the NAS bootstrap once the broader Ansible → scripts refactor is scoped
