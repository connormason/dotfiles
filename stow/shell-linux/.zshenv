# =====================================================================================================================
# Debian/Ubuntu's /etc/zsh/zshrc can run its own unguarded `compinit` (no -i), which prompts or aborts on insecure $fpath
# directories (e.g. group-writable Linuxbrew share dirs) unless skip_global_compinit is set. zsh reads ~/.zshenv before
# /etc/zsh/zshrc, so setting it here skips that; conf.d/20-completion.zsh owns the only compinit.
# Keep this file minimal: every zsh, including scripts, sources it.
# =====================================================================================================================
skip_global_compinit=1
