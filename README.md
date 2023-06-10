# Connor's Dotfiles
These are my dotfiles. Yay.

## Steps to Install (on new computer)
1. Open Terminal
2. Clone this repo into ~ (`cd ~; git clone https://github.com/connormason/dotfiles.git`)
3. Generate an SSH key with bundled script `chmod u+x generate_and_copy_ssh_key.sh; ./generate_and_copy_ssh_key.sh` (or follow instructions [here](https://help.github.com/en/articles/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)), then give it to GitHub (and internal GitHub if performing a work install)
4. Run the install script
    - Personal machine: `./bootstrap.sh personal`
    - Work machine: `./bootstrap.sh work <git_url> <git_branch>`, providing the details for where to find work dotfiles
5. Run `brew doctor` if on a Mac

If running a home server install, make sure to reserve an IP address in the router configuration.

## NAS Bootstrapping

Bootstrapping of my home NAS is done with ansible

1. Install Ansible (ideally in a virtual environment)
2. Create file `vault_password.txt` in the repo root and paste in the Ansible Vault password from my password manager
3. Run `chmod u+x; nas_bootstrap.sh`
