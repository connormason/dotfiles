"""
Unit tests for run.py shell_command real-time (pty) output path
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import run

# Generous upper bound: the child sleeps 30s, so anything near this means the timeout never fired
PROMPT_SECONDS = 5


class TestShellCommandStreaming:
    """
    Tests for shell_command when streaming output (indent set, no capture)
    """
    def test_timeout_raises_promptly_when_check_true(self) -> None:
        """
        Test that a silent hung command is killed at the timeout and raises TimeoutExpired
        """
        start = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            run.shell_command(['sleep', '30'], indent=0, timeout=0.3, check=True)
        assert time.monotonic() - start < PROMPT_SECONDS

    def test_timeout_returns_sentinel_when_check_false(self) -> None:
        """
        Test that a timed-out command returns returncode -1 promptly when check is disabled
        """
        start = time.monotonic()
        result = run.shell_command(['sleep', '30'], indent=0, timeout=0.3, check=False)
        assert result.returncode == -1
        assert time.monotonic() - start < PROMPT_SECONDS

    def test_timeout_keeps_output_emitted_before_the_kill(self) -> None:
        """
        Test that output produced before the timeout is preserved on the returned result
        """
        result = run.shell_command(['sh', '-c', 'echo before; sleep 30'], indent=0, timeout=1, check=False)
        assert result.returncode == -1
        assert 'before' in result.stdout

    def test_normal_completion_with_timeout_set(self) -> None:
        """
        Test that a command finishing inside the timeout returns its output and exit code
        """
        result = run.shell_command(['sh', '-c', 'echo hello; exit 3'], indent=0, timeout=10, check=False)
        assert result.returncode == 3
        assert 'hello' in result.stdout

    def test_nonzero_exit_raises_when_check_true(self) -> None:
        """
        Test that a nonzero exit raises ShellCommandError rather than a timeout error
        """
        with pytest.raises(run.ShellCommandError):
            run.shell_command(['sh', '-c', 'exit 2'], indent=0, timeout=10, check=True)

    def test_read_loop_exception_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an exception raised inside the read loop reaches the caller unchanged
        """
        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError('poll failed')

        monkeypatch.setattr(run.select, 'select', boom)
        with pytest.raises(RuntimeError, match='poll failed'):
            run.shell_command(['sleep', '30'], indent=0, timeout=0.3, check=False)
