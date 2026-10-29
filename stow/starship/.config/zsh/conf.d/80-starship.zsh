# =====================================================================================================
# Starship (https://starship.rs)
# =====================================================================================================

# Aliases
alias ss='starship'

# Generate & activate Starship zsh shell prompt (needs a terminal on stdin and a capable TERM; piped `zsh -c` and
# TERM=dumb contexts have neither, and `starship init` errors out there)
if (( $+commands[starship] )) && [[ -t 0 && "$TERM" != dumb ]]; then
    cached_eval starship starship init zsh
fi
