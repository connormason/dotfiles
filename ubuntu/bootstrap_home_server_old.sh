#!/usr/bin/env bash

NC="\033[0m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
MAGENTA="\033[0;35m"

CUR_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
HOMEASSISTANT_CONFIG_REPO="git@github.com:connormason/homeassistant.git"

# Install net-tools (gets us ifconfig, among other things)
echo -e "${CYAN}Installing net-tools...${NC}"
sudo apt-get install -y net-tools
echo ""

# Install SSH server
echo -e "${CYAN}Installing SSH server...${NC}"
sudo apt-get install -y openssh-server
echo ""

# Install Docker dependencies and add package repo
echo -e "${CYAN}Installing Docker dependencies and package repo...${NC}"
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -

# Using edge/test repos for now, since I'm not currently using a stable Lubuntu release
# sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable edge test"
sudo apt-get update
echo ""

# TODO: validate output 
apt-cache policy docker-ce
echo ""

# Install Docker
echo -e "${CYAN}Installing Docker...${NC}"
sudo apt-get install -y docker-ce
sudo systemctl status docker
echo ""

# Install Docker Compose
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
echo -e "${CYAN}Creating ~/docker/ directory...${NC}"
if [ ! -d ~/docker ]; then
	mkdir ~/docker
	sudo setfacl -Rdm g:docker:rwx ~/docker
	sudo chmod -R 775 ~/docker
	ln -sfv $CUR_DIR/docker-compose.yml ~/docker
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

# Install pip
echo -e "${CYAN}Installing pip (for python3)...${NC}"
sudo apt-get install -y python3-pip
echo ""

# Install iPython3
echo -e "${CYAN}Installing ipython (3)...${NC}"
sudo apt-get install -y ipython3
echo ""

# Install fzf
echo -e "${CYAN}Installing fzf...${NC}"
sudo apt-get install -y fzf
echo ""

# Install tmux
echo -e "${CYAN}Installing tmux...${NC}"
sudo apt-get install -y tmux
echo ""

# Install zsh
echo -e "${CYAN}Installing zsh...${NC}"
sudo apt-get install -y zsh
echo ""

echo -e "${CYAN}Auto-removing extraneous packages...${NC}"
sudo apt-get autoremove -y
echo ""