#!/usr/bin/env bash

# Exit when any command fails
set -e

# Color definitions
NC="\033[0m"
YELLOW="\033[0;33m"
MAGENTA="\033[0;35m"
RED="\033[0;31m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"

# Filepath definitions
DOTFILES_DIR=$(pwd)
HOME_DIR=$HOME
STATES_DIR="$(pwd)/states"
USERNAME=$(whoami)

# Ask for the administrator password upfront
echo -e "${YELLOW}Enter your password plz...${NC}"
sudo -v
echo ""

# Add a `sudo` to the command if none provided
USE_SUDO=''
if [[ $(whoami) != 'root' ]]; then
    USE_SUDO='sudo '
fi

if [[ $(uname) == 'Darwin' ]]; then

	# Install Homebrew
    if [[ ! $(command -v brew) ]]; then
        echo -e "Installing Homebrew..."
        ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
    else
    	echo 'Homebrew already installed'
    fi

    # Install SaltStack
    if [[ ! $(command -v salt-call) ]]; then
    	echo -e "Installing SaltStack..."
        brew install saltstack
    fi
else
    if [[ ! $(command -v salt-call) ]]; then
        echo "Bootstrap script unsupported for $(uname)."
        echo "Please manually install SaltStack with your system package manager, then try again."
        echo "Aborting..."
        exit 1
    fi
fi
echo ""

# Run standalone minion to apply states
echo  -e "${MAGENTA}Kicking off configuration with SaltStack...${NC}"
command="$1"
if [[ -n "$command" ]]; then
    shift
else
    command=state.highstate
fi

$USE_SUDO salt-call --config=./ grains.setvals "{\
    \"dotfiles_dir\": \"$DOTFILES_DIR\", \
    \"home\": \"$HOME_DIR\", \
    \"states_dir\": \"$STATES_DIR\", \
    \"user\": \"$USERNAME\" \
}"
$USE_SUDO salt-call --config=./ --retcode-passthrough "$command" "$@"
