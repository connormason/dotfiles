#!/usr/bin/env bash

NC="\033[0m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
MAGENTA="\033[0;35m"

LINUX_DOTFILES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
HOMEASSISTANT_CONFIG_REPO="git@github.com:connormason/homeassistant.git"

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
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
echo ""

# Add apt repositories
echo -e "${CYAN}Adding apt repositories...${NC}"
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) bionic stable"
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

echo -e "${CYAN}Installing pip (for python3)...${NC}"
sudo apt-get install -y python3-pip
echo ""

echo -e "${CYAN}Installing ipython (3)...${NC}"
sudo apt-get install -y ipython3
echo ""

echo -e "${CYAN}Installing tmux...${NC}"
sudo apt-get install -y tmux
echo ""

echo -e "${CYAN}Installing Sublime Text...${NC}"
sudo apt install -y apt-transport-https
sudo apt install -y sublime-text
echo ""

echo -e "${CYAN}Installing Docker...${NC}"
sudo apt install -y ca-certificates gnupg-agent
sudo apt install -y docker-ce docker-ce-cli containerd.io
sudo systemctl status docker
echo ""

echo -e "${CYAN}Installing Docker Compose...${NC}"
sudo apt-get install -y docker-compose
docker-compose --version
echo ""

# Add user to Docker group
echo -e "${CYAN}Adding user '${USER}' to Docker group...${NC}"
sudo usermod -aG docker ${USER}
echo "Done"
echo ""

# Create ~/docker directory (if it doesn't already exist)
echo -e "${CYAN}Creating ~/docker/ directory and symlinking docker-compose.yaml...${NC}"
if [ ! -d ~/docker ]; then
	mkdir ~/docker
	sudo setfacl -Rdm g:docker:rwx ~/docker
	sudo chmod -R 775 ~/docker
	ln -sfv $LINUX_DOTFILES_DIR/docker-compose.yml ~/docker
else
	echo -e "${MAEGNTA}~/docker/ directory already exists${NC}"
fi

echo ""

# Grab homeassistant config repo (or pull latest if we already have it)
if [ ! -d ~/docker/homeassistant ]; then
	echo -e "${CYAN}Cloning homeassistant configuration repo...${NC}"
	cd ~/docker
	git clone $HOMEASSISTANT_CONFIG_REPO
else
	echo -e "${CYAN}Pulling latest homeassistant configuration repo...${NC}"
	cd ~/docker/homeassistant
	git pull
fi
echo ""

echo -e "${CYAN}Starting up docker with docker-compose...${NC}"
docker-compose -f ~/docker/docker-compose.yml up -d
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

# Cleanup
echo -e "${CYAN}Cleaning up...${NC}"
sudo apt -y autoremove
echo ""

echo 