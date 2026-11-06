[Project Root](../../README.md) > [Scripts](../README.md) > **docs_audit**

# docs_audit — deterministic per-directory README audit

Emits the mechanical half of a README review: which directories are missing a README, which READMEs are stale candidates
(by commit timestamp), and which existing READMEs have structural, broken-link, or content-policy issues. Judging
whether a README's content has drifted from its code stays with a human or an LLM.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Usage](#usage)
- [Directory classes](#directory-classes)
- [Module structure](#module-structure)
- [API Quick Reference](#api-quick-reference)
  - [report.py](#reportpy)
  - [discover.py](#discoverpy)
  - [classify.py](#classifypy)
  - [checks.py](#checkspy)
  - [audit.py](#auditpy)
  - [conventions.py](#conventionspy)
- [Core components](#core-components)
  - [AuditReport](#auditreport)
  - [AuditReportSummaryDict](#auditreportsummarydict)
  - [style / unstyle](#style--unstyle)
- [JSON envelope](#json-envelope)
- [Dependencies](#dependencies)
  - [Internal imports](#internal-imports)
  - [External imports (stdlib only)](#external-imports-stdlib-only)
  - [Imported by](#imported-by)

<!-- mdformat-toc end -->

## Usage<a name="usage"></a>

```bash
python3 run.py docs-audit [SCOPE ...] [--json] [--no-fail]   # or: make docs-audit
uv run python -m scripts.docs_audit [SCOPE ...] [--json] [--no-fail]
```

`SCOPE` arguments are repo-relative paths (default: the whole repo). Exit codes: `0` clean (or `--no-fail`), `1`
findings, `2` usage/internal error.

The file-scoped checks (structural, link, policy) also run as the prek hook `docs-audit-readme` on changed `README.md`
files; see [`scripts/hooks/`](../hooks/README.md#docs_audit_hookpy).

## Directory classes<a name="directory-classes"></a>

Directories are discovered from `git ls-files` (so untracked artifacts never appear) and each gets a
[`DirClass`](#classifypy) that decides its README requirements.

| Class    | Which directories                                                                | README required                                                             |
| -------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `META`   | The repo root and top-level `docs`, `scripts`, `tests`                           | Yes: an index/overview that also covers non-data descendants                |
| `CODE`   | Any directory holding a `.py` file                                               | Yes, unless a `META` or `DATA` ancestor below the repo root has a README    |
| `DATA`   | Any other directory with documentable content                                    | Only at the top of a data tree (or when no ancestor below the root has one) |
| `EXEMPT` | `docs/plans/**`, and directories holding only placeholders (`.gitkeep`, `.keep`) | No; READMEs in them are also skipped by the structural/link/policy checks   |

## Module structure<a name="module-structure"></a>

```
docs_audit/
├── conventions.py   # hardcoded exclusions, meta dirs, plans-exempt, forbidden patterns + policy opt-out markers
├── discover.py      # discover(scopes) + is_excluded(rel_dir) -> in-scope directories (from git ls-files)
├── classify.py      # DirClass + classify(dir)
├── checks.py        # finding types + find_missing/stale_candidates/structural/link/policy
├── report.py        # AuditReport + AuditReportSummaryDict + to_text()/to_json() + style/unstyle helpers
├── audit.py         # run_audit(scopes) orchestration
└── __main__.py      # argparse CLI + exit codes
```

The per-file checks (`structural_issues`, `link_issues`, `policy_issues`) are also driven by
`scripts/hooks/docs_audit_hook.py`. The `style` and `unstyle` helpers are exported from `report.py` so the hook can
reuse them without duplicating ANSI handling.

## API Quick Reference<a name="api-quick-reference"></a>

### report.py<a name="reportpy"></a>

| Symbol                   | Type      | Signature                                                                       | Description                                                   |
| ------------------------ | --------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `AuditReport`            | dataclass | —                                                                               | Aggregated deterministic docs-audit findings                  |
| `AuditReportSummaryDict` | TypedDict | —                                                                               | Per-category finding counts; schema for `AuditReport.summary` |
| `style`                  | function  | `(text: Any, *, fg: str \| None, bold: bool \| None, dim: bool \| None) -> str` | Apply ANSI codes; no-op when `NO_COLOR` is set                |
| `unstyle`                | function  | `(text: str) -> str`                                                            | Strip ANSI sequences from a string                            |

### discover.py<a name="discoverpy"></a>

| Symbol        | Type     | Signature                                                    | Description                                                      |
| ------------- | -------- | ------------------------------------------------------------ | ---------------------------------------------------------------- |
| `discover`    | function | `(scopes: Sequence[Path], *, repo_root: Path) -> list[Path]` | Enumerate in-scope directories from `git ls-files`               |
| `is_excluded` | function | `(rel_dir: Path) -> bool`                                    | Return whether a directory matches an excluded segment or suffix |

### classify.py<a name="classifypy"></a>

| Symbol     | Type     | Signature                                         | Description                        |
| ---------- | -------- | ------------------------------------------------- | ---------------------------------- |
| `DirClass` | enum     | —                                                 | `CODE`, `DATA`, `META`, `EXEMPT`   |
| `classify` | function | `(rel_dir: Path, *, repo_root: Path) -> DirClass` | Classify a repo-relative directory |

### checks.py<a name="checkspy"></a>

| Symbol              | Type      | Signature                                                                                   | Description                                                                                |
| ------------------- | --------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `MissingFinding`    | dataclass | —                                                                                           | Directory required to have a README but has none                                           |
| `StaleFinding`      | dataclass | —                                                                                           | README whose commit time predates the newest source file                                   |
| `StructuralFinding` | dataclass | —                                                                                           | README with structural issues (breadcrumb, title, down-links)                              |
| `BrokenLink`        | dataclass | —                                                                                           | A single broken relative link or unresolved anchor                                         |
| `LinkFinding`       | dataclass | —                                                                                           | README with one or more broken links                                                       |
| `PolicyMatch`       | dataclass | —                                                                                           | A single forbidden-pattern match within a README                                           |
| `PolicyFinding`     | dataclass | —                                                                                           | README containing forbidden command patterns                                               |
| `find_missing`      | function  | `(classified: Sequence[tuple[Path, DirClass]], *, repo_root: Path) -> list[MissingFinding]` | Directories missing a required README (honors data-tree-top and index-coverage exemptions) |
| `stale_candidates`  | function  | `(classified: Sequence[tuple[Path, DirClass]], *, repo_root: Path) -> list[StaleFinding]`   | READMEs older than their newest sibling source file                                        |
| `structural_issues` | function  | `(readme: Path, *, children_with_readme: Sequence[Path], is_repo_root: bool) -> list[str]`  | Structural completeness check                                                              |
| `link_issues`       | function  | `(readme: Path) -> list[BrokenLink]`                                                        | Relative-link and anchor check                                                             |
| `policy_issues`     | function  | `(readme: Path) -> list[PolicyMatch]`                                                       | Forbidden command pattern scan (honors opt-out markers)                                    |

### audit.py<a name="auditpy"></a>

| Symbol      | Type     | Signature                                                     | Description                                        |
| ----------- | -------- | ------------------------------------------------------------- | -------------------------------------------------- |
| `run_audit` | function | `(scopes: Sequence[Path], *, repo_root: Path) -> AuditReport` | Orchestrate all checks and return an `AuditReport` |

### conventions.py<a name="conventionspy"></a>

| Symbol                  | Type                     | Description                                                                                     |
| ----------------------- | ------------------------ | ----------------------------------------------------------------------------------------------- |
| `EXCLUDE_SEGMENTS`      | `frozenset[str]`         | Path segments excluded at any depth (caches, VCS, tooling, and hidden stow payload directories) |
| `EXCLUDE_TOP_LEVEL`     | `frozenset[str]`         | Names excluded only at the repo root (`archive`, `build`, `dist`, `site`)                       |
| `EXCLUDE_SUFFIXES`      | `tuple[str, ...]`        | Path-segment suffixes that disqualify a directory (e.g. `.egg-info`)                            |
| `META_DIR_NAMES`        | `frozenset[str]`         | Top-level names treated as meta directories (`docs`, `scripts`, `tests`)                        |
| `PLACEHOLDER_FILENAMES` | `frozenset[str]`         | Filenames (`.gitkeep`, `.keep`) that mark an otherwise-empty dir as EXEMPT                      |
| `PLANS_EXEMPT_PARTS`    | `tuple[str, ...]`        | Leading path parts whose subtree is EXEMPT (`docs/plans`)                                       |
| `FORBIDDEN_PATTERNS`    | `tuple[re.Pattern, ...]` | Compiled patterns for the policy check (currently the banned formatter command)                 |
| `POLICY_ALLOW_INLINE`   | `str`                    | Inline opt-out marker; a line containing it is skipped by the policy check                      |
| `POLICY_ALLOW_START`    | `str`                    | Opens a block whose lines are skipped by the policy check (wraps code fences)                   |
| `POLICY_ALLOW_END`      | `str`                    | Closes a policy opt-out block opened by `POLICY_ALLOW_START`                                    |

## Core components<a name="core-components"></a>

### AuditReport<a name="auditreport"></a>

`AuditReport` is a dataclass that holds the five finding lists returned by `run_audit`. It is the sole return type of
`run_audit` and the primary object consumers interact with.

<details>
<summary><strong>Properties and methods</strong></summary>

| Member         | Signature                                       | Description                                   |
| -------------- | ----------------------------------------------- | --------------------------------------------- |
| `has_findings` | `-> bool`                                       | `True` when any finding category is non-empty |
| `summary`      | `-> AuditReportSummaryDict`                     | Per-category finding counts                   |
| `to_dict`      | `() -> dict[str, Any]`                          | JSON-encodable dict (the full envelope)       |
| `to_json`      | `(*, indent: int \| None = 2, **kwargs) -> str` | Render as the documented JSON envelope        |
| `to_text`      | `() -> str`                                     | Render as ANSI-styled human-readable text     |

</details>

### AuditReportSummaryDict<a name="auditreportsummarydict"></a>

`AuditReportSummaryDict` is a `TypedDict` that defines the schema of the `summary` key in the JSON envelope and the
return type of `AuditReport.summary`:

```python
class AuditReportSummaryDict(TypedDict):
    missing:          int
    stale_candidates: int
    structural:       int
    links:            int
    policy:           int
```

Consumers that parse the `--json` output should type-annotate the `summary` key against this TypedDict.

### style / unstyle<a name="style--unstyle"></a>

`style` and `unstyle` are ANSI helpers exported from `report.py` for reuse by the prek hook wrapper.

```python
from scripts.docs_audit.report import style
from scripts.docs_audit.report import unstyle

text = style('docs-audit', fg='cyan', bold=True)
plain = unstyle(text)  # 'docs-audit'
```

`style` is a no-op (returns the string unchanged) when the `NO_COLOR` environment variable is set.

## JSON envelope<a name="json-envelope"></a>

`--json` emits a single object. The `summary` key conforms to `AuditReportSummaryDict`:

<!-- docs-audit-allow-start -->

```json
{
  "scope": [
    "roles"
  ],
  "missing": [
    {
      "path": "roles/foo",
      "class": "code"
    }
  ],
  "stale_candidates": [
    {
      "path": "roles/foo/README.md",
      "readme_mtime": "2025-01-01T00:00:00+00:00",
      "newest_source": "2025-06-01T12:00:00+00:00",
      "newest_source_file": "roles/foo/tasks.py"
    }
  ],
  "structural": [
    {
      "path": "roles/foo/README.md",
      "issues": [
        "missing breadcrumb"
      ]
    }
  ],
  "links": [
    {
      "path": "roles/foo/README.md",
      "broken": [
        {
          "link": "../missing.md",
          "reason": "path not found"
        }
      ]
    }
  ],
  "policy": [
    {
      "path": "roles/foo/README.md",
      "matches": [
        {
          "pattern": "\\bruff format\\b",
          "line": 42,
          "text": "ruff format"
        }
      ]
    }
  ],
  "summary": {
    "missing": 1,
    "stale_candidates": 1,
    "structural": 1,
    "links": 1,
    "policy": 1
  }
}
```

<!-- docs-audit-allow-end -->

## Dependencies<a name="dependencies"></a>

### Internal imports<a name="internal-imports"></a>

| Module                           | Symbols used                                                                                                                                                                                                        |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts.docs_audit.checks`      | all finding dataclasses + all check functions                                                                                                                                                                       |
| `scripts.docs_audit.classify`    | `DirClass`, `classify`                                                                                                                                                                                              |
| `scripts.docs_audit.conventions` | `EXCLUDE_SEGMENTS`, `EXCLUDE_TOP_LEVEL`, `EXCLUDE_SUFFIXES`, `FORBIDDEN_PATTERNS`, `PLACEHOLDER_FILENAMES`, `POLICY_ALLOW_INLINE`, `POLICY_ALLOW_START`, `POLICY_ALLOW_END`, `META_DIR_NAMES`, `PLANS_EXEMPT_PARTS` |
| `scripts.docs_audit.discover`    | `discover`                                                                                                                                                                                                          |
| `scripts.docs_audit.report`      | `AuditReport`                                                                                                                                                                                                       |

### External imports (stdlib only)<a name="external-imports-stdlib-only"></a>

`argparse`, `dataclasses`, `enum`, `functools`, `json`, `os`, `pathlib`, `re`, `subprocess`, `sys`, `typing`

### Imported by<a name="imported-by"></a>

| Consumer                           | What                                                                                                 |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `scripts/hooks/docs_audit_hook.py` | `structural_issues`, `link_issues`, `policy_issues`, `EXCLUDE_SEGMENTS`, `EXCLUDE_SUFFIXES`, `style` |
| `run.py`                           | `DocsAuditCommand` runs `python -m scripts.docs_audit` (the `docs-audit` command)                    |
