# =============================================================================
# Path
# =============================================================================

# Basic PATH additions (pathadd is defined in 00-lib.zsh)
# Keep PATH and FPATH free of duplicates (nested shells inherit both from their parent)
typeset -U path fpath
pathadd "/usr/local/sbin"
pathadd "$HOME/.local/bin"
