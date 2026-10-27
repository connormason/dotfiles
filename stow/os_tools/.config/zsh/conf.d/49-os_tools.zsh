# =====================================================================================================
# ranger (https://github.com/ranger/ranger/wiki/Official-user-guide)
# =====================================================================================================

# Aliases
alias ra="ranger"

# =====================================================================================================
# eza (https://github.com/eza-community/eza)
# =====================================================================================================

# `ls` -> `eza` replacements (skipped when eza is absent, so `ls` keeps working)
if (( $+commands[eza] )); then
    # Point `eza` at its config directory (holds theme.yml)
    export EZA_CONFIG_DIR="$HOME/.config/eza"

    LS_LOPTS="--icons --git-repos --git --octal-permissions --time-style long-iso"  # Common options for aliases below

    alias ls="eza ${LS_LOPTS}"
    alias l="eza -l ${LS_LOPTS}"
    alias ll="eza -l ${LS_LOPTS}"
    alias la="eza -la ${LS_LOPTS}"
    alias lah="eza -lah ${LS_LOPTS}"
    alias lsa="eza -lah ${LS_LOPTS}"
    alias lt="eza --tree ${LS_LOPTS}"
    alias lt1="eza --tree --level=1 ${LS_LOPTS}"
    alias lt2="eza --tree --level=2 ${LS_LOPTS}"
    alias lt3="eza --tree --level=3 ${LS_LOPTS}"
    alias lt4="eza --tree --level=4 ${LS_LOPTS}"
    alias lt5="eza --tree --level=5 ${LS_LOPTS}"
    alias lta="eza -la --tree ${LS_LOPTS}"
    alias lta1="eza -la --tree --level=1 ${LS_LOPTS}"
    alias lta2="eza -la --tree --level=2 ${LS_LOPTS}"
    alias lta3="eza -la --tree --level=3 ${LS_LOPTS}"
    alias lta4="eza -la --tree --level=4 ${LS_LOPTS}"
    alias lta5="eza -la --tree --level=5 ${LS_LOPTS}"
    alias lat="eza -la --tree ${LS_LOPTS}"
    alias lat1="eza -la --tree --level=1 ${LS_LOPTS}"
    alias lat2="eza -la --tree --level=2 ${LS_LOPTS}"
    alias lat3="eza -la --tree --level=3 ${LS_LOPTS}"
    alias lat4="eza -la --tree --level=4 ${LS_LOPTS}"
    alias lat5="eza -la --tree --level=5 ${LS_LOPTS}"
    alias llt="eza -l --tree ${LS_LOPTS}"
    alias llt1="eza -l --tree --level=1 ${LS_LOPTS}"
    alias llt2="eza -l --tree --level=2 ${LS_LOPTS}"
    alias llt3="eza -l --tree --level=3 ${LS_LOPTS}"
    alias llt4="eza -l --tree --level=4 ${LS_LOPTS}"
    alias llt5="eza -l --tree --level=5 ${LS_LOPTS}"
fi
