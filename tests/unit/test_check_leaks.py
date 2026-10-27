"""
Unit tests for scripts/hooks/check-leaks.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'hooks' / 'check-leaks.py'

# Built at runtime so this file never contains the literal identifiers it exercises
CORP_DOMAIN = 'apple' + '.com'
TRACKER_URL = 'rdar' + ':' + '//' + '123456'


def _load_module() -> ModuleType:
    """
    Import the hyphenated hook script as module ``check_leaks``
    """
    spec = importlib.util.spec_from_file_location('check_leaks', SCRIPT_PATH)
    assert spec        is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules['check_leaks'] = module
    spec.loader.exec_module(module)
    return module


check_leaks = _load_module()


@pytest.fixture(autouse=True)
def isolate_private_patterns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Keep a developer's real private pattern file out of every test
    """
    monkeypatch.delenv('DOTFILES_LEAK_PATTERNS', raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg-config'))


@pytest.fixture
def baseline() -> list:
    """
    Compiled baseline patterns only
    """
    return check_leaks.load_patterns(None, required=False)


class TestBaselinePatterns:
    """
    Tests for the built-in public baseline
    """
    @pytest.mark.parametrize(
        'text',
        [
            f'url = "https://pkgs.{CORP_DOMAIN}/simple"',
            f'Author: Jane Doe <jane@{CORP_DOMAIN}>',
            f'host git.internal.{CORP_DOMAIN}',
            f'www.internal.{CORP_DOMAIN}',
            f'developer.internal.{CORP_DOMAIN}',
            f'apps.x.{CORP_DOMAIN}',
            f'support.y.{CORP_DOMAIN}',
            f'bare {CORP_DOMAIN.upper()} mention',
            f'see {TRACKER_URL}',
            'see ' + 'Radar' + ':' + '//' + '42',
        ],
    )
    def test_internal_identifiers_match(self, baseline: list, text: str) -> None:
        """
        Test that corporate domains, emails, subdomains, and tracker URLs are flagged
        """
        assert check_leaks.scan_text(text, baseline)

    @pytest.mark.parametrize(
        'text',
        [
            'defaults write com.apple.dock autohide -bool true',
            f'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.{CORP_DOMAIN}/DTDs/PropertyList-1.0.dtd">',
            f'App ID from https://apps.{CORP_DOMAIN}/app/id937984704',
            f'https://developer.{CORP_DOMAIN}/documentation',
            f'https://support.{CORP_DOMAIN}/en-us/102345',
            'image: lscr.io/linuxserver/radarr:latest',
            'Radarr manages movies',
            'apple' + '.community',
        ],
    )
    def test_public_text_does_not_match(self, baseline: list, text: str) -> None:
        """
        Test that public vendor hosts, macOS preference domains, and Radarr are not flagged
        """
        assert check_leaks.scan_text(text, baseline) == []

    @pytest.mark.parametrize('path', [SCRIPT_PATH, Path(__file__)])
    def test_own_source_is_clean(self, baseline: list, path: Path) -> None:
        """
        Test that the hook script and this test file never match their own patterns
        """
        assert check_leaks.scan_file(path, baseline) == []


class TestPrivatePatterns:
    """
    Tests for loading the optional private pattern file
    """
    def test_absent_default_file_uses_baseline_only(self) -> None:
        """
        Test that a missing default pattern file silently falls back to the baseline
        """
        patterns = check_leaks.load_patterns(check_leaks.default_patterns_file(), required=False)
        assert len(patterns) == len(check_leaks.BASELINE_PATTERNS)

    def test_default_file_location_honors_xdg(self, tmp_path: Path) -> None:
        """
        Test that the default pattern file lives under XDG_CONFIG_HOME
        """
        assert check_leaks.default_patterns_file() == tmp_path / 'xdg-config' / 'dotfiles' / 'leak-patterns.txt'

    def test_present_file_adds_patterns(self, tmp_path: Path) -> None:
        """
        Test that private patterns are applied and comments/blank lines are ignored
        """
        patterns_file = tmp_path / 'leak-patterns.txt'
        patterns_file.write_text('# internal tools\n\nsecret-tool\n', encoding='utf-8')

        patterns = check_leaks.load_patterns(patterns_file, required=True)
        assert len(patterns) == len(check_leaks.BASELINE_PATTERNS) + 1
        assert check_leaks.scan_text('runs Secret-Tool nightly', patterns) == [(1, 'Secret-Tool')]

    def test_required_missing_file_raises(self, tmp_path: Path) -> None:
        """
        Test that an explicitly requested but missing pattern file fails closed
        """
        with pytest.raises(check_leaks.LeakGuardError):
            check_leaks.load_patterns(tmp_path / 'missing.txt', required=True)

    def test_invalid_regex_raises(self, tmp_path: Path) -> None:
        """
        Test that an invalid private regex fails closed
        """
        patterns_file = tmp_path / 'leak-patterns.txt'
        patterns_file.write_text('unclosed(group\n', encoding='utf-8')
        with pytest.raises(check_leaks.LeakGuardError):
            check_leaks.load_patterns(patterns_file, required=True)

    def test_empty_matching_pattern_raises(self, tmp_path: Path) -> None:
        """
        Test that a private regex able to match the empty string fails closed
        """
        patterns_file = tmp_path / 'leak-patterns.txt'
        patterns_file.write_text('foo|\n', encoding='utf-8')
        with pytest.raises(check_leaks.LeakGuardError):
            check_leaks.load_patterns(patterns_file, required=True)

    def test_dangling_symlink_default_file_exits_2(self, tmp_path: Path) -> None:
        """
        Test that a dangling symlink at the default path fails closed instead of using the baseline
        """
        default = check_leaks.default_patterns_file()
        default.parent.mkdir(parents=True)
        default.symlink_to(tmp_path / 'nowhere.txt')
        assert check_leaks.main([]) == 2

    def test_directory_default_file_exits_2(self) -> None:
        """
        Test that a directory at the default path fails closed instead of using the baseline
        """
        check_leaks.default_patterns_file().mkdir(parents=True)
        assert check_leaks.main([]) == 2

    def test_non_utf8_file_raises(self, tmp_path: Path) -> None:
        """
        Test that an undecodable pattern file fails closed rather than escaping as a traceback
        """
        patterns_file = tmp_path / 'leak-patterns.txt'
        patterns_file.write_bytes(b'\xff\xfe\x00bad\n')
        with pytest.raises(check_leaks.LeakGuardError):
            check_leaks.load_patterns(patterns_file, required=True)

    def test_env_var_invalid_file_exits_2(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that main() returns a configuration error for a bad file named by the env var
        """
        monkeypatch.setenv('DOTFILES_LEAK_PATTERNS', str(tmp_path / 'missing.txt'))
        assert check_leaks.main([]) == 2


class TestAllowMarker:
    """
    Tests for the inline allow escape hatch
    """
    def test_marker_suppresses_only_its_line(self, baseline: list) -> None:
        """
        Test that the allow marker skips its own line but not the next one
        """
        text = f'{CORP_DOMAIN}  # {check_leaks.ALLOW_MARKER}\n{CORP_DOMAIN}\n'
        assert check_leaks.scan_text(text, baseline) == [(2, CORP_DOMAIN)]


class TestScanFile:
    """
    Tests for scan_file
    """
    def test_path_is_scanned(self, tmp_path: Path) -> None:
        """
        Test that a matching file path is reported with line 0
        """
        patterns_file = tmp_path / 'leak-patterns.txt'
        patterns_file.write_text('secret-tool\n', encoding='utf-8')

        patterns = check_leaks.load_patterns(patterns_file, required=True)

        target = tmp_path / 'secret-tool.txt'
        target.write_text('clean\n', encoding='utf-8')

        findings = check_leaks.scan_file(target, patterns)
        assert [(f.line, f.match) for f in findings] == [(0, 'secret-tool')]

    def test_content_line_numbers(self, baseline: list, tmp_path: Path) -> None:
        """
        Test that content findings carry 1-based line numbers
        """
        target = tmp_path / 'notes.md'
        target.write_text(f'clean\nmail jane@{CORP_DOMAIN}\n', encoding='utf-8')

        findings = check_leaks.scan_file(target, baseline)
        assert [(f.line, f.match) for f in findings] == [(2, CORP_DOMAIN)]

    def test_binary_file_is_skipped(self, baseline: list, tmp_path: Path) -> None:
        """
        Test that files with a NUL byte in the sniff window are not content-scanned
        """
        target = tmp_path / 'blob.bin'
        target.write_bytes(b'\0' + CORP_DOMAIN.encode())
        assert check_leaks.scan_file(target, baseline) == []


class TestIdentity:
    """
    Tests for git identity checks
    """
    @pytest.fixture
    def identity(self, monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
        """
        Pin a personal author and committer identity for git var
        """
        for role in ('AUTHOR', 'COMMITTER'):
            monkeypatch.setenv(f'GIT_{role}_NAME',  'Jane Doe')
            monkeypatch.setenv(f'GIT_{role}_EMAIL', 'jane@example.org')
        return monkeypatch

    def test_personal_identity_passes(self, identity: pytest.MonkeyPatch) -> None:
        """
        Test that a personal author/committer identity is accepted
        """
        assert check_leaks.main(['--identity']) == 0

    def test_corporate_author_email_fails(self, identity: pytest.MonkeyPatch) -> None:
        """
        Test that a corporate author email is rejected before the commit exists
        """
        identity.setenv('GIT_AUTHOR_EMAIL', f'jane@{CORP_DOMAIN}')
        assert check_leaks.main(['--identity']) == 1

    def test_identities_from_file(self, tmp_path: Path) -> None:
        """
        Test that identities read from a file are checked line by line
        """
        identities = tmp_path / 'identities.txt'
        identities.write_text(f'Jane Doe <jane@example.org>\nJane Doe <jane@{CORP_DOMAIN}>\n', encoding='utf-8')
        assert check_leaks.main(['--identities-from', str(identities)]) == 1

    def test_missing_identities_file_exits_2(self, tmp_path: Path) -> None:
        """
        Test that an unreadable identities file is a configuration error, not a traceback
        """
        assert check_leaks.main(['--identities-from', str(tmp_path / 'missing.txt')]) == 2


class TestOutput:
    """
    Tests for reporting and masking
    """
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('abcdef', 'a****f'),
            ('ab',     '**'),
            ('a',      '*'),
        ],
    )
    def test_mask(self, text: str, expected: str) -> None:
        """
        Test that masking keeps only the first and last characters
        """
        assert check_leaks.mask(text) == expected

    def test_report_never_prints_match(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that output masks matched text and caps findings per file
        """
        target = tmp_path / 'many.txt'
        target.write_text(''.join(f'jane{i}@{CORP_DOMAIN}\n' for i in range(7)), encoding='utf-8')
        assert check_leaks.main([str(target)]) == 1

        out = capsys.readouterr().out
        assert CORP_DOMAIN not in out
        assert 'and 2 more'    in out

    def test_report_masks_matches_in_path(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a leaked identifier in a file name is masked in the report header
        """
        target = tmp_path / f'jane@{CORP_DOMAIN}.txt'
        target.write_text('clean\n', encoding='utf-8')

        assert check_leaks.main([str(target)]) == 1
        assert CORP_DOMAIN not in capsys.readouterr().out

    def test_unreadable_file_header_masks_matches(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that the unreadable-file header masks a leaked identifier in the path
        """
        missing = tmp_path / f'jane@{CORP_DOMAIN}.txt'
        assert check_leaks.main([str(missing)]) == 1
        assert CORP_DOMAIN not in capsys.readouterr().out

    def test_clean_file_exits_0(self, tmp_path: Path) -> None:
        """
        Test that a clean file passes
        """
        target = tmp_path / 'clean.txt'
        target.write_text('nothing to see here\n', encoding='utf-8')
        assert check_leaks.main([str(target)]) == 0
