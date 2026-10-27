# =====================================================================================================
# zoxide (https://github.com/ajeetdsouza/zoxide)
# =====================================================================================================

# Generate & activate zoxide shell configuration
if (( $+commands[zoxide] )); then
    eval "$(zoxide init zsh)"
fi
