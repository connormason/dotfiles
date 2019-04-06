# Path to your oh-my-zsh installation.
export ZSH=/Users/connormason/.oh-my-zsh
export PATH="/usr/local/sbin:$PATH"

# Set name of the theme to load.
# Look in ~/.oh-my-zsh/themes/
# Optionally, if you set this to "random", it'll load a random theme each
# time that oh-my-zsh is loaded.
ZSH_THEME="gallois"

# Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# Uncomment the following line to use hyphen-insensitive completion. Case
# sensitive completion must be off. _ and - will be interchangeable.
# HYPHEN_INSENSITIVE="true"

# Uncomment the following line to disable bi-weekly auto-update checks.
# DISABLE_AUTO_UPDATE="true"

# Uncomment the following line to change how often to auto-update (in days).
# export UPDATE_ZSH_DAYS=13

# Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# Uncomment the following line to enable command auto-correction.
# ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
# COMPLETION_WAITING_DOTS="true"

# Uncomment the following line if you want to disable marking untracked files
# under VCS as dirty. This makes repository status check for large repositories
# much, much faster.
# DISABLE_UNTRACKED_FILES_DIRTY="true"

# Uncomment the following line if you want to change the command execution time
# stamp shown in the history command output.
# The optional three formats: "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# HIST_STAMPS="mm/dd/yyyy"

# Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# Which plugins would you like to load? (plugins can be found in ~/.oh-my-zsh/plugins/*)
# Custom plugins may be added to ~/.oh-my-zsh/custom/plugins/
# Example format: plugins=(rails git textmate ruby lighthouse)
# Add wisely, as too many plugins slow down shell startup.
plugins=(git git-extras python sublime sudo terminal app web-search)

# Color definitions for pretty output
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

source $ZSH/oh-my-zsh.sh
source $HOME/.bash_profile

source $HOME/.applerc > /dev/null 2>&1
if [ $? -eq 0 ]; then
	echo -e "${CYAN}Connor's Apple zshrc loaded${NC}"
fi

source $HOME/.personalrc > /dev/null 2>&1
if [ $? -eq 0 ]; then
	echo -e "${GREEN}Connor's personal zshrc loaded${NC}"
fi

# Config aliases
alias zshconfig="st ~/.zshrc"
alias zshrc="st ~/.zshrc"
alias ohmyzsh="~/.oh-my-zsh"
alias bashconfig="st ~/.bash_profile"
alias tmuxconf="st ~/.tmux.conf"

# The Fuck
eval "$(thefuck --alias)"
eval "$(thefuck --alias FUCK)"

# Generic command aliases
alias o="open ."
alias clr="clear"

# Generic folder aliases
alias dotfiles="~/.dotfiles"

alias docs="~/Documents"
alias doc="~/Documents"
alias documents="~/Documents"

alias dl="~/Downloads"
alias dls="~/Downloads"
alias down="~/Downloads"
alias downloads="~/Downloads"

alias desk="~/Desktop"
alias desktop="~/Desktop"

alias googleDrive="~/'Google Drive'"
alias gdrive="~/'Google Drive'"
alias gDrive="~/'Google Drive'"

# Python Aliases
alias p="ipython"

# Tmux Aliases
alias tmn="tmux new -s"
alias tma="tmux attach -t"
alias tmls="tmux ls"

# SSH aliases
alias sshpi="ssh pi@192.168.1.69"