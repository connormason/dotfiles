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
WORK_DOTFILES_DIR="$STATES_DIR/work"
USERNAME=$(whoami)

# Input error output function
input_error() {
    echo "usage: "
    echo "  ./bootstrap.sh personal                    --> installs on a personal machine"
    echo "  ./bootstrap.sh work <git_url> <git_branch> --> installs on a work machine, cloning work dotfiles from <git_url>"
}

# Require work/personal argument
if [[ -z $1 ]]; then
    input_error
    exit 1
elif [[ $1 == "work" ]] && [[ -z $2 ]]; then
    input_error
    exit 1
fi

# Ask for the administrator password upfront
echo -e "${YELLOW}Enter your password plz...${NC}"
sudo -v
echo ""

# Add a `sudo` to the command if none provided
USE_SUDO=""
if [[ $(whoami) != "root" ]]; then
    USE_SUDO="sudo "
fi

# Run installation process for current environment (if implemented)
ENV="$(./determine_environment.sh)"
if [[ $ENV == "Mac" ]]; then
    if [[ $1 == "work" ]]; then
        echo -e "${MAGENTA}Running work install on Mac${NC}"

        # Get most recent version of work dotfiles
        if [ ! -d $WORK_DOTFILES_DIR ]; then
            echo "Work repo not yet cloned, cloning $2..."
            yes | git clone $2 $WORK_DOTFILES_DIR
            RET=$?
            if [ $RET -ne 0 ]; then
                echo -e "${RED}Failed to clone work dotfiles repo"
                exit 1
            fi
        else
            echo "Work repo already cloned, updating..."
            cd $WORK_DOTFILES_DIR
            git pull
        fi

        RET=$?
        if [ $RET -ne 0 ]; then
            echo -e "${RED}Failed to retrieve work dotfiles repo"
            exit 1
        fi
        echo ""

        # Checkout specific branch (if specified)
        if [[ ! -z $3 ]]; then
            echo -e "Checking out specified work dotfiles branch: ${CYAN}$3${NC}"
            git checkout $3
            echo ""
        fi
    else
        echo -e "${MAGENTA}Running personal install on Mac${NC}"
    fi

	# Install Homebrew
    if [[ ! $(command -v brew) ]]; then
        echo -e "Installing Homebrew..."
        ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
    fi

    # Install SaltStack
    if [[ ! $(command -v salt-call) ]]; then
    	echo -e "Installing SaltStack..."
        brew install saltstack || :
    fi

elif [[ $ENV == "Linux" ]] && [[ $1 == "personal" ]]; then
    echo -e "${MAGENTA}Bootstrapping home server...${NC}"
    cd $DOTFILES_DIR/linux
    chmod u+x bootstrap_home_server.sh
    ./bootstrap_home_server.sh
else
    if [[ ! $(command -v salt-call) ]]; then
        echo "Bootstrapping unspported for $1 installation on $ENV."
        echo "Aborting..."
        exit 1
    fi
fi
echo ""

# Run standalone minion to apply states
cd $DOTFILES_DIR
echo  -e "Kicking off configuration with SaltStack..."
$USE_SUDO salt-call --config=./ grains.setvals "{\
    \"dotfiles_dir\": \"$DOTFILES_DIR\", \
    \"home\": \"$HOME_DIR\", \
    \"states_dir\": \"$STATES_DIR\", \
    \"user\": \"$USERNAME\", \
    \"install_type\": \"$1\" \
}"
$USE_SUDO salt-call --config=./ --retcode-passthrough state.highstate

echo -e "${GREEN}Bootstrapping completed. Please restart so all changes take effect${NC}"
