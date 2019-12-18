# Color definitions for pretty output
WHITE="\033[1;37m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
GREEN="\033[0;32m"
RED="\033[0;31m"
NC="\033[0m"

# Source .applerc if on work install
source $HOME/.applerc > /dev/null 2>&1
if [ $? -eq 0 ]; then
	echo -e "${WHITE}Connor's${NC} ${YELLOW}Apple${NC}${WHITE} zshrc loaded${NC}"
fi

# Source .personalrc if on personal install
source $HOME/.personalrc > /dev/null 2>&1
if [ $? -eq 0 ]; then
	echo -e "${WHITE}Connor's${NC} ${CYAN}Personal${NC}${WHITE} zshrc loaded${NC}"
fi

# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block, everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# To customize prompt, run `p10k configure` or edit ~/.p10k.zsh.
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

# Path to your oh-my-zsh installation.
export ZSH=~/.oh-my-zsh

# TODO: don't do this if its alrady in there
export PATH="/usr/local/sbin:$PATH"

# Set name of the theme to load.
# Look in ~/.oh-my-zsh/themes/
# Optionally, if you set this to "random", it'll load a random theme each
# time that oh-my-zsh is loaded.
ZSH_THEME=powerlevel10k/powerlevel10k

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
plugins=(git git-extras python sublime sudo web-search)

source $ZSH/oh-my-zsh.sh
source $HOME/.bash_profile

# Source 
source $HOME/.applerc > /dev/null 2>&1

# Mac specific stuff
if [ "$(uname)" != "Darwin" ]; then
	alias o="open ."

	# FZF
	[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh
fi

# Zsh completions
fpath=(/usr/local/share/zsh-completions $fpath)

# gitignore.io
function gi() { curl -sLw n https://www.gitignore.io/api/$@ ;}

# Let's get sourced!
alias src="source ~/.zshrc"
alias sourcerc="source ~/.zshrc"

# Config aliases
alias zshconfig="st ~/.zshrc"
alias zshrc="st ~/.zshrc"
alias ohmyzsh="~/.oh-my-zsh"
alias bashconfig="st ~/.bash_profile"
alias tmuxconf="st ~/.tmux.conf"

# Generic command aliases
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

# Git aliases
alias gsl="git stash list"
alias gsp="git stash pop"
alias gs="git stash"
alias gsm="git stash push -m"

# Personal aliases
alias homeserver="ssh connor@192.168.1.133"
