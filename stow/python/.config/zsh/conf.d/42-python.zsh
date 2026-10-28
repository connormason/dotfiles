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
    cached_eval uv uv generate-shell-completion zsh
fi
