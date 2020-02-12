#!/usr/bin/env bash

MAC_DOTFILES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

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
brew tap homebrew/bundle
brew bundle
rehash

# Suppress the warning for downloaded applications
xattr -d -r com.apple.quarantine ~/Applications
echo ""

echo -e "${CYAN}Installing fzf...${NC}"
brew install fzf
$(brew --prefix)/opt/fzf/install --all --no-zsh
echo ""

echo -e "${CYAN}Installating python3...${NC}"
brew install python3
echo ""

echo -e "${CYAN}Upgrading pip...${NC}"
python3 -m pip install --user --upgrade pip
echo ""

echo -e "${CYAN}Installating ipython...${NC}"
python3 -m pip install ipython --user
echo ""

echo -e "${CYAN}Running brew cleanup...${NC}"
brew cleanup
echo ""

echo -e "${CYAN}Setting up iTerm to load preferences from dotfiles...${NC}"
defaults write com.googlecode.iterm2.plist PrefsCustomFolder -string "$MAC_DOTFILES_DIR/iterm2"
defaults write com.googlecode.iterm2.plist LoadPrefsFromCustomFolder -bool true
echo ""

echo -e "${CYAN}Creating .hammerspoon directory and symlinking init.lua..."
mkdir ~/.hammerspoon
ln -sfv "$MAC_DOTFILES_DIR/hammerspoon/init.lua" ~/.hammerspoon
echo ""

echo -e "${CYAN}Installing spaces plugin for Hammerspoon...${NC}"
git clone https://github.com/asmagill/hs._asm.undocumented.spaces "$MAC_DOTFILES_DIR/hammerspoon/spaces"
cd hammerspoon/spaces
make install
cd ../..
echo ""

echo -e "${CYAN}Configuring macOS preferences...${NC}"
chmod u+x install_mac.sh
./setup_preferences.sh
echo ""

# Install zsh
echo -e "${CYAN}Installing zsh...${NC}"
brew install zsh zsh-completions
echo ""
