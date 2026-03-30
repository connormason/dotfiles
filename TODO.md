# TODOs
- Use Watchtower for automating Docker container updates (https://containrrr.dev/watchtower/)
- Portainer? (https://www.portainer.io)
- lazydocker
- install brew on linux too?
- Glances (https://github.com/nicolargo/glances)
- Symlink pihole/dnsmasq config files?
- Update docker-compose.yml schema version?
- remove requirements.txt?

## Docker Services Modularization
Remaining manual steps (require NAS/GitHub access):
1. Audit existing NAS .env for extra variables
2. Migrate ~/docker/shared/ to ~/docker/homeassistant/shared/ on NAS
3. Set up 5 GitHub secrets (Tailscale OAuth, SSH key, NAS host, user)
4. Run Ansible bootstrap once on NAS
5. End-to-end test: push a config change, verify auto-deploy
