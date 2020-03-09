#!/usr/bin/env bash

NC="\033[0m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
MAGENTA="\033[0;35m"

CUR_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Exit when any command fails
set -e

# Ask for the administrator password upfront
echo -e "${YELLOW}Enter your password plz...${NC}"
sudo -v
echo ""

# Keep-alive: update existing `sudo` timestamp until this script has finished
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

# Install git
echo -e "${CYAN}Installing git...${NC}"
sudo apt install -y git
echo ""

# Install net-tools (gives me ifconfig, among other things)
echo -e "${CYAN}Installing net-tools...${NC}"
sudo apt install -y net-tools
echo ""

echo -e "${CYAN}Installing graphics drivers...${NC}"
sudo ubuntu-drivers autoinstall
echo ""

echo -e "${CYAN}Installing Additional Drivers GUI...${NC}"
sudo apt install software-properties-gtk software-properties-common
echo ""

echo -e "${CYAN}Installing SSH server...${NC}"
sudo apt install -y ssh-import-id
sudo apt install -y openssh-server
echo ""

# Install Sublime Text
echo -e "${CYAN}Installing Sublime Text...${NC}"
# TODO: considering adding GPG keys and update at beginning of script
wget -qO - https://download.sublimetext.com/sublimehq-pub.gpg | sudo apt-key add -
sudo apt install -y apt-transport-https
sudo apt update
sudo apt install -y sublime-text
echo ""

# Cleanup
sudo apt autoremove

# Configure settings
echo -e "${CYAN}Configuring Gnome preferences...${NC}"
chmod u+x setup_preferences.sh 
./setup_preferences.sh
echo ""

# TODO: reboot?
