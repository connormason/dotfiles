"""
Unit tests for stow/ghtools/.local/bin/gh-labels
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from itertools import pairwise
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


class FakeGh:
    """
    Stand-in for ``run_gh`` that records calls and serves a canned label list in two pages
    """
    def __init__(self, existing: list[dict[str, object]] | None = None) -> None:
        self.existing = existing or []
        self.repo_url = 'https://ghe.example.com/me/proj'
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        if args[:2] == ('repo', 'view'):
            return json.dumps({'url': self.repo_url})
        if '--paginate' in args:
            return json.dumps([self.existing[:2], self.existing[2:]])
        return ''

    @property
    def mutations(self) -> list[tuple[str, str, dict[str, str]]]:
        """
        Every non-GET ``gh api`` call as ``(method, endpoint, fields)``.
        """
        found = []
        for args in self.calls:
            if args[0] != 'api':
                continue
            method = args[args.index('--method') + 1]
            if method == 'GET':
                continue
            fields = {
                pair.partition('=')[0]: pair.partition('=')[2]
                for flag, pair in pairwise(args)
                if flag == '--raw-field'
            }
            found.append((method, args[1], fields))
        return found


EXISTING: list[dict[str, object]] = [
    {'name': 'bug',     'color': 'D73A4A', 'description': None},
    {'name': 'Docs',    'color': '0075ca', 'description': None},
    {'name': 'wontfix', 'color': 'ffffff', 'description': 'This will not be worked on'},
]
DESIRED = [
    Label('bug',     'd73a4a'),
    Label('docs',    '0075ca', 'Documentation'),
    Label('feature', '5ab1cd', 'New capability'),
]
REPO = gh_labels.RepoRef(None, 'me', 'proj')


@pytest.fixture
def fake_gh(monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    """
    Replace ``run_gh`` with a recording fake holding the sample repository's labels
    """
    fake = FakeGh(EXISTING)
    monkeypatch.setattr(gh_labels, 'run_gh', fake)
    return fake


class TestRepoRef:
    """
    Tests for parse_repo and RepoRef
    """
    @pytest.mark.parametrize(
        ('spec', 'host', 'owner', 'name'),
        [
            ('me/proj',                      None,              'me', 'proj'),
            ('ghe.example.com/me/proj',      'ghe.example.com', 'me', 'proj'),
            ('me/my.repo-name_2',            None,              'me', 'my.repo-name_2'),
        ],
    )
    def test_valid_specs(self, spec: str, host: str | None, owner: str, name: str) -> None:
        """
        Test that OWNER/REPO and HOST/OWNER/REPO are both understood
        """
        assert gh_labels.parse_repo(spec) == gh_labels.RepoRef(host, owner, name)

    @pytest.mark.parametrize('spec', ['proj', 'a/b/c/d', '', 'me/', '/proj', 'me/pro j'])
    def test_invalid_specs(self, spec: str) -> None:
        """
        Test that malformed repository specs raise
        """
        with pytest.raises(gh_labels.LabelsError, match='invalid repo'):
            gh_labels.parse_repo(spec)

    def test_endpoint_and_str(self) -> None:
        """
        Test the labels endpoint and the display form, with and without a host
        """
        assert REPO.labels_endpoint == 'repos/me/proj/labels'
        assert str(REPO) == 'me/proj'
        assert str(gh_labels.RepoRef('h.example.com', 'me', 'proj')) == 'h.example.com/me/proj'


class TestRunGh:
    """
    Tests for run_gh
    """
    def test_returns_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that stdout of a successful gh call is returned and the argv is passed as a list
        """
        seen: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> object:
            seen.append(cmd)
            return type('Result', (), {'stdout': 'ok\n'})()

        monkeypatch.setattr(gh_labels.subprocess, 'run', fake_run)

        assert gh_labels.run_gh('api', 'x') == 'ok\n'
        assert seen == [['gh', 'api', 'x']]

    def test_missing_gh_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a missing gh binary raises a LabelsError that says so
        """
        def fake_run(*args: object, **kwargs: object) -> object:
            raise FileNotFoundError

        monkeypatch.setattr(gh_labels.subprocess, 'run', fake_run)

        with pytest.raises(gh_labels.LabelsError, match='not installed'):
            gh_labels.run_gh('api', 'x')

    def test_failure_includes_stderr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that a failing gh call surfaces its stderr text
        """
        def fake_run(cmd: list[str], **kwargs: object) -> object:
            raise gh_labels.subprocess.CalledProcessError(1, cmd, stderr='HTTP 404: Not Found\n')

        monkeypatch.setattr(gh_labels.subprocess, 'run', fake_run)

        with pytest.raises(gh_labels.LabelsError, match='HTTP 404'):
            gh_labels.run_gh('api', 'x')


