[Project Root](../README.md) > **Scripts**

# Scripts

Helper scripts for the repository: the render tool, prek hook scripts, standalone tool installers, Python environment
utilities, codebase maintenance, and the NAS deploy script.

| Directory                    | Contents                                                                             |
| ---------------------------- | ------------------------------------------------------------------------------------ |
| [`codebase/`](codebase/)     | `update_gitignore.py`: refreshes the generated `.gitignore` block (scheduled)        |
| [`docs_audit/`](docs_audit/) | `docs_audit` package: deterministic per-directory README audit (`run.py docs-audit`) |
| [`dotfiles/`](dotfiles/)     | `render.py`: merges settings fragments across layers                                 |
| [`env/`](env/)               | `loadenv.py`, `python_diagnostic.py`, `venvshell.py`: Python environment utilities   |
| [`hooks/`](hooks/)           | prek hook scripts and `uv-public.sh`, the public-index `uv` wrapper                  |
| [`install/`](install/)       | `install_uv.py`, `install_hatch.py`: standalone tool installers                      |
| [`nas/`](nas/)               | `deploy-services.sh`: syncs `services/` to the NAS and runs `deploy.sh`              |
| [`utility/`](utility/)       | `generate_completions.py`, `summarize_stow.awk`                                      |

[`STYLE-GUIDE.md`](STYLE-GUIDE.md) documents the console-output and argparse conventions these scripts share; `run.py`
is its reference implementation.

## Subdirectory READMEs

- [Codebase scripts](codebase/README.md)
- [Docs audit](docs_audit/README.md)
- [Dotfiles tools](dotfiles/README.md)
- [Env scripts](env/README.md)
- [Hook scripts](hooks/README.md)
- [Install scripts](install/README.md)
- [NAS scripts](nas/README.md)
