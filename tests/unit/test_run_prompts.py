"""
Unit tests for run.py interactive prompts
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run


class TestConfirm:
    """
    Tests for the confirm prompt
    """
    @pytest.mark.parametrize(
        ('answer', 'default', 'expected'),
        [
            ('y',     False, True),
            ('YES',   False, True),
            ('n',     True,  False),
            ('',      True,  True),
            ('',      False, False),
            ('maybe', True,  False),
        ],
    )
    def test_interprets_answer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        answer: str,
        default: bool,
        expected: bool,
    ) -> None:
        """
        Test that yes/no answers are honored and an empty answer falls back to the default
        """
        monkeypatch.setattr('builtins.input', lambda prompt: answer)
        assert run.confirm('Proceed?', default=default) is expected

    def test_prompt_shows_default_and_indent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that the prompt marks the default answer and honors the indent
        """
        prompts: list[str] = []

        def fake_input(prompt: str) -> str:
            prompts.append(prompt)
            return 'y'

        monkeypatch.setattr('builtins.input', fake_input)

        run.confirm('Proceed?', indent=3)
        run.confirm('Proceed?', default=False)
        assert prompts == ['   Proceed? [Y/n]: ', 'Proceed? [y/N]: ']

    def test_eof_declines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a closed stdin counts as "no" rather than raising
        """
        def raise_eof(prompt: str) -> str:
            raise EOFError

        monkeypatch.setattr('builtins.input', raise_eof)
        assert run.confirm('Proceed?') is False

    def test_ctrl_c_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that Ctrl-C reaches main() (cancelling the run) instead of being read as "no"
        """
        def raise_interrupt(prompt: str) -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr('builtins.input', raise_interrupt)
        with pytest.raises(KeyboardInterrupt):
            run.confirm('Proceed?')
