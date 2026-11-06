"""
Tests for the update_gitignore.py script
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.conftest import unstyle

if TYPE_CHECKING:
    from types import ModuleType

    from typing_extensions import Self


SCRIPT_PATH = Path(__file__).parents[4] / 'scripts' / 'codebase' / 'update_gitignore.py'

TEMPLATES = 'macos,python,pycharm+all'
API_URL   = 'https://www.toptal.com/developers/gitignore/api/'
GENERATED = (
    f'# Created by {API_URL}{TEMPLATES}\n'
    f'# Edit at https://www.toptal.com/developers/gitignore?templates={TEMPLATES}\n'
    '\n'
    '### macOS ###\n'
    '.DS_Store\n'
    '\n'
    f'# End of {API_URL}{TEMPLATES}\n'
)
CUSTOM = '\n# Custom\n.claude/worktrees/\n\n*.local\n'


class FakeResponse:
    """
    Minimal stand-in for the context manager returned by ``urlopen``
    """
    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode('utf-8')


@pytest.fixture
def script() -> ModuleType:
    """
    Load the script as a module (it lives outside any package)
    """
    spec = importlib.util.spec_from_file_location('update_gitignore', SCRIPT_PATH)
    assert spec        is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestExtractTemplates:
    """
    Tests for extract_templates
    """
    @pytest.mark.parametrize(
        ('content', 'expected'),
        [
            (GENERATED,                                    ['macos', 'python', 'pycharm+all']),
            (f'# Created by {API_URL}rust-analyzer,a.b\n', ['rust-analyzer', 'a.b']),
            (f'x\n# Created by {API_URL}git\ny\n',         ['git']),
        ],
    )
    def test_parses_template_list(self, script: ModuleType, content: str, expected: list[str]) -> None:
        """
        Test that the template list is read from the embedded gitignore.io URL
        """
        assert script.extract_templates(content) == expected

    def test_missing_url_raises(self, script: ModuleType) -> None:
        """
        Test that a file without the gitignore.io URL is rejected
        """
        with pytest.raises(ValueError, match=r'gitignore\.io URL'):
            script.extract_templates('*.pyc\n')


class TestExtractCustomPatterns:
    """
    Tests for extract_custom_patterns
    """
    def test_returns_lines_after_end_marker(self, script: ModuleType) -> None:
        """
        Test that custom lines are kept verbatim, minus leading and trailing blank lines
        """
        assert script.extract_custom_patterns(GENERATED + CUSTOM) == ['# Custom', '.claude/worktrees/', '', '*.local']

    @pytest.mark.parametrize('tail', ['', '\n', '\n\n   \n'])
    def test_no_custom_lines(self, script: ModuleType, tail: str) -> None:
        """
        Test that blank-only content after the marker yields no custom patterns
        """
        assert script.extract_custom_patterns(GENERATED + tail) == []

    def test_missing_end_marker_raises(self, script: ModuleType) -> None:
        """
        Test that a missing end marker is an error rather than silently dropping custom patterns
        """
        with pytest.raises(ValueError, match='end marker'):
            script.extract_custom_patterns(f'# Created by {API_URL}git\n.DS_Store\n')


class TestGenerateUpdatedGitignore:
    """
    Tests for generate_updated_gitignore
    """
    def test_without_custom_patterns(self, script: ModuleType) -> None:
        """
        Test that fresh content is returned with exactly one trailing newline
        """
        assert script.generate_updated_gitignore(GENERATED + '\n\n', []) == GENERATED

    def test_round_trip_preserves_custom_patterns(self, script: ModuleType) -> None:
        """
        Test that extracting then regenerating reproduces the original file
        """
        original = GENERATED + CUSTOM.replace('\n\n*.local', '\n*.local')
        custom   = script.extract_custom_patterns(original)
        assert script.generate_updated_gitignore(GENERATED, custom) == original


class TestFetchGitignoreContent:
    """
    Tests for fetch_gitignore_content
    """
    def test_urllib_success(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that urllib content is returned and the request URL joins the templates
        """
        seen: list[str] = []

        def fake_urlopen(url: str, timeout: float) -> FakeResponse:
            seen.append(url)
            return FakeResponse(GENERATED)

        monkeypatch.setattr(script, 'urlopen', fake_urlopen)
        assert script.fetch_gitignore_content(['macos', 'python']) == GENERATED
        assert seen == [f'{API_URL}macos,python']

    def test_falls_back_to_curl(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a urllib failure falls back to curl against the same URL
        """
        def failing_urlopen(url: str, timeout: float) -> FakeResponse:
            raise OSError('certificate verify failed')

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout=GENERATED, stderr='')

        monkeypatch.setattr(script,            'urlopen', failing_urlopen)
        monkeypatch.setattr(script.subprocess, 'run',     fake_run)

        assert script.fetch_gitignore_content(['git']) == GENERATED
        assert calls[0][0]  == 'curl'
        assert calls[0][-1] == f'{API_URL}git'

    def test_all_methods_fail(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a curl failure after a urllib failure raises RuntimeError with the exit code
        """
        def failing_urlopen(url: str, timeout: float) -> FakeResponse:
            raise OSError('offline')

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 22, stdout='', stderr='HTTP 404')

        monkeypatch.setattr(script,            'urlopen', failing_urlopen)
        monkeypatch.setattr(script.subprocess, 'run',     fake_run)

        with pytest.raises(RuntimeError, match='curl exit 22'):
            script.fetch_gitignore_content(['git'])

    def test_curl_missing(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that an absent curl binary is reported as a fetch failure
        """
        def failing_urlopen(url: str, timeout: float) -> FakeResponse:
            raise OSError('offline')

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError('curl')

        monkeypatch.setattr(script,            'urlopen', failing_urlopen)
        monkeypatch.setattr(script.subprocess, 'run',     fake_run)

        with pytest.raises(RuntimeError, match='urllib and curl both failed'):
            script.fetch_gitignore_content(['git'])

    def test_content_without_end_marker_rejected(self, script: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that truncated or error-page content is refused instead of overwriting the file
        """
        monkeypatch.setattr(script, 'urlopen', lambda url, timeout: FakeResponse('<html>rate limited</html>'))
        with pytest.raises(RuntimeError, match='end marker'):
            script.fetch_gitignore_content(['git'])


class TestMain:
    """
    Tests for main
    """
    @pytest.fixture
    def gitignore(self, tmp_path: Path) -> Path:
        """
        A .gitignore with a stale generated block and custom patterns
        """
        path = tmp_path / '.gitignore'
        path.write_text(GENERATED.replace('.DS_Store', '.OLD') + CUSTOM, encoding='utf-8')
        return path

    def test_updates_file_and_keeps_custom_patterns(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a changed upstream block is written and custom patterns survive
        """
        monkeypatch.setattr(script, 'fetch_gitignore_content', lambda templates: GENERATED)
        assert script.main(['--gitignore-path', str(gitignore)]) == 0

        text = gitignore.read_text(encoding='utf-8')
        assert '.DS_Store' in text
        assert '.OLD'  not in text
        assert text.endswith('# Custom\n.claude/worktrees/\n\n*.local\n')
        assert 'Updated' in unstyle(capsys.readouterr().out)

    def test_already_up_to_date(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that identical content leaves the file untouched and says so
        """
        current = gitignore.read_text(encoding='utf-8')
        monkeypatch.setattr(script, 'fetch_gitignore_content', lambda templates: current.split('\n# Custom')[0] + '\n')

        assert script.main(['--gitignore-path', str(gitignore)]) == 0
        assert gitignore.read_text(encoding='utf-8') == current
        assert 'already up to date' in unstyle(capsys.readouterr().out)

    def test_dry_run_does_not_write(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --dry-run reports the change without modifying the file
        """
        before = gitignore.read_text(encoding='utf-8')
        monkeypatch.setattr(script, 'fetch_gitignore_content', lambda templates: GENERATED)

        assert script.main(['--gitignore-path', str(gitignore), '--dry-run']) == 0
        assert gitignore.read_text(encoding='utf-8') == before
        assert 'Dry run' in unstyle(capsys.readouterr().out)

    def test_force_rewrites_identical_content(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that --force reports an update even when nothing changed
        """
        current = gitignore.read_text(encoding='utf-8')
        monkeypatch.setattr(script, 'fetch_gitignore_content', lambda templates: current.split('\n# Custom')[0] + '\n')

        assert script.main(['--gitignore-path', str(gitignore), '--force']) == 0
        assert 'Updated' in unstyle(capsys.readouterr().out)

    def test_missing_file(self, script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a nonexistent .gitignore exits 1 with a message on stderr
        """
        assert script.main(['--gitignore-path', str(tmp_path / 'nope')]) == 1
        assert 'not found' in unstyle(capsys.readouterr().err)

    def test_file_without_gitignore_url(
        self,
        script: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        Test that a hand-written .gitignore is rejected rather than overwritten
        """
        path = tmp_path / '.gitignore'
        path.write_text('*.pyc\n', encoding='utf-8')

        assert script.main(['--gitignore-path', str(path)]) == 1
        assert path.read_text(encoding='utf-8') == '*.pyc\n'
        assert 'gitignore.io URL' in unstyle(capsys.readouterr().err)

    def test_fetch_failure_leaves_file_untouched(
        self,
        script: ModuleType,
        gitignore: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Test that a fetch error exits 1 and does not modify the file
        """
        def failing_fetch(templates: list[str]) -> str:
            raise RuntimeError('offline')

        before = gitignore.read_text(encoding='utf-8')
        monkeypatch.setattr(script, 'fetch_gitignore_content', failing_fetch)

        assert script.main(['--gitignore-path', str(gitignore)]) == 1
        assert gitignore.read_text(encoding='utf-8') == before
