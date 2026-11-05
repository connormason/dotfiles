"""
Unit tests for run.py ANSI styling
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run

ROOT = Path(__file__).resolve().parents[2]


class TestNoColor:
    """
    Tests for NO_COLOR handling in style()
    """
    def test_style_emits_ansi_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that styling is applied when NO_COLOR is off
        """
        monkeypatch.setattr(run, 'NO_COLOR', False)
        assert run.style('hi', fg='red') == '\033[31mhi\033[0m'

    def test_style_is_plain_when_no_color_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that every style attribute is dropped when NO_COLOR is on
        """
        monkeypatch.setattr(run, 'NO_COLOR', True)
        assert run.style('hi', fg='red', bg='blue', bold=True, dim=True, italic=True) == 'hi'

    def test_plain_style_still_stringifies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that non-str values are converted to str on the unstyled path
        """
        monkeypatch.setattr(run, 'NO_COLOR', True)
        assert run.style(42, fg='red') == '42'

    @pytest.mark.parametrize(
        ('value', 'styled'),
        [
            (None,    True),
            ('',      True),
            ('1',     False),
            ('0',     False),
            ('false', False),
        ],
    )
    def test_env_var_follows_no_color_convention(self, value: str | None, styled: bool) -> None:
        """
        Test that any non-empty NO_COLOR value (even "0") disables styling and an empty or unset one does not
        """
        env = {key: val for key, val in os.environ.items() if key != 'NO_COLOR'}
        if value is not None:
            env['NO_COLOR'] = value

        code = f'import sys; sys.path.insert(0, {str(ROOT)!r}); import run; print(run.style("x", fg="red"))'
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, check=True)
        assert (result.stdout.strip() != 'x') is styled
