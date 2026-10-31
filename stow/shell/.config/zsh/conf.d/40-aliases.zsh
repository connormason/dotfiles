# =============================================================================
# Default tools and directories
# =============================================================================

# Set default pager/editor: Sublime Text on macOS; elsewhere (the headless NAS) micro from the shared Brewfile, which
# also stands in for Sublime's `st` so the config aliases below work
export PAGER=moor
if [[ $OSTYPE == darwin* ]]; then
    export VISUAL=subl
else
    export VISUAL=micro
    alias st=micro
fi

# =============================================================================
# Config file aliases
# =============================================================================

# Aliases for sourcing ~/.zshrc for easy reloads
alias src="source ~/.zshrc"
alias sourcerc="source ~/.zshrc"

# Config aliases
alias zshconfig="st ~/.zshrc"
alias zshrc="st ~/.zshrc"
alias ohmyzsh="~/.oh-my-zsh"
alias bashconfig="st ~/.bash_profile"

# =============================================================================
# Built-in command aliases
# =============================================================================

# Make some basic commands verbose
alias rm="rm -v"
alias cp="cp -v"
alias mv="mv -v"

# Generic command aliases
# macOS only: Linux's `open` is openvt
if [[ $OSTYPE == darwin* ]]; then
    alias o="open ."
fi
alias clr="clear"
