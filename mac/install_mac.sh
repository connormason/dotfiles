#!/usr/bin/env bash

MAC_DOTFILES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Installs apps
# TODO: turn into brewfile
install_mac_apps() {
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
install_mac_apps
echo ""

echo -e "${CYAN}Installating python3...${NC}"
brew install python3
echo ""

echo -e "${CYAN}Installating ipython...${NC}"
python3 -m pip install ipython
echo ""

echo -e "${CYAN}Setting up iTerm to load preferences from dotfiles...${NC}"
defaults write com.googlecode.iterm2.plist PrefsCustomFolder -string "$MAC_DOTFILES_DIR/iterm2"
defaults write com.googlecode.iterm2.plist LoadPrefsFromCustomFolder -bool true
echo ""

echo -e "${CYAN}Installing spaces plugin for Hammerspoon...${NC}"
git clone https://github.com/asmagill/hs._asm.undocumented.spaces "$MAC_DOTFILES_DIR/hammerspoon/spaces"
cd hammerspoon/spaces
[HS_APPLICATION=/Applications] [PREFIX=~/.hammerspoon] make install
cd ../..
echo ""

echo -e "${CYAN}Symlinking Hammerspoon init.lua...${NC}"
ln -sfv "$DOTFILES_DIR/hammerspoon/init.lua" ~/.hammerspoon
echo ""
