#!/usr/bin/env bash

NC="\033[0m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
MAGENTA="\033[0;35m"

LINUX_DOTFILES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Exit when any command fails
set -e

# Ask for the administrator password upfront
echo -e "${YELLOW}Enter your password plz...${NC}"
sudo -v
echo ""

# Keep-alive: update existing `sudo` timestamp until this script has finished
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

# Add GPG keys for repos
echo -e "${CYAN}Adding GPG keys for repositories...${NC}"
wget -qO - https://download.sublimetext.com/sublimehq-pub.gpg | sudo apt-key add -
echo ""

echo -e "${CYAN}Updating apt...${NC}"
sudo apt update
echo ""

echo -e "${CYAN}Installing git...${NC}"
sudo apt install -y git
echo ""

echo -e "${CYAN}Installing gdebi...${NC}"
sudo apt install -y gdebi-core
echo ""

# Install net-tools (gives me ifconfig, among other things)
echo -e "${CYAN}Installing net-tools...${NC}"
sudo apt install -y net-tools
echo ""

echo -e "${CYAN}Installing graphics drivers...${NC}"
sudo ubuntu-drivers autoinstall
echo ""

echo -e "${CYAN}Installing Additional Drivers GUI...${NC}"
sudo apt install -y software-properties-gtk software-properties-common
echo ""

echo -e "${CYAN}Installing SSH server...${NC}"
sudo apt install -y ssh-import-id
sudo apt install -y openssh-server
echo ""

# Install Sublime Text
echo -e "${CYAN}Installing Sublime Text...${NC}"
sudo apt install -y apt-transport-https
sudo apt install -y sublime-text
echo ""

# Install Kinto (macOS bindings for Linux)
echo -e "${CYAN}Installing dependencies and pulling latest version of Kinto...${NC}"
sudo apt install -y xbindkeys xdotool
if [ ! -d ~/kinto/.git ]; then
	git clone https://github.com/rbreaves/kinto.git ~/kinto
else
	cd ~/kinto/
	git pull
fi
echo ""

# Create Kinto config symlink
echo -e "${CYAN}Symlinking Kinto config...${NC}"
if [ ! -d ~/.config/kinto ]; then
	mkdir -p ~/.config/kinto
fi
ln -sfv "$LINUX_DOTFILES_DIR/.config/kinto/user_config.json" ~/.config/kinto
echo ""

echo -e "${CYAN}Running Kinto setup...${NC}"
yes "n" | ./setup.py
cd $LINUX_DOTFILES_DIR
echo ""

# Cleanup
sudo apt -y autoremove
echo ""

# Configure settings
echo -e "${CYAN}Configuring Gnome preferences...${NC}"
chmod u+x setup_preferences.sh 
./setup_preferences.sh
echo ""

# Install zsh and make it the default shell
echo -e "${CYAN}Installing zsh and making it the default shell...${NC}"
sudo apt install -y zsh
sudo chsh -s $(which zsh) $(whoami)
echo ""

# TODO: reboot?
