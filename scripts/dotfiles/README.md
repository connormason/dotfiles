[Project Root](../../README.md) > **Dotfiles Tools**

# Dotfiles Tools

Helper tools for the layered dev-environment engine. Currently one tool: `render.py`.

## render.py

Renders JSON settings files from per-layer fragments. Each layer (the base repo first, then each overlay registered via
`bootstrap/lib.sh`) may provide `render/<target>.json`. Fragments deep-merge in layer order into a **real file** at the
target's path; a drift guard refuses to overwrite edits made in the app since the last render.

### Targets

| Target   | Rendered file                                           |
| -------- | ------------------------------------------------------- |
| `claude` | `~/.claude/settings.json`                               |
| `vscode` | `~/Library/Application Support/Code/User/settings.json` |

A target for which no layer provides a fragment is skipped.

### Merge semantics

| Value type | Rule                                                                 |
| ---------- | -------------------------------------------------------------------- |
| Objects    | Deep-merge                                                           |
| Arrays     | Concatenate, de-duplicating by canonical JSON while preserving order |
| Scalars    | Later layer wins                                                     |
| `null`     | In a later layer, deletes the key                                    |

Output is deterministic: sorted keys, 2-space indent, trailing newline.

### `$unmanaged`

A fragment's top-level `"$unmanaged"` is a list of top-level key names owned by the app or an installer. The lists merge
across layers. Those keys are never written from fragments, are preserved from the live file on render, and are ignored
by drift and `--check` comparison.

### Drift guard

The last managed render is stored as `${XDG_STATE_HOME:-~/.local/state}/dotfiles/render/<target>.json`. Drift means the
live managed content differs from **both** the stored last render and the new render. A drifted target is refused (with
a diff on stderr) unless `--force` is given, which first copies the live file to
`~/.dotfiles-backup/<YYYYmmdd-HHMMSS>/<path relative to HOME>`. A pre-existing file equal to the new render is adopted
without `--force`. A symlink at the target is replaced by a real file; the symlink's target is never written.

### Usage

```
render.py [TARGET…] [--diff | --check] [--force] [--repo PATH] [-v]
```

| Flag      | Effect                                                          |
| --------- | --------------------------------------------------------------- |
| `--diff`  | Show live-vs-rendered differences; write nothing                |
| `--check` | Exit 1 if a target is out of sync; write nothing                |
| `--force` | Overwrite in-app edits (live file is backed up first)           |
| `--repo`  | Base repository root (default: the repo containing this script) |
| `-v`      | Report skipped and already-current targets                      |

Exit codes: `0` ok / in sync, `1` drift refused or out of sync, `2` configuration error (bad fragment, unknown target,
missing overlay).

### Worked example

Base `render/claude.json`:

```json
{
  "theme": "dark",
  "permissions": {
    "allow": [
      "Read",
      "Grep"
    ]
  },
  "$unmanaged": [
    "installMethod"
  ]
}
```

Overlay `render/claude.json`:

```json
{
  "theme": null,
  "permissions": {
    "allow": [
      "Grep",
      "Bash(ls:*)"
    ]
  },
  "env": {
    "EXAMPLE": "1"
  }
}
```

Rendered `~/.claude/settings.json` (an existing `installMethod` key in the live file is carried over untouched):

```json
{
  "env": {
    "EXAMPLE": "1"
  },
  "permissions": {
    "allow": [
      "Read",
      "Grep",
      "Bash(ls:*)"
    ]
  }
}
```
