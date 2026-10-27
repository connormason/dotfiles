# =====================================================================================================
# bun
# =====================================================================================================

source_if_exists "$HOME/.bun/_bun"

# Add `bun` installation & binaries to PATH
export BUN_INSTALL="$HOME/.bun"
pathadd "$BUN_INSTALL/bin"
