#!/usr/bin/env bash

NC="\033[0m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"

CUR_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
HOMEASSISTANT_CONFIG_REPO="https://github.com/connormason/homeassistant.git"

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

echo -e "${CYAN}Creating ~/docker/ directory...${NC}"
mkdir ~/docker
sudo setfacl -Rdm g:docker:rwx ~/docker
sudo chmod -R 775 ~/docker
ln -sfv $CUR_DIR/docker-compose.yml ~/docker
echo ""

echo -e "${CYAN}Grabbing latest homeassistant configuration...${NC}"
git clone $HOMEASSISTANT_CONFIG_REPO ~/docker
echo ""

# docker-compose -f ~/docker/docker-compose.yml up

# Install pip
# echo -e "${CYAN}Installing pip (for python3)...${NC}"
# sudo apt-get install -y python3-pip
# echo ""

# # Install required Python packages (TODO: maybe move to a requirements.txt)
# echo -e "${CYAN}Installing required Python packages...${NC}"
# python3 -m pip install tzlocal
# echo ""

# # Setup environment variables for Docker
# echo -e "${CYAN}Setting up environment variables for Docker...${NC}"
# python3 $CUR_DIR/bootstrap_utils.py setup_environment
# echo ""

# # Install iPython3
# echo -e "${CYAN}Installing ipython (3)...${NC}"
# sudo apt-get install -y ipython3
# echo ""
