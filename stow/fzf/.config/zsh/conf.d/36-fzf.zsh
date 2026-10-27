# =====================================================================================================
# FZF (https://github.com/junegunn/fzf)
# =====================================================================================================

# Activate `fzf` shell configuration (needs a terminal on stdin: piped `zsh -c` has no ZLE, and the integration's
# option restore errors out there)
if (( $+commands[fzf] )) && [[ -t 0 ]]; then
    source <(fzf --zsh)
fi
# export FZF_CTRL_T_OPTS="
#   --walker-skip .git,.idea,.mypy_cache,.pytest_cache,.ruff_cache,.venv,__pycache__,node_modules,venv
#   --preview 'bat -n --color=always {}'
#   --bind 'ctrl-/:change-preview-window(down|hidden|)'"

# Configure `fzf` default commands & shortcuts (only when `fd` is available to provide them)
if (( $+commands[fd] )); then
    export FZF_DEFAULT_COMMAND='fd --type f --hidden --follow --exclude .git'
    export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
    export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git'
fi
