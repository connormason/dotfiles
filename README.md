# Connor's Dotfiles

These are my dotfiles. Yay.

## Personal Mac Bootstrapping

- Download password manager from the Mac App Store
- Login to github.com from browser
- Setup SSH keys with Github
  - Generate SSH key in terminal: `ssh-keygen -t ed25519 -C "your_email@example.com"`
  - Start SSH agent: `eval "$(ssh-agent -s)"`
  - Add SSH key to ssh-agent: `ssh-add --apple-use-keychain ~/.ssh/id_ed25519`
  - Copy SSH key to clipboard: `pbcopy < ~/.ssh/id_ed25519.pub`
  - Add SSH key to github.com account
- Clone dotfiles repo: `git clone git@github.com:connormason/dotfiles.git`
- Create `vault_password.txt` file in dotfiles repo and paste in Ansible Vault password from password manager
- Run bootstrapping script
  - `chmod u+x local_bootstrap.sh`
  - `./local_bootstrap.sh`

## NAS Bootstrapping

- Create file `vault_password.txt` in the repo root and paste in the Ansible Vault password from password manager
- Run bootstrapping script
  - `chmod u+x nas_bootstrap.sh`
  - `./nas_bootstrap.sh`
- Point router DNS at NAS for PiHole

## Notes
- Probably need to request a tailscale auth key from https://login.tailscale.com/admin/authkeys (expires after 90 days)
