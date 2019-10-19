# Connor's Dotfiles
These are my dotfiles. Yay.

## Steps to Install (on new computer)
1. Open Terminal
2. [Generate an SSH key](https://help.github.com/en/articles/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent) and give it to GitHub (if performing a work install, also give it to work GitHub)
3. Clone this repo into ~ (`cd ~; git clone git@github.com:connormason/dotfiles.git`)
4. Rename directory to ".dotfiles" and cd into it (`mv dotfiles .dotfiles; cd .dotfiles`)
5. Run the install script
    - Personal Ubuntu machine: `./install.sh personal ubuntu`
    - Personal Mac machine: `./install.sh personal mac`
    - Work: `./install.sh work`

If running a home server install, make sure to reserve an IP address in the router configuration.
