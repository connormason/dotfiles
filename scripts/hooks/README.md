[Project Root](../../README.md) > **Hook Scripts**

---

# Hook Scripts

Custom pre-commit hook scripts for checks and transforms not covered by standard hooks. The Python scripts follow the
same interface contract as `pre-commit`: they accept a list of filenames as positional arguments and exit `0` on success
or non-zero on failure. They are wired into [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) as `local` repo
hooks and run via `prek` / `make pre`. Each is a self-contained PEP 723 script, so `uv run` resolves any dependencies in
isolation. [`uv-public.sh`](#uv-publicsh) is the exception: a shell wrapper around `uv` that consumes no filenames.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Scripts](#scripts)
- [Pre-Commit Wiring](#pre-commit-wiring)
- [`check-json5.py`](#check-json5py)
  - [Synopsis](#synopsis)
  - [Options](#options)
  - [Behavior](#behavior)
  - [Exit Codes](#exit-codes)
  - [Pre-Commit Integration](#pre-commit-integration)
- [`check-leaks.py`](#check-leakspy)
  - [Synopsis](#synopsis-1)
  - [Options](#options-1)
  - [Behavior](#behavior-1)
  - [Exit Codes](#exit-codes-1)
  - [Pre-Commit Integration](#pre-commit-integration-1)
- [`check-leaks-push.sh`](#check-leaks-pushsh)
  - [Synopsis](#synopsis-2)
  - [Behavior](#behavior-2)
  - [Exit Codes](#exit-codes-2)
  - [Pre-Commit Integration](#pre-commit-integration-2)
- [`check-pkl.py`](#check-pklpy)
  - [Synopsis](#synopsis-3)
  - [Options](#options-2)
  - [Behavior](#behavior-3)
  - [Exit Codes](#exit-codes-3)
  - [Pre-Commit Integration](#pre-commit-integration-3)
- [`format-pkl.py`](#format-pklpy)
  - [Synopsis](#synopsis-4)
  - [Options](#options-3)
  - [Behavior](#behavior-4)
  - [Exit Codes](#exit-codes-4)
  - [Pre-Commit Integration](#pre-commit-integration-4)
- [`sort-json-array.py`](#sort-json-arraypy)
  - [Synopsis](#synopsis-5)
  - [Options](#options-4)
  - [Behavior](#behavior-5)
  - [Exit Codes](#exit-codes-5)
  - [Pre-Commit Integration](#pre-commit-integration-5)
- [`uv-public.sh`](#uv-publicsh)
  - [Synopsis](#synopsis-6)
  - [Behavior](#behavior-6)
  - [Pre-Commit Integration](#pre-commit-integration-6)

<!-- mdformat-toc end -->

## Scripts<a name="scripts"></a>

| Script                                       | What it does                                                            | Hook id                                              | Priority          |
| -------------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------- | ----------------- |
| [`check-json5.py`](#check-json5py)           | Validate JSON5 file syntax via `pyjson5`                                | `check-json5`                                        | 10 (check phase)  |
| [`check-leaks.py`](#check-leakspy)           | Block employer-internal identifiers (content, paths, git identity)      | `check-leaks`, `check-leaks-msg`                     | 10 (check phase)  |
| [`check-leaks-push.sh`](#check-leaks-pushsh) | Pre-push scan of pushed commits' identities, messages, and added lines  | `check-leaks-push-history`, `check-leaks-push-files` | 10 (check phase)  |
| [`check-pkl.py`](#check-pklpy)               | Validate Pkl files by running `pkl eval --format yaml`                  | `check-pkl`                                          | 10 (check phase)  |
| [`format-pkl.py`](#format-pklpy)             | Auto-format Pkl files via `pkl format`                                  | `format-pkl`                                         | 35 (format phase) |
| [`sort-json-array.py`](#sort-json-arraypy)   | Sort a top-level JSON array of objects by a key                         | `sort-json-array`                                    | 30 (sort phase)   |
| [`uv-public.sh`](#uv-publicsh)               | Run uv against public PyPI only (wraps `uv-lock`/`uv-sync`/`uv-export`) | `uv-*`                                               | 0–5 (sync phase)  |

> [!NOTE]
> this repository does not currently contain any `.json5`, `.pkl`, or `keybindings.json` files, so the JSON5, Pkl, and
> sort hooks are staged for future use. Each is scoped so it matches nothing today and fires automatically the moment a
> matching file lands. `check-leaks` runs on every commit; the `uv-*` hooks run through `uv-public.sh` but fire only on
> their own triggers (`uv-lock` when `uv.lock`, `pyproject.toml`, or `uv.toml` is staged; `uv-sync` after checkout,
> merge, or rewrite).

## Pre-Commit Wiring<a name="pre-commit-wiring"></a>

The Python hooks are declared as `repo: local` entries in [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml),
slotted into the repository's priority scheme (the `uv-*` entries that call `uv-public.sh` are shown under its
[own section](#uv-publicsh)). The relevant stanzas are:

```yaml
  - repo: local
    hooks:
      - id: check-json5
        name: '[check]  json5 syntax'
        priority: 10
        entry: scripts/hooks/check-json5.py
        language: python
        files: .*\.json5$

      - id: check-pkl
        name: '[check]  pkl syntax'
        priority: 10
        entry: scripts/hooks/check-pkl.py
        language: python
        files: .*\.pkl$
        types: [file]

      - id: check-leaks
        name: '[check]  internal identifiers (leak guard)'
        stages: [pre-commit]
        priority: 10
        entry: scripts/hooks/check-leaks.py --identity
        language: python
        types: [text]
        always_run: true

      - id: check-leaks-msg
        name: '[check]  internal identifiers in commit message'
        stages: [commit-msg]
        entry: scripts/hooks/check-leaks.py
        language: python

  - repo: local
    hooks:
      - id: sort-json-array
        name: '[format] sorting (keybindings.json)'
        priority: 30
        stages: [pre-commit]
        entry: scripts/hooks/sort-json-array.py
        language: python
        files: .*keybindings\.json$
        args: [--key, command]

  - repo: local
    hooks:
      - id: format-pkl
        name: '[format] pkl (pkl format)'
        priority: 35
        stages: [pre-commit]    # skipped in CI
        entry: scripts/hooks/format-pkl.py
        language: python
        files: .*\.pkl$
        types: [file]
```

**Priority scheme** used across the whole config:

| Priority band | Phase             | Notes                                                                                          |
| ------------- | ----------------- | ---------------------------------------------------------------------------------------------- |
| 0–6           | Dependency sync   | `uv-lock`, `uv-sync`, `uv-export` (via `uv-public.sh`), `sync-with-uv`, `sync-pre-commit-deps` |
| 10            | Read-only checks  | Run in parallel; `check-json5`, `check-pkl`, `check-leaks` live here                           |
| 20–23         | Whitespace fixers | `fix-byte-order-marker`, `end-of-file-fixer`, `trailing-whitespace`, etc.                      |
| 30–35         | Formatters        | `keep-sorted`, `sort-json-array` (30); `shfmt`, `format-pkl`, etc. (35)                        |
| 40            | Linters           | `ruff`, `mypy`, `yamllint`, `shellcheck`, `codespell`                                          |

The `format-pkl` hook carries `stages: [pre-commit]` so it is skipped when the config is run in CI (`manual` stage).
`check-pkl` and `check-json5` run in all stages (`check-leaks` is `pre-commit` only and `check-leaks-msg` is
`commit-msg` only; the `check-leaks-push-*` hooks are `pre-push` only; CI runs its own job). `sort-json-array` runs at
priority 30 (before the priority-35 `pretty-format-json` formatter) so a reordered array is normalized once and surfaces
in the diff to re-stage rather than landing silently.

Both Pkl hooks are tolerant of environments where `pkl` is not installed: by default they print a warning and exit `0`.
Pass `--require-pkl` to make the missing binary a hard failure.

---

## `check-json5.py`<a name="check-json5py"></a>

### Synopsis<a name="synopsis"></a>

Validates that every supplied `.json5` file parses successfully via `pyjson5`. Declared as a PEP 723 inline-script with
`pyjson5` as a dependency so `uv run` can execute it in isolation.

```
python3 scripts/hooks/check-json5.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options"></a>

| Flag              | Description                                       | Default |
| ----------------- | ------------------------------------------------- | ------- |
| `FILENAMES`       | One or more `.json5` files to validate            | —       |
| `-v`, `--verbose` | Print a per-file `INFO` line for every valid file | off     |
| `-h`, `--help`    | Show help and exit                                | —       |

### Behavior<a name="behavior"></a>

For each filename:

1. Opens the file and calls `pyjson5.load()`.
2. On `Json5DecoderException` — prints `ERROR <filename>` followed by the exception class and message (indented),
   records failure.
3. On any other exception — prints `ERROR <filename>` followed by `Unable to decode JSON5: <exc>`.
4. On success with `--verbose` — prints `INFO <filename>` followed by `Valid JSON5`.

All output is ANSI-colored. The script exits non-zero if any file fails.

### Exit Codes<a name="exit-codes"></a>

| Code | Meaning                                |
| ---- | -------------------------------------- |
| `0`  | All files valid (or no files supplied) |
| `1`  | One or more files failed to parse      |

### Pre-Commit Integration<a name="pre-commit-integration"></a>

```yaml
  - id: check-json5
    entry: scripts/hooks/check-json5.py
    language: python
    files: .*\.json5$
```

pre-commit passes all staged `.json5` files as positional arguments. The `language: python` runtime means pre-commit
manages the `pyjson5` dependency automatically using the inline PEP 723 metadata.

---

## `check-leaks.py`<a name="check-leakspy"></a>

### Synopsis<a name="synopsis-1"></a>

Blocks employer-internal identifiers from entering this public repository. Every supplied file's **path** and
**contents** are matched against a built-in public baseline plus optional private patterns kept outside the repository,
and the git author/committer **identity** can be checked as well. Pure-stdlib PEP 723 script (no dependencies).

```
python3 scripts/hooks/check-leaks.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options-1"></a>

#### Positional

| Argument    | Description                                |
| ----------- | ------------------------------------------ |
| `FILENAMES` | Files whose paths and contents are scanned |

#### Identity options

| Flag                     | Description                                                                       | Default |
| ------------------------ | --------------------------------------------------------------------------------- | ------- |
| `--identity`             | Also check the git author/committer identity of the commit being made             | off     |
| `--identities-from FILE` | Check one `Name <email>` identity per line from `FILE` (`-` reads standard input) | —       |

#### Pattern options

| Flag                   | Description                                 | Default                                                                                  |
| ---------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `--patterns-file PATH` | Private pattern file; must exist when given | `$DOTFILES_LEAK_PATTERNS`, else `$XDG_CONFIG_HOME/dotfiles/leak-patterns.txt` if present |

#### Output options

| Flag              | Description                                                         | Default |
| ----------------- | ------------------------------------------------------------------- | ------- |
| `-v`, `--verbose` | Report clean results too (to stderr, with the active pattern count) | off     |

#### Other

| Flag           | Description        |
| -------------- | ------------------ |
| `-h`, `--help` | Show help and exit |

### Behavior<a name="behavior-1"></a>

**Pattern sources.** All patterns are case-insensitive regular expressions, applied line by line to file contents and to
the whole path string.

1. *Public baseline* (built in): the employer's corporate domain, including any subdomain and any email address at it;
   and the internal bug-tracker URL schemes. Only the bare public vendor hosts (`www`, `apps`, `developer`, `support`
   directly under the corporate domain) are exempt, so plist DTDs and App Store or developer-documentation links pass;
   any further subdomain beneath one of them is still flagged.
2. *Private patterns* (optional): one regex per line; blank lines and `#` comments are ignored. These carry identifiers
   that must not be spelled out in a public repository (hostnames, project code names), so the file lives outside the
   repo and is supplied by the private work overlay. Exactly one private file is loaded, chosen by precedence:
   `--patterns-file` > `$DOTFILES_LEAK_PATTERNS` > `$XDG_CONFIG_HOME/dotfiles/leak-patterns.txt` (`~/.config` when
   `XDG_CONFIG_HOME` is unset). The first two are explicit and **must exist**; the XDG default is optional and silently
   skipped when absent. The baseline always applies in addition.

**Fail-closed rules.** A guard that quietly stops guarding is worse than none, so configuration problems abort with exit
`2` instead of degrading: a pattern file that is missing (when explicit: `--patterns-file` or the environment variable),
a pattern path that exists but is not a readable UTF-8 regular file (explicit or the default location, so a dangling
symlink or a directory at the default path aborts rather than silently reverting to the baseline), an invalid regex, a
pattern that matches the empty string (it would flag every line), a failed `git var`, or an unreadable/undecodable
`--identities-from` file. Only an absent default file is skipped silently. A target file that cannot be read is reported
and yields exit `1`.

**Scanning.** A file is scanned by path first, then by content unless a NUL byte appears in its first 8 KiB (treated as
binary; its path is still checked). Invalid UTF-8 is decoded with replacement characters rather than skipped.

**Self-non-matching regex convention.** Patterns must not match their own source text, so this script and the pattern
documentation can be scanned like any other file without an exclusion list. The baseline does this by escaping the dot
before the TLD and writing the tracker URL's double slash as `/{2}`; follow the same trick in private patterns that may
be quoted in tracked files.

**Allow marker.** A line containing `leak-guard: allow` is skipped for content matches. Path and identity matches cannot
be waived.

**Masking.** Findings never re-publish a leak. Each match is printed with only its first and last characters visible,
and scanned data echoed back (file paths, identities, OS error text for unreadable targets) has pattern matches masked
the same way. Configuration errors (exit `2`) are printed as-is, since they describe the setup rather than scanned data:
the pattern-file path, or the stderr of a failed `git var`. At most 5 findings are listed per source, followed by
`... and N more`.

**Identity checks.** `--identity` resolves what git will record for the commit via `git var GIT_AUTHOR_IDENT` and
`git var GIT_COMMITTER_IDENT`. `--identities-from` takes identities from a file or standard input instead, which suits
CI where the identities of past commits are fed in via `git log --format`. The two flags can be combined.

**CI.** The `leak guard` job in [`.github/workflows/leaks.yml`](../../.github/workflows/leaks.yml) checks out the full
history and runs three scans (the baseline only; the runner has no private pattern file):

1. Every tracked file (`git ls-files -z | xargs -0 ... --`).
2. Commit **messages of new commits only**, written to a temporary file and scanned like any other file. Older history
   predates the guard (a few early messages contain the corporate domain) and is deliberately not rescanned. Pull
   requests cover `base..head`; a push covers `before..sha`. A new-branch push (all-zero `before` SHA), a `before` SHA
   that is not reachable in the clone, or a manual `workflow_dispatch` run falls back to the tip commit only.
3. The author/committer identities of **all reachable history** through `--identities-from -` (history is clean, so no
   range is needed).

The runner has no git identity, so `--identity` is not used there. Unit tests run in the `pytest` job of
[`.github/workflows/lint.yml`](../../.github/workflows/lint.yml).

### Exit Codes<a name="exit-codes-1"></a>

| Code | Meaning                                                                                  |
| ---- | ---------------------------------------------------------------------------------------- |
| `0`  | No findings                                                                              |
| `1`  | One or more findings, or a target file could not be read                                 |
| `2`  | Configuration error (see fail-closed rules above); no findings are reported for that run |

### Pre-Commit Integration<a name="pre-commit-integration-1"></a>

```yaml
  - id: check-leaks
    entry: scripts/hooks/check-leaks.py --identity
    language: python
    types: [text]
    always_run: true
    stages: [pre-commit]

  - id: check-leaks-msg
    entry: scripts/hooks/check-leaks.py
    language: python
    stages: [commit-msg]
```

`always_run: true` keeps the identity check firing even for commits that stage no text files. `types: [text]` makes prek
skip binary files entirely, so locally neither their paths nor contents are checked; they are covered only by the CI
scan of every tracked file (`git ls-files`). The `check-leaks` hook runs only at the `pre-commit` stage.
`prek run check-leaks --all-files` audits every tracked file on demand.

`check-leaks-msg` runs at the `commit-msg` stage, where prek passes the path of the commit message file as the filename,
so the unmodified script scans the message like any other file (the identity is already covered by `check-leaks`).
`commit-msg` is listed in `default_install_hook_types`, so `prek install` installs its shim. A rejected message aborts
the commit; amend the wording and commit again.

---

## `check-leaks-push.sh`<a name="check-leaks-pushsh"></a>

### Synopsis<a name="synopsis-2"></a>

Pre-push leak scan of the commits being pushed: their author/committer identities, commit messages, and every line they
add, fed to [`check-leaks.py`](#check-leakspy). `cherry-pick`, `rebase`, `am`, and `git commit --no-verify` bypass the
`pre-commit` and `commit-msg` hooks, so this is the last local gate before content reaches the public remote. It takes
no arguments.

### Behavior<a name="behavior-2"></a>

**Range.** Read from the environment prek exports to `pre-push` hooks, `PRE_COMMIT_FROM_REF` and `PRE_COMMIT_TO_REF`
(`to` defaults to `HEAD`):

1. `FROM..TO` when the from-ref resolves to a commit in the local repository.
2. Otherwise `merge-base(TO, origin/main)..TO` (a new branch, or a from-ref that is not present locally).
3. Otherwise the tip commit only (`-1 TO`).

Commits before the range are not scanned. Commit messages are written to a temporary file and scanned like any other
file; identities are piped to `check-leaks.py --identities-from -`.

**Patches.** The added lines of every pushed commit
(`git log -p -U0 --cc --no-textconv --format='commit %h' --no-color <range>`; `--cc` shows the combined diff of merge
commits, so a leak introduced by a conflict resolution is seen) are written to a temporary file and scanned too, so
content that one pushed commit adds and a later one removes is caught even though the tip is clean. Removed and context
lines are blanked rather than deleted: a removed line was either added earlier in the range (and is caught there) or is
already public, and blanking keeps the reported line numbers aligned with that command's output. The paths each pushed
commit adds, copies, or renames to
(`git log --name-only --diff-filter=ACR --cc --format='commit %h' --no-color <range>`) are appended to the same file,
because a leak that lives only in a path (an empty file, a pure rename) has no added line. The script prints
`pre-push: scanning <range>` first and, on findings, `pre-push: inspect with: <the patch command>` followed by
`pre-push: and (paths): <the path command>`.

**File contents** at the tip are scanned by the separate `check-leaks-push-files` hook entry, which prek feeds the files
changed between the two refs.

### Exit Codes<a name="exit-codes-2"></a>

Those of `check-leaks.py`: `0` clean, `1` findings, `2` configuration error (for example an unreadable private pattern
file).

### Pre-Commit Integration<a name="pre-commit-integration-2"></a>

```yaml
  - id: check-leaks-push-files
    entry: scripts/hooks/check-leaks.py
    language: python
    types: [text]
    stages: [pre-push]

  - id: check-leaks-push-history
    entry: scripts/hooks/check-leaks-push.sh
    language: system
    pass_filenames: false
    always_run: true
    stages: [pre-push]
```

`pre-push` is listed in `default_install_hook_types`, so `prek install` installs its shim. To exercise the hooks without
pushing: `prek run --hook-stage pre-push --from-ref origin/main --to-ref HEAD`.

---

## `check-pkl.py`<a name="check-pklpy"></a>

### Synopsis<a name="synopsis-3"></a>

Validates Pkl configuration files by running `pkl eval --format yaml` against each file. If `pkl` is not found on `PATH`
the script warns and exits `0` (non-blocking) unless `--require-pkl` is set.

```
python3 scripts/hooks/check-pkl.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options-2"></a>

#### Positional

| Argument    | Description                          |
| ----------- | ------------------------------------ |
| `FILENAMES` | One or more `.pkl` files to validate |

#### Pkl executable options

| Flag                | Description                                                        | Default                      |
| ------------------- | ------------------------------------------------------------------ | ---------------------------- |
| `--require-pkl`     | Exit non-zero if `pkl` binary not found (default: warn and exit 0) | off                          |
| `--executable PATH` | Path to `pkl` binary                                               | `pkl` (resolved from `PATH`) |

#### Output options

| Flag                          | Description                                             | Default  |
| ----------------------------- | ------------------------------------------------------- | -------- |
| `-v`, `--verbose`             | Print per-file `INFO` line for valid files              | off      |
| `--dump-yaml`                 | Print the YAML output generated by `pkl eval` to stdout | off      |
| `--color never\|auto\|always` | ANSI color control (forwarded to `pkl eval --color`)    | `always` |

#### Execution options

| Flag                              | Description                                                     | Default |
| --------------------------------- | --------------------------------------------------------------- | ------- |
| `-t SECONDS`, `--timeout SECONDS` | Per-file evaluation timeout (forwarded to `pkl eval --timeout`) | none    |

#### Package options

| Flag         | Description                                                   | Default |
| ------------ | ------------------------------------------------------------- | ------- |
| `--no-cache` | Disable Pkl package cache (passes `--no-cache` to `pkl eval`) | off     |

#### Other

| Flag           | Description        |
| -------------- | ------------------ |
| `-h`, `--help` | Show help and exit |

### Behavior<a name="behavior-3"></a>

1. Checks `shutil.which(args.executable)`. If not found: warn and return `0`, or error and return `1` if `--require-pkl`
   is set.
2. Builds the base command: `pkl eval --format yaml [--color ...] [--timeout ...] [--no-cache]`.
3. For each file, runs the command via `subprocess.run(check=True, capture_output=True)`.
4. On `CalledProcessError` — prints `ERROR <filename>` with the stderr content (strips the redundant `–– Pkl Error ––`
   header that `pkl` emits).
5. On success with `--verbose` — prints `INFO <filename>` followed by `Valid Pkl`.
6. With `--dump-yaml` — prints the evaluated YAML output below the per-file status line.

### Exit Codes<a name="exit-codes-3"></a>

| Code | Meaning                                                                                 |
| ---- | --------------------------------------------------------------------------------------- |
| `0`  | All files valid, or `pkl` not installed (without `--require-pkl`), or no files supplied |
| `1`  | One or more files failed validation, or `pkl` not found with `--require-pkl`            |

### Pre-Commit Integration<a name="pre-commit-integration-3"></a>

```yaml
  - id: check-pkl
    entry: scripts/hooks/check-pkl.py
    language: python
    files: .*\.pkl$
    types: [file]
```

---

## `format-pkl.py`<a name="format-pklpy"></a>

### Synopsis<a name="synopsis-4"></a>

Auto-formats Pkl files in-place using `pkl format`. Detects files that need formatting (exit code `11` from
`pkl format --diff-name-only`) and rewrites them with `--write`. Reports `MODIFIED` or `UNMODIFIED` per file. If `pkl`
is not on `PATH`, warns and exits `0` unless `--require-pkl` is set.

```
python3 scripts/hooks/format-pkl.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options-3"></a>

#### Positional

| Argument    | Description                        |
| ----------- | ---------------------------------- |
| `FILENAMES` | One or more `.pkl` files to format |

#### Pkl executable options

| Flag                | Description                             | Default                      |
| ------------------- | --------------------------------------- | ---------------------------- |
| `--require-pkl`     | Exit non-zero if `pkl` binary not found | off                          |
| `--executable PATH` | Path to `pkl` binary                    | `pkl` (resolved from `PATH`) |

#### Grammar options

| Flag                     | Description                                                      | Default |
| ------------------------ | ---------------------------------------------------------------- | ------- |
| `--grammar-version 1\|2` | Pkl grammar compatibility version (`1` = 0.25–0.29, `2` = 0.30+) | `2`     |

#### Output options

| Flag              | Description                                              | Default |
| ----------------- | -------------------------------------------------------- | ------- |
| `-v`, `--verbose` | Print `UNMODIFIED` line for files that needed no changes | off     |
| `-h`, `--help`    | Show help and exit                                       | —       |

### Behavior<a name="behavior-4"></a>

1. Checks `shutil.which(args.executable)`. If not found: warn and return `0`, or error and return `1` if
   `--require-pkl`.
2. Builds the base command: `pkl format --diff-name-only [--grammar-version N]`.
3. For each file:
   - Runs `pkl format --diff-name-only <file>`. Exit `0` means already formatted; exit `11` means the file needs
     reformatting.
   - On exit `11` — re-runs with `--write` to reformat in-place, prints `MODIFIED <filename>`.
   - On any other non-zero exit — prints `ERROR <filename>` with stderr (suppressing the generic
     `An error occurred during formatting.` line), and records the exit code.
4. With `--verbose`, prints `UNMODIFIED <filename>` for files that required no changes.

The exit code of the hook is the maximum non-zero return code seen across all files, or `0` if all succeeded.

### Exit Codes<a name="exit-codes-4"></a>

| Code     | Meaning                                                                                               |
| -------- | ----------------------------------------------------------------------------------------------------- |
| `0`      | All files formatted or already correct, or `pkl` not installed (without `--require-pkl`), or no files |
| `1`      | `pkl` not found with `--require-pkl`, or an unexpected exception occurred                             |
| `N` (>0) | Maximum `pkl format` exit code across all failing files                                               |

### Pre-Commit Integration<a name="pre-commit-integration-4"></a>

```yaml
  - id: format-pkl
    entry: scripts/hooks/format-pkl.py
    language: python
    files: .*\.pkl$
    types: [file]
    stages: [pre-commit]  # not run in CI
```

The `stages: [pre-commit]` restriction means this hook only runs during interactive `git commit` (and `make pre`). CI
pipelines run `check-pkl` (read-only) instead of attempting in-place formatting.

---

## `sort-json-array.py`<a name="sort-json-arraypy"></a>

### Synopsis<a name="synopsis-5"></a>

Sorts a top-level JSON array of objects in-place by the value of a chosen object key. Pure-stdlib PEP 723 script (no
dependencies). The file is rewritten only when the sorted result differs from the original.

```
python3 scripts/hooks/sort-json-array.py [OPTIONS] [FILENAMES...]
```

### Options<a name="options-4"></a>

| Flag              | Description                                           | Default   |
| ----------------- | ----------------------------------------------------- | --------- |
| `FILENAMES`       | One or more JSON files (top-level array of objects)   | —         |
| `-k`, `--key`     | Object key whose value each array entry is sorted by  | `command` |
| `--indent`        | Number of spaces to indent the rewritten JSON by      | `4`       |
| `-v`, `--verbose` | Print a per-file `INFO` line for already-sorted files | off       |
| `-h`, `--help`    | Show help and exit                                    | —         |

### Behavior<a name="behavior-5"></a>

For each filename:

1. Reads and parses the file as JSON.
2. On a decode error, or if the top level is not an array of objects — prints `ERROR <filename>` with the reason,
   records failure.
3. Stably sorts the array by `entry.get(key, '')` (entries missing the key sort first; equal keys keep their original
   relative order).
4. Re-serializes and, if the result differs, rewrites the file in-place and prints `INFO <filename>` /
   `Sorted array by '<key>'`.
5. If already sorted — with `--verbose`, prints `INFO <filename>` / `Already sorted by '<key>'`.

### Exit Codes<a name="exit-codes-5"></a>

| Code | Meaning                                                                           |
| ---- | --------------------------------------------------------------------------------- |
| `0`  | Every file already sorted (or no files supplied)                                  |
| `1`  | One or more files were rewritten, failed to parse, or are not an array of objects |

### Pre-Commit Integration<a name="pre-commit-integration-5"></a>

```yaml
  - id: sort-json-array
    entry: scripts/hooks/sort-json-array.py
    language: python
    args: [--key, command]
    files: .*keybindings\.json$
```

Scoped to any `keybindings.json`, this keeps such a file's array ordered by each entry's `command` value. It runs at
priority 30 (before the priority-35 `pretty-format-json` formatter), so a reordered file is normalized once and surfaces
in the diff to re-stage rather than landing silently. The default `--key command` also makes the hook usable as-is for
other keybindings-style JSON.

---

## `uv-public.sh`<a name="uv-publicsh"></a>

### Synopsis<a name="synopsis-6"></a>

Shell wrapper that runs `uv` against public PyPI only. Work machines inject an internal package index, and a plain `uv`
invocation there rewrites `uv.lock` to reference that index, which would leak it into this public repository. Unlike the
Python scripts above it consumes no filenames; it forwards all arguments to `uv`.

```
scripts/hooks/uv-public.sh <uv arguments...>
```

### Behavior<a name="behavior-6"></a>

The wrapper neutralizes the internal index through **both** channels it arrives by, then `exec`s `uv`:

1. `unset UV_INDEX_URL UV_DEFAULT_INDEX UV_EXTRA_INDEX_URL UV_INDEX UV_CONFIG_FILE UV_FIND_LINKS` removes index settings
   injected via environment variables, plus an explicit config path and extra package source that could smuggle the same
   index in.
2. `export UV_NO_CONFIG=1` makes uv ignore user-level and system `uv.toml` files, where an extra index URL may also be
   configured (uv consults them ahead of any project default index).

Both are required: verified 2026-10-26, either one alone still produced a `uv.lock` referencing the internal index.
`UV_NO_CONFIG` skips only user/system config, so this project's own `[tool.uv]` table in `pyproject.toml` still applies.

**Self-healing lock.** The `uv-lock` hook runs `scripts/hooks/uv-public.sh lock --refresh`. The `--refresh` flag is
essential: without it, `uv lock` keeps the registry URLs already recorded in an existing lock and does nothing, so a
polluted lock would never be repaired. With it, whenever `uv.lock`, `pyproject.toml`, or `uv.toml` is staged, a lock
that was regenerated with the internal index is rewritten back to public PyPI before the commit lands.

**Always use it instead of bare `uv` in this repo** (for example `scripts/hooks/uv-public.sh run pytest`, or
`scripts/hooks/uv-public.sh sync --group test`).

### Pre-Commit Integration<a name="pre-commit-integration-6"></a>

```yaml
  - id: uv-lock
    entry: scripts/hooks/uv-public.sh lock --refresh
    language: system
    files: ^(uv\.lock|pyproject\.toml|uv\.toml)$
    pass_filenames: false
```

`uv-sync` (`sync --no-active --locked`) and `uv-export` use the same wrapper with `language: system` and
`pass_filenames: false`.
