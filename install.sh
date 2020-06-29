#!/usr/bin/env bash

# Exit when any command fails
set -e

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
    echo "  ./install.sh work     --> installs on work machine"
    echo "  ./install.sh personal --> installs on a personal machine (home server)"
}

# Require work/personal argument
if [ -z "$1" ]; then
    input_error
    exit 1
fi

# Run install script for current environment (if implemented)
ENV="$(./determine_environment.sh)"
if [ "$ENV" = "Mac" ] && [ "$1" = "work" ]; then
    echo -e "${MAGENTA}Running work install on Mac${NC}"
elif [ "$ENV" = "Mac" ] && [ "$1" == "personal" ]; then
    echo -e "${MAGENTA}Running personal install on Mac${NC}"
elif [ "$ENV" = "Linux" ] && [ "$1" = "personal" ]; then
    echo -e "${MAGENTA}Running home server install on Linux${NC}"
elif [ "$ENV" = "Linux" ] && [ "$1" = "work" ]; then
    echo -e "${RED}Work Linux install not implemented${NC}"
    exit 1
else
    input_error
    exit 1
fi
echo ""

# Get dotfiles directory location
DOTFILES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change dotfiles origin to use SSH instead of HTTPS
echo -e "${MAGENTA}Changing dotfiles remote to use SSH...${NC}"
git remote set-url origin git@github.com:connormason/dotfiles.git
echo ""

# Create symlinks
echo -e "${CYAN}Creating symlinks...${NC}"
if [ "$1" == "work" ]; then
    ln -sfv "$DOTFILES_DIR/work/.applerc" ~
    ln -sfv "$DOTFILES_DIR/work/.bash_profile" ~
    ln -sfv "$DOTFILES_DIR/work/.gitconfig" ~
elif [ "$1" == "personal" ]; then
    ln -sfv "$DOTFILES_DIR/personal/.personalrc" ~
    ln -sfv "$DOTFILES_DIR/personal/.bash_profile" ~
    ln -sfv "$DOTFILES_DIR/personal/.gitconfig" ~
fi

echo ""

# Update dotfiles repo
echo -e "${CYAN}Pulling latest dotfiles repo...${NC}"
[ -d "$DOTFILES_DIR/.git" ] && git --work-tree="$DOTFILES_DIR" --git-dir="$DOTFILES_DIR/.git" pull origin master
echo ""

# Setup/run platform-specific auxillary install scripts
if [ "$ENV" = "Mac" ]; then
    echo -e "${MAGENTA}Running MacOS install script...${NC}"
    cd $DOTFILES_DIR/mac
    # chmod u+x install_mac.sh
    # ./install_mac.sh
elif [ "$ENV" = "Linux" ]; then
    echo -e "${MAGENTA}Bootstrapping home server...${NC}"
    cd $DOTFILES_DIR/linux
    chmod u+x bootstrap_home_server.sh
    ./bootstrap_home_server.sh
fi


# Setup/run work dotfiles install script
if [ "$1" == "work" ]; then
    echo -e "${CYAN}Pulling latest work dotfiles from repo...${NC}"

    if [ ! -d $DOTFILES_DIR/work/.git ]; then
        cd $DOTFILES_DIR
        rm -rf work

        yes | git clone $WORK_DOTFILES_REPO
        RET=$?
        if [ $RET -ne 0 ]; then
            echo -e "${RED}Failed to clone work dotfiles repo. Are you connected to AppleConnect?${NC}"
            exit 1
        fi
        mv dotfiles work
    else
        cd $DOTFILES_DIR/work
        
        git pull
        RET=$?
        if [ $RET -ne 0 ]; then
            echo -e "${RED}Failed to pull work dotfiles repo. Are you connected to AppleConnect?${NC}"
            exit 1
        fi
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
fi

cd $DOTFILES_DIR

echo ""
echo -e "${GREEN}Installation finished. Please reboot for all settings to take effect${NC}"

# Launch zsh
exec zsh -l