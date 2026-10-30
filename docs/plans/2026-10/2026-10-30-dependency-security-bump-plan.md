# Dependency security bump plan (urllib3, cryptography)

Closes the 8 open Dependabot alerts (urllib3 x3 advisories, cryptography x1; each in `uv.lock` and `requirements.txt`).
Supersedes the Dependabot PRs #20 (cryptography only) and #21 (urllib3 only): both edit `requirements.txt` alone, leave
`uv.lock` stale (alerts #4/#6/#8/#10 would stay open), conflict with each other, and #20 stops at 50.0.0.

## Global Constraints

- Run every `uv` invocation through `scripts/hooks/uv-public.sh` (public PyPI only; never plain `uv`).
- `uv.lock` is the source of truth; `requirements.txt` is generated from it by the `uv-export` prek hook. Never hand-edit
  `requirements.txt`.
- Touch only `uv.lock` and `requirements.txt`. No other package may change version; any collateral version movement in
  the lock diff is a failure, not a tolerated side effect.
- The lock must reference public PyPI only (no internal index URLs, hosts or mirror names anywhere in the diff).
- Never run `ruff format`.
- Commit message: conventional style, e.g. `fix(deps): bump urllib3 to 2.8.0 and cryptography to 50.0.2`.

## Task 1: Upgrade the two packages in the lock and re-export requirements.txt

1. Record the baseline: `scripts/hooks/uv-public.sh lock --dry-run --upgrade-package urllib3 --upgrade-package
   cryptography` and confirm the only changes are urllib3 2.7.0 -> 2.8.0 and cryptography 49.0.0 -> 50.0.2. If the dry
   run moves any other package, STOP and report (do not proceed).
2. Apply: `scripts/hooks/uv-public.sh lock --upgrade-package urllib3 --upgrade-package cryptography`.
3. Regenerate the export exactly as the hook does: `scripts/hooks/uv-public.sh export --format=requirements.txt
   --output-file=requirements.txt --frozen --no-hashes --no-header`.
4. Verify: `git diff --stat` shows only `uv.lock` and `requirements.txt`; `git diff -U0 requirements.txt` shows only the
   two version lines; in `uv.lock` the diff is limited to the urllib3 and cryptography package entries (versions, sdist
   and wheel URLs/hashes, and any dependency metadata those packages themselves changed). `grep -c` the diff for any
   non-`pypi.org` / `files.pythonhosted.org` registry or URL: expect zero.
5. Run `scripts/hooks/uv-public.sh lock --check` (lock consistent) and the full suite
   `scripts/hooks/uv-public.sh run pytest -q`; both must pass. The tracked tree must be unchanged by the test run.
6. Run `prek run --all-files` (or `prek run` on the staged files plus the leak guard,
   `scripts/hooks/check-leaks.py` as wired in `.pre-commit-config.yaml`); everything green, no auto-fix leftovers.
7. Commit (single commit).
