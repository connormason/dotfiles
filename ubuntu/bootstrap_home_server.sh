#!/usr/bin/env bash

NC="\033[0m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"

# Ask for the administrator password upfront
echo -e "${YELLOW}Enter your password plz...${NC}"
sudo -v

# Keep-alive: update existing `sudo` timestamp until this script has finished
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

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
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add –

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
echo ""

# Setup environment variables for Docker
# TODO....