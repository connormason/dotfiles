#!/usr/bin/env bash
# Run uv against public PyPI only.
#
# Work machines inject an internal package index two ways: UV_* index environment variables, and an extra-index-url
# in the user-level ~/.config/uv/uv.toml (which uv consults before any project default index). Both must be
# neutralized; either alone still produces a uv.lock that references the internal index. UV_NO_CONFIG skips only
# user/system uv.toml files -- this project's [tool.uv] table in pyproject.toml is still honored.
set -euo pipefail

unset UV_INDEX_URL UV_DEFAULT_INDEX UV_EXTRA_INDEX_URL UV_INDEX
export UV_NO_CONFIG=1

exec uv "$@"
