# =====================================================================================================
# forgit (https://github.com/wfxr/forgit)
# =====================================================================================================

# Activate git-forgit zsh plugin
source_if_exists "$HOMEBREW_PREFIX/share/forgit/forgit.plugin.zsh"

# Add `git forgit` aliases
[[ -n "$FORGIT_INSTALL_DIR" ]] && pathadd "$FORGIT_INSTALL_DIR/bin"

# Workaround for display width issue when `delta` pager used in `fzf` preview window
# https://github.com/wfxr/forgit/issues/121#issuecomment-725358145
export FORGIT_PAGER='delta --side-by-side -w ${FZF_PREVIEW_COLUMNS:-$COLUMNS}'

# Shorter alias for base git-forgit command
alias forgit=git-forgit

# =====================================================================================================
# worktrunk (https://worktrunk.dev)
# =====================================================================================================

# Activate `wt` shell configuration
if command -v wt >/dev/null 2>&1; then eval "$(command wt config shell init zsh)"; fi

# =====================================================================================================
# git aliases
# =====================================================================================================

alias gsl="git stash list"
alias gsp="git stash pop"
alias gs="git stash"
alias gsm="git stash push -m"
alias gd="git diff"             # git-forgit oh-my-zsh plugin overwrites this to ``forgit::diff``, but I don't want that
