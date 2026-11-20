"""
Unit tests for stow/ghtools/.local/bin/gh-labels
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import tomllib

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT   = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / 'stow' / 'ghtools' / '.local' / 'bin' / 'gh-labels'


def _load_module() -> ModuleType:
    """
    Import the extension-less ``gh-labels`` script as module ``gh_labels``.
    """
    loader = importlib.machinery.SourceFileLoader('gh_labels', str(SCRIPT_PATH))
    spec   = importlib.util.spec_from_loader('gh_labels', loader)
    assert spec is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules['gh_labels'] = module

    # The script lives in a stow package: keep exec_module from leaving a __pycache__ that stow would link into $HOME
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous

    return module


gh_labels = _load_module()
Label     = gh_labels.Label


@pytest.fixture(autouse=True)
def plain_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Disable ANSI styling so assertions can match plain text
    """
    monkeypatch.setattr(gh_labels, 'NO_COLOR', True, raising=False)


class TestNormalizeColor:
    """
    Tests for normalize_color
    """
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('d73a4a',  'd73a4a'),
            ('#D73A4A', 'd73a4a'),
            ('5AB1CD',  '5ab1cd'),
        ],
    )
    def test_valid_colors_are_normalised(self, raw: str, expected: str) -> None:
        """
        Test that a color loses its hash prefix and is lowercased
        """
        assert gh_labels.normalize_color(raw) == expected

    @pytest.mark.parametrize('raw', ['', 'xyz123', '12345', '#1234567', 'ggg000'])
    def test_invalid_colors_are_rejected(self, raw: str) -> None:
        """
        Test that anything other than six hex digits raises
        """
        with pytest.raises(gh_labels.LabelsError, match='invalid color'):
            gh_labels.normalize_color(raw)


class TestParseLabels:
    """
    Tests for parse_labels
    """
    def test_valid_config_is_parsed(self) -> None:
        """
        Test that names, colors, and optional descriptions become Label objects
        """
        data = {
            'label': [
                {'name': 'bug',     'color': '#D73A4A', 'description': "Something isn't working"},
                {'name': 'feature', 'color': '5ab1cd'},
            ],
        }

        assert gh_labels.parse_labels(data) == [
            Label('bug',     'd73a4a', "Something isn't working"),
            Label('feature', '5ab1cd', ''),
        ]

    def test_name_is_stripped(self) -> None:
        """
        Test that surrounding whitespace in a name is removed
        """
        assert gh_labels.parse_labels({'label': [{'name': '  bug ', 'color': 'ffffff'}]})[0].name == 'bug'

    @pytest.mark.parametrize(
        ('data', 'message'),
        [
            ({},                                                              'at least one'),
            ({'label': []},                                                   'at least one'),
            ({'label': ['bug']},                                              'expected a table'),
            ({'label': [{'name': 'a', 'color': 'ffffff', 'colour': 'x'}]},    'unknown key'),
            ({'label': [{'color': 'ffffff'}]},                                'name must be'),
            ({'label': [{'name': '  ', 'color': 'ffffff'}]},                  'name must be'),
            ({'label': [{'name': 'x' * 51, 'color': 'ffffff'}]},              'exceeds 50'),
            ({'label': [{'name': 'a'}]},                                      'color must be'),
            ({'label': [{'name': 'a', 'color': 'nothex'}]},                   'invalid color'),
            ({'label': [{'name': 'a', 'color': 'ffffff', 'description': 7}]}, 'description must be'),
            ({'label': [{'name': 'a', 'color': 'ffffff', 'description': 'x' * 101}]}, 'exceeds 100'),
            (
                {'label': [{'name': 'Bug', 'color': 'ffffff'}, {'name': 'bug', 'color': '000000'}]},
                'duplicate',
            ),
        ],
    )
    def test_invalid_configs_are_rejected(self, data: dict[str, object], message: str) -> None:
        """
        Test that each validation rule raises a LabelsError with a helpful message
        """
        with pytest.raises(gh_labels.LabelsError, match=message):
            gh_labels.parse_labels(data)

    def test_description_at_limit_is_accepted(self) -> None:
        """
        Test that a 100 character description and a 50 character name are within limits
        """
        label = gh_labels.parse_labels({'label': [{'name': 'n' * 50, 'color': 'ffffff', 'description': 'd' * 100}]})[0]

        assert (len(label.name), len(label.description)) == (50, 100)


class TestLoadLabels:
    """
    Tests for load_labels
    """
    def test_loads_a_toml_file(self, tmp_path: Path) -> None:
        """
        Test that a TOML file on disk is parsed into labels
        """
        path = tmp_path / 'labels.toml'
        path.write_text('[[label]]\nname = "bug"\ncolor = "d73a4a"\n', encoding='utf-8')

        assert gh_labels.load_labels(path) == [Label('bug', 'd73a4a', '')]

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """
        Test that a missing config file raises a LabelsError naming the path
        """
        with pytest.raises(gh_labels.LabelsError, match='config not found'):
            gh_labels.load_labels(tmp_path / 'absent.toml')

    def test_malformed_toml_raises(self, tmp_path: Path) -> None:
        """
        Test that TOML syntax errors surface as a LabelsError
        """
        path = tmp_path / 'labels.toml'
        path.write_text('[[label]\nname = ', encoding='utf-8')

        with pytest.raises(gh_labels.LabelsError, match=r'labels\.toml'):
            gh_labels.load_labels(path)


class TestRenderToml:
    """
    Tests for render_toml
    """
    def test_round_trips_through_the_parser(self) -> None:
        """
        Test that rendered TOML parses back to the same labels, including quotes and non-ASCII text
        """
        labels = [
            Label('bug',        'd73a4a', ''),
            Label('say "hi"',   'ffffff', 'tab\tand ünïcode ✅'),
            Label('back\\slash', '000000', 'x'),
        ]

        assert gh_labels.parse_labels(tomllib.loads(gh_labels.render_toml(labels))) == labels

    def test_empty_description_is_omitted(self) -> None:
        """
        Test that labels without a description render no description key
        """
        assert 'description' not in gh_labels.render_toml([Label('bug', 'd73a4a')])


class TestDefaultConfigPath:
    """
    Tests for default_config_path
    """
    def test_honours_xdg_config_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that XDG_CONFIG_HOME relocates the default config
        """
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

        assert gh_labels.default_config_path() == tmp_path / 'gh-labels' / 'labels.toml'

    def test_falls_back_to_dot_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        Test that without XDG_CONFIG_HOME the default is under ~/.config
        """
        monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        assert gh_labels.default_config_path() == tmp_path / '.config' / 'gh-labels' / 'labels.toml'
