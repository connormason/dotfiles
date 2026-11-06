[Project Root](../README.md) > **render**

# render

Base-layer settings fragments consumed by [`scripts/dotfiles/render.py`](../scripts/dotfiles/README.md#renderpy), which
deep-merges them with the fragments of any overlay into real settings files.

| Fragment                     | Render target | Rendered file                                           |
| ---------------------------- | ------------- | ------------------------------------------------------- |
| [`claude.json`](claude.json) | `claude`      | `~/.claude/settings.json`                               |
| [`vscode.json`](vscode.json) | `vscode`      | `~/Library/Application Support/Code/User/settings.json` |

Overlays contribute their own fragments under `<profile>/render/`, for example
[`profiles/personal-mac/render/claude.json`](../profiles/personal-mac/render/claude.json). Merge order, the `$unmanaged`
key list, and the drift guard are documented in the [render tool README](../scripts/dotfiles/README.md#renderpy).
