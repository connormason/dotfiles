# Connor's Dotfiles

These are my dotfiles. Yay.

## NAS Bootstrapping

Bootstrapping of my home NAS/server is done with ansible

1. Create python virtual environment to install dependencies into
2. `pip install -r requirements.txt`
3. Create file `vault_password.txt` in the repo root and paste in the Ansible Vault password from password manager
4. Run `chmod u+x; ./nas_bootstrap.sh`

## Notes
- Probably need to request a tailscale auth key from https://login.tailscale.com/admin/authkeys (expires after 90 days)
