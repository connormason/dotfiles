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

echo -e "${CYAN}Installing tree...${NC}" 
brew install tree
echo ""

echo -e "${CYAN}Installing libmagic...${NC}" 
brew install libmagic
echo ""

echo -e "${CYAN}Installing applications...${NC}"
install_mac_apps
echo ""

# TODO: might need to add --no-zsh here since we already have what we need in the .zshrc
echo -e "${CYAN}Installing fzf...${NC}"
brew install fzf
$(brew --prefix)/opt/fzf/install --all
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
ln -sfv "$MAC_DOTFILES_DIR/hammerspoon/init.lua" ~/.hammerspoon
echo ""

# Install zsh
echo -e "${CYAN}Installing zsh...${NC}"
brew install zsh zsh-completions
echo ""
