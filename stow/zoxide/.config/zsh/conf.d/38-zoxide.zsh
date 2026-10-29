# =====================================================================================================
# zoxide (https://github.com/ajeetdsouza/zoxide)
# =====================================================================================================

# Generate & activate zoxide shell configuration (not cached: the output varies with $_ZO_ECHO and
# $_ZO_RESOLVE_SYMLINKS)
if (( $+commands[zoxide] )); then
    eval "$(zoxide init zsh)"
fi
