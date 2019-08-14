#!/usr/bin/env bash

# Work dotfile repo location
WORK_DOTFILES_REPO="git@github.pie.apple.com:connor-mason/dotfiles.git"

# Color definitions
NC="\033[0m"
RED="\033[0;31m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"

# Installs apps
# TODO: turn into brewfile
install_apps() {
	apps=(
		google-chrome
		iterm2
		hammerspoon
		sublime-text
		pycharm
		franz
	)

	brew cask install "${apps[@]}"
	brew cask cleanup
}

# Input error output function
input_error() {
	echo "usage: "
	echo "  ./install.sh work 	--> installs on work computer"
	echo "  ./install.sh personal --> installs on personal computer"
}

# Check for argument existance
if [ -z "$1" ]; then
	input_error
	exit 1
fi

# Check if argument is a valid option
if !([ "$1" == "personal" ] || [ "$1" == "work" ]); then
	input_error
	exit 1
fi

# Get dotfiles directory location
DOTFILES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Ask for the administrator password upfront
echo -e "${YELLOW}Enter your password plz...${NC}"
sudo -v

# Keep-alive: update existing `sudo` timestamp until this script has finished
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

# Update dotfiles repo
echo -e "${CYAN}Pulling latest dotfiles repo...${NC}"
[ -d "$DOTFILES_DIR/.git" ] && git --work-tree="$DOTFILES_DIR" --git-dir="$DOTFILES_DIR/.git" pull origin master
echo ""

# Pull work dotfile repo and run its install script if necessary
if [ "$1" == "work" ]; then
	echo -e "${CYAN}Pulling latest work dotfiles from repo...${NC}"
    if [ ! -d $DOTFILES_DIR/work/.git ]; then
        cd $DOTFILES_DIR
        rm -rf work

        if [ ! $(git clone $WORK_DOTFILES_REPO) ]; then
            echo -e "${RED}Failed to clone work dotfiles repo. Are you connected to AppleConnect?${NC}"
            exit 1
        fi
        mv dotfiles work
    else
        cd $DOTFILES_DIR/work
        if [ ! $(git pull) ]; then
            echo -e "${RED}Failed to pull work dotfiles repo. Are you connected to AppleConnect?${NC}"
            exit 1
        fi
        cd $DOTFILES_DIR
    fi
    echo ""

	echo -e "${CYAN}Running work dotfiles install.sh...${NC}"
	cd $DOTFILES_DIR/work
	chmod u+x install.sh
	./install.sh
	cd $DOTFILES_DIR

	echo ""
fi

# Create symlinks
echo -e "${CYAN}Creating symlinks...${NC}"
ln -sfv "$DOTFILES_DIR/.gitignore_global" ~
ln -sfv "$DOTFILES_DIR/.tmux.conf" ~

if [ "$1" == "work" ]; then
	ln -sfv "$DOTFILES_DIR/work/.applerc" ~
	ln -sfv "$DOTFILES_DIR/work/.bash_profile" ~
	ln -sfv "$DOTFILES_DIR/work/.gitconfig" ~
elif [ "$1" == "personal" ]; then
	ln -sfv "$DOTFILES_DIR/personal/.bash_profile" ~
	ln -sfv "$DOTFILES_DIR/personal/.gitconfig" ~
	ln -sfv "$DOTFILES_DIR/personal/.personalrc" ~
fi

echo ""

echo -e "${CYAN}Installing spaces plugin for Hammerspoon...${NC}"
git clone https://github.com/asmagill/hs._asm.undocumented.spaces hammerspoon/spaces
cd hammerspoon/spaces
make install
cd ../..
echo ""

# Install Homebrew and Homebrew packages
echo -e "${CYAN}Installing and updating Homebrew...${NC}"

echo | ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
brew update 
brew upgrade 
echo ""

echo -e "${CYAN}Installing Caskroom...${NC}"
brew tap caskroom/cask
brew install brew-cask
brew tap caskroom/versions
echo ""

echo -e "${CYAN}Installing thefuck...${NC}" 
brew install thefuck
echo ""

echo -e "${CYAN}Installing tree...${NC}" 
brew install tree
echo ""

echo -e "${CYAN}Installing libmagic...${NC}" 
brew install libmagic
echo ""

echo -e "${CYAN}Installing applications...${NC}"
install_apps
echo ""

echo -e "${CYAN}Installating python3...${NC}"
brew install python3
echo ""

echo -e "${CYAN}Installating ipython...${NC}"
python3 -m pip install ipython
echo ""

echo -e "${CYAN}Setting up iTerm to load preferences from dotfiles...${NC}"
defaults write com.googlecode.iterm2.plist PrefsCustomFolder -string "~/$DOTFILES_DIR/iterm2"
defaults write com.googlecode.iterm2.plist LoadPrefsFromCustomFolder -bool true
echo ""

echo -e "${CYAN}Symlinking Hammerspoon init.lua...${NC}"
ln -sfv "$DOTFILES_DIR/hammerspoon/init.lua" ~/.hammerspoon
echo ""

echo -e "${CYAN}Installing spaces plugin for Hammerspoon...${NC}"
git clone https://github.com/asmagill/hs._asm.undocumented.spaces spaces
cd spaces
[HS_APPLICATION=/Applications] [PREFIX=~/.hammerspoon] make install
echo ""

# Download oh-my-zsh
echo -e "${CYAN}Installing oh-my-zsh...${NC}"
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
echo ""

echo -e "${CYAN}Symlinking .zshrc correctly...${NC}"
rm ~/.zshrc
rm ~/.zshrc.pre-oh-my-zsh 
ln -sfv "$DOTFILES_DIR/.zshrc" ~
source ~/.zshrc
echo ""

echo ""
echo -e "${GREEN}Done.${NC}"