# =====================================================================================================================
# Debian-family /etc/zsh/zshrc runs an unguarded `compinit` (no -i) that prompts or aborts on insecure $fpath
# directories (e.g. group-writable Linuxbrew share dirs). zsh reads ~/.zshenv before /etc/zsh/zshrc, so setting this
# here skips it; conf.d/20-completion.zsh owns the only compinit.
# =====================================================================================================================
skip_global_compinit=1
