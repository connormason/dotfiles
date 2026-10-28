# =====================================================================================================
# Miscellaneous tools
#
# One-liner shell wiring for tools that have no dedicated stow package and no config files of their own.
# Directory jumping is zoxide's `z` (stow/zoxide).
# =====================================================================================================

# =====================================================================================================
# lazyssh (https://github.com/Adembc/lazyssh)
# =====================================================================================================

alias lssh="lazyssh"

# =====================================================================================================
# Pkl (https://pkl-lang.org)
# =====================================================================================================

# The generated script runs a bare `compinit` (a full $fpath rescan plus security audit) that 20-completion already
# did; a no-op stands in for compinit while the cached script loads
if (( $+commands[pkl] )); then
    compinit() { : }
    cached_eval pkl pkl shell-completion zsh
    unfunction compinit
    autoload -Uz compinit
fi
