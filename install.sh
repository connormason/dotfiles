#!/usr/bin/env bash

# Work dotfile repo location
WORK_DOTFILES_REPO="git@github.pie.apple.com:connor-mason/dotfiles.git"

# Color definitions
NC="\033[0m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
MAGENTA="\033[0;35m"
CYAN="\033[0;36m"

# Input error output function
input_error() {
    echo "usage: "
    echo "  ./install.sh work   --> installs on work Mac machine"
    echo "  ./install.sh mac    --> installs on personal Mac machine"
    echo "  ./install.sh server --> installs on home server Ubuntu machine"
}

# Check for argument existance and validity
if [ ! -z "$1" ] && [ "$1" == "work" ]; then
    echo -e "${MAGENTA}Running work install on Mac${NC}"
elif [ ! -z "$1" ] && [ "$1" == "mac" ]; then
    echo -e "${MAGENTA}Running personal install on Mac${NC}"
elif [ ! -z "$1" ] && [ "$1" == "server" ]; then
    echo -e "${MAGENTA}Running home server install on Ubuntu${NC}"
else
    input_error
    exit 1
fi
echo ""

# Get dotfiles directory location
DOTFILES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Ask for the administrator password upfront
echo -e "${YELLOW}Enter your password plz...${NC}"
sudo -v
echo ""

# Keep-alive: update existing `sudo` timestamp until this script has finished
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

# Create symlinks
echo -e "${CYAN}Creating symlinks...${NC}"
ln -sfv "$DOTFILES_DIR/.gitignore_global" ~
ln -sfv "$DOTFILES_DIR/.tmux.conf" ~

if [ "$1" == "work" ]; then
    ln -sfv "$DOTFILES_DIR/work/.applerc" ~
    ln -sfv "$DOTFILES_DIR/work/.bash_profile" ~
    ln -sfv "$DOTFILES_DIR/work/.gitconfig" ~
elif [ "$1" == "mac" ] || [ "$1" == "server" ]; then
    ln -sfv "$DOTFILES_DIR/personal/.personalrc" ~
    ln -sfv "$DOTFILES_DIR/personal/.bash_profile" ~
    ln -sfv "$DOTFILES_DIR/personal/.gitconfig" ~
fi

echo ""

# Update dotfiles repo
echo -e "${CYAN}Pulling latest dotfiles repo...${NC}"
[ -d "$DOTFILES_DIR/.git" ] && git --work-tree="$DOTFILES_DIR" --git-dir="$DOTFILES_DIR/.git" pull origin master
echo ""

# Setup/run auxillary install scripts
if [ "$1" == "work" ]; then

    # Pull latest work dotfiles
    echo -e "${CYAN}Pulling latest work dotfiles from repo...${NC}"

    if [ ! -d $DOTFILES_DIR/work/.git ]; then
        cd $DOTFILES_DIR
        rm -rf work
        git clone $WORK_DOTFILES_REPO
        mv dotfiles work
    else
        cd $DOTFILES_DIR/work
        git pull
        cd $DOTFILES_DIR
    fi
    echo ""

    # Run work install script
    echo -e "${CYAN}Running work dotfiles install.sh...${NC}"
    cd $DOTFILES_DIR/work
    chmod u+x install.sh
    ./install.sh
    cd $DOTFILES_DIR

    echo ""

elif [ "$1" == "mac" ]; then
    if [ "$(uname)" != "Darwin" ]; then
        echo -e "${RED}Cannot perform Mac install on non-macOS device${NC}"
        exit 1
    fi

    echo -e "${MAGENTA}Running MacOS install script...${NC}"
    cd $DOTFILES_DIR/mac
    chmod u+x install_mac.sh
    ./install_mac.sh
elif [ "$1" == "server" ]; then
    if [ "$(expr substr $(uname -s) 1 5)" != "Linux" ]; then
        echo -e "${RED}Cannot perform home server (Ubuntu) install on non-Ubuntu device${NC}"
        exit 1
    fi

    echo -e "${MAGENTA}Bootstrapping home server...${NC}"
    cd $DOTFILES_DIR/ubuntu
    chmod u+x bootstrap_home_server.sh
    ./bootstrap_home_server.sh
fi

cd $DOTFILES_DIR

# Download/instsall oh-my-zsh (--unattended to prevent prompts)
# TODO: can we somehow make zsh the default shell in this install script?
echo -e "${CYAN}Installing oh-my-zsh...${NC}"
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh --unattended)"
echo ""

echo -e "${CYAN}Symlinking .zshrc correctly...${NC}"
rm -f ~/.zshrc
rm -f ~/.zshrc.pre-oh-my-zsh
ln -sfv "$DOTFILES_DIR/.zshrc" ~
source ~/.zshrc
echo ""

echo ""
echo -e "${GREEN}Installation finished.${NC}"
