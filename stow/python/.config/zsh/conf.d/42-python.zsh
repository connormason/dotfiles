# =====================================================================================================
# Python
# =====================================================================================================

# Basic aliases
alias p="ipython"
alias sourcevenv="source venv/bin/activate"

# Default directory `pew` creates virtualenvs within
export WORKON_HOME=$HOME/.virtualenvs

# =====================================================================================================
# uv (https://docs.astral.sh/uv/)
# =====================================================================================================

# Generate & activate `uv` shell completions
if (( $+commands[uv] )); then
    eval "$(uv generate-shell-completion zsh)"
fi
