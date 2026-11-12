"""
Behavioral tests for roles/debian/files/nas-notify, run against stub curl and logger executables
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT    = REPO_ROOT / 'roles' / 'debian' / 'files' / 'nas-notify'

STUB = '#!/usr/bin/env bash\nprintf "%s\\n" "$@" >> "$STUB_LOG_DIR/{name}.log"\nexit "${{STUB_{upper}_RC:-0}}"\n'


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """
    Create a directory holding stub curl and logger executables and their call logs
    """
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    for name in ('curl', 'logger'):
        stub = bindir / name
        stub.write_text(STUB.format(name=name, upper=name.upper()), encoding='utf-8')
        stub.chmod(0o755)
    return tmp_path


def _run(
    sandbox: Path,
    *args: str,
    token: str | None = 'tok',
    stdin: str = '',
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    Run nas-notify with the stubs first on PATH

    :param sandbox: directory from the ``sandbox`` fixture
    :param args: command-line arguments
    :param token: NTFY_TOKEN to write to the settings file, or None for no file at all
    :param stdin: standard input
    :param env: extra environment variables
    :return: the completed process
    """
    settings = sandbox / 'nas-notify.env'
    if token is not None:
        lines = ["NTFY_URL='http://ntfy.test'", "NTFY_TOPIC='alerts'", f"NTFY_TOKEN='{token}'"]
        settings.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return subprocess.run(
        [str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env={
            'PATH': f'{sandbox / "bin"}:{os.environ["PATH"]}',
            'NAS_NOTIFY_ENV': str(settings),
            'STUB_LOG_DIR': str(sandbox),
            **(env or {}),
        },
    )


def _calls(sandbox: Path, name: str) -> list[str]:
    """
    Return the argument lines a stub recorded (empty when it was never called)
    """
    log = sandbox / f'{name}.log'
    return log.read_text(encoding='utf-8').splitlines() if log.exists() else []


class TestNasNotify:
    """
    Tests for the nas-notify alert publisher
    """
    def test_publishes_to_ntfy_with_token_title_and_priority(self, sandbox: Path) -> None:
        """
        Test that a direct call posts the message to the configured URL and topic with the auth header
        """
        result = _run(sandbox, '-p', 'urgent', '-t', 'Disk', 'sda', 'is', 'failing')

        assert result.returncode == 0, result.stderr
        curl = _calls(sandbox, 'curl')
        assert 'Authorization: Bearer tok' in curl
        assert 'Title: Disk' in curl
        assert 'Priority: urgent' in curl
        assert 'sda is failing' in curl
        assert curl[-1] == 'http://ntfy.test/alerts'

    def test_logs_to_the_journal_even_when_publishing(self, sandbox: Path) -> None:
        """
        Test that every alert reaches logger, so an unreachable ntfy never loses the message
        """
        _run(sandbox, '-t', 'Disk', 'sda failing')

        assert any('Disk: sda failing' in line for line in _calls(sandbox, 'logger'))

    @pytest.mark.parametrize('token', ['', None])
    def test_without_a_token_it_logs_only_and_succeeds(self, sandbox: Path, token: str | None) -> None:
        """
        Test that a missing token or settings file skips ntfy, still logs, and exits 0 (so ZED and smartd stay quiet)
        """
        result = _run(sandbox, 'something broke', token=token)

        assert result.returncode == 0
        assert _calls(sandbox, 'curl') == []
        assert any('something broke' in line for line in _calls(sandbox, 'logger'))
        assert 'alert logged only' in result.stderr

    def test_publish_failure_is_reported(self, sandbox: Path) -> None:
        """
        Test that a curl failure becomes a non-zero exit, after the alert was logged
        """
        result = _run(sandbox, 'x', env={'STUB_CURL_RC': '22'})

        assert result.returncode != 0
        assert any(line.endswith(': x') for line in _calls(sandbox, 'logger'))

    def test_smartd_environment_builds_the_alert_and_ignores_positional_arguments(self, sandbox: Path) -> None:
        """
        Test that SMARTD_MESSAGE wins over the mail-style arguments smartd also passes
        """
        result = _run(
            sandbox,
            'root', 'SMART error', 'ignored',
            env={
                'SMARTD_MESSAGE':  'Reallocated sectors rose',
                'SMARTD_FAILTYPE': 'Health',
                'SMARTD_DEVICE':   '/dev/sda',
            },
        )

        assert result.returncode == 0, result.stderr
        curl = _calls(sandbox, 'curl')
        assert 'Title: SMART Health on /dev/sda' in curl
        assert 'Priority: high' in curl
        assert 'Reallocated sectors rose' in curl
        assert 'root' not in curl

    def test_zed_mode_splits_the_subject_header_from_the_body(self, sandbox: Path) -> None:
        """
        Test that -z takes the first stdin line as the title and the rest as the body, at high priority
        """
        result = _run(sandbox, '-z', stdin='Subject: ZFS scrub_finish pool storage\nThe pool is healthy.\nDone.\n')

        assert result.returncode == 0, result.stderr
        curl = _calls(sandbox, 'curl')
        assert 'Title: ZFS scrub_finish pool storage' in curl
        assert 'Priority: high' in curl
        assert any(line.startswith('The pool is healthy.') for line in curl)
        assert not any(line.startswith('Subject:') for line in curl)

    def test_oversized_message_is_truncated_below_the_ntfy_limit(self, sandbox: Path) -> None:
        """
        Test that a body over 4096 bytes is cut so ntfy does not reject it
        """
        _run(sandbox, 'a' * 6000)

        body = next(line for line in _calls(sandbox, 'curl') if line.startswith('aaaa'))
        assert len(body) == 3900

    def test_newlines_in_the_title_cannot_inject_headers(self, sandbox: Path) -> None:
        """
        Test that a multi-line title is flattened into a single header value
        """
        _run(sandbox, '-t', 'one\nX-Evil: 1', 'msg')

        assert 'Title: one X-Evil: 1' in _calls(sandbox, 'curl')

    def test_no_message_is_a_usage_error(self, sandbox: Path) -> None:
        """
        Test that calling with nothing to send exits 2 and publishes nothing
        """
        result = _run(sandbox)

        assert result.returncode == 2
        assert _calls(sandbox, 'curl') == []