class TestGhApi:
    """
    Tests for gh_api, current_repo, resolve_repo, and fetch_labels
    """
    def test_argument_shape(self, fake_gh: FakeGh) -> None:
        """
        Test the argv built for a mutating call with a host and raw fields
        """
        repo = gh_labels.RepoRef('ghe.example.com', 'me', 'proj')
        gh_labels.gh_api(repo, 'repos/me/proj/labels', method='POST', fields={'name': 'a=b', 'color': 'ffffff'})

        assert fake_gh.calls == [(
            'api', 'repos/me/proj/labels', '--method', 'POST', '--hostname', 'ghe.example.com',
            '--raw-field', 'name=a=b', '--raw-field', 'color=ffffff',
        )]

    def test_paginate_uses_slurp(self, fake_gh: FakeGh) -> None:
        """
        Test that paginated reads ask gh to slurp pages into one JSON array
        """
        gh_labels.gh_api(REPO, 'repos/me/proj/labels', paginate=True)

        assert fake_gh.calls[0][-2:] == ('--paginate', '--slurp')

    def test_current_repo_reads_host_from_url(self, fake_gh: FakeGh) -> None:
        """
        Test that the repository of the working directory is found through gh repo view
        """
        assert gh_labels.current_repo() == gh_labels.RepoRef('ghe.example.com', 'me', 'proj')

    def test_current_repo_failure_suggests_repo_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Test that failing to detect a repository hints at --repo
        """
        def failing(*args: str) -> str:
            raise gh_labels.LabelsError('gh repo failed: not a git repository')

        monkeypatch.setattr(gh_labels, 'run_gh', failing)

        with pytest.raises(gh_labels.LabelsError, match='--repo'):
            gh_labels.current_repo()

    def test_resolve_repo_prefers_the_explicit_spec(self, fake_gh: FakeGh) -> None:
        """
        Test that an explicit spec is parsed without calling gh
        """
        assert gh_labels.resolve_repo('me/proj') == REPO
        assert fake_gh.calls == []

    def test_fetch_labels_flattens_pages_and_normalises(self, fake_gh: FakeGh) -> None:
        """
        Test that pages are flattened, colors lowercased, and null descriptions become empty strings
        """
        assert gh_labels.fetch_labels(REPO) == [
            Label('bug',     'd73a4a', ''),
            Label('Docs',    '0075ca', ''),
            Label('wontfix', 'ffffff', 'This will not be worked on'),
        ]


class TestBuildPlan:
    """
    Tests for build_plan
    """
    def test_classifies_every_label(self) -> None:
        """
        Test create, update (case-insensitive match), unchanged, and extra classification
        """
        existing = gh_labels.labels_from_api(EXISTING)
        plan     = gh_labels.build_plan(DESIRED, existing)

        assert plan.create    == [Label('feature', '5ab1cd', 'New capability')]
        assert plan.update    == [(Label('Docs', '0075ca', ''), Label('docs', '0075ca', 'Documentation'))]
        assert plan.unchanged == [Label('bug', 'd73a4a', '')]
        assert plan.extra     == [Label('wontfix', 'ffffff', 'This will not be worked on')]

    def test_identical_sets_need_no_changes(self) -> None:
        """
        Test that matching sets yield an empty create, update, and extra list
        """
        plan = gh_labels.build_plan(DESIRED, DESIRED)

        assert (plan.create, plan.update, plan.extra) == ([], [], [])
        assert plan.unchanged == DESIRED


class TestApplyPlan:
    """
    Tests for apply_plan and summarize
    """
    def _plan(self) -> object:
        return gh_labels.build_plan(DESIRED, gh_labels.labels_from_api(EXISTING))

    def test_creates_and_updates(self, fake_gh: FakeGh) -> None:
        """
        Test the POST and PATCH calls, including a URL-quoted label name
        """
        existing = [Label('work in progress', 'c5def5', '')]
        desired  = [Label('work in progress', '000000', 'WIP'), Label('new', 'ffffff', '')]

        gh_labels.apply_plan(REPO, gh_labels.build_plan(desired, existing), prune=False, dry_run=False)

        assert fake_gh.mutations == [
            ('POST',  'repos/me/proj/labels', {'name': 'new', 'color': 'ffffff', 'description': ''}),
            (
                'PATCH',
                'repos/me/proj/labels/work%20in%20progress',
                {'new_name': 'work in progress', 'color': '000000', 'description': 'WIP'},
            ),
        ]

    def test_extras_are_kept_without_prune(self, fake_gh: FakeGh, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that labels missing from the config are reported but not deleted by default
        """
        gh_labels.apply_plan(REPO, self._plan(), prune=False, dry_run=False)

        assert all(method != 'DELETE' for method, _, _ in fake_gh.mutations)
        assert 'wontfix' in capsys.readouterr().out

    def test_prune_deletes_extras(self, fake_gh: FakeGh) -> None:
        """
        Test that --prune deletes labels missing from the config
        """
        gh_labels.apply_plan(REPO, self._plan(), prune=True, dry_run=False)

        assert ('DELETE', 'repos/me/proj/labels/wontfix', {}) in fake_gh.mutations

    def test_dry_run_makes_no_mutations(self, fake_gh: FakeGh, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that a dry run reports every action yet issues no mutating call, even with prune
        """
        gh_labels.apply_plan(REPO, self._plan(), prune=True, dry_run=True)
        out = capsys.readouterr().out

        assert fake_gh.mutations == []
        assert all(word in out for word in ('create', 'update', 'delete'))

    def test_summary_counts(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        Test that the summary line reports counts and flags kept extras
        """
        gh_labels.summarize(self._plan(), prune=False, dry_run=False)
        out = capsys.readouterr().out

        assert '1 created, 1 updated, 1 unchanged' in out
        assert '--prune' in out
