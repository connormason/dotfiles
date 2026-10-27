"""
Unit tests for scripts/utility/summarize_stow.awk

The summarizer distills a captured GNU Stow ``--restow --verbose`` log into the net state change
(added / updated / removed), using stow's ``(reverts previous action)`` marker to filter out the per-file UNLINK/LINK
churn. These tests feed synthetic log fixtures to the awk script via subprocess and assert the categorization, so they
exercise the real classification logic without touching ``$HOME``.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SUMMARIZER = Path(__file__).parent.parent.parent / 'scripts' / 'utility' / 'summarize_stow.awk'


def run_summarizer(log: str, *, dry: bool = False) -> str:
    """
    Pipe ``log`` through the awk summarizer and return its stdout.

    :param log: the synthetic stow verbose log to feed on stdin.
    :param dry: when True, pass ``-v dry=1`` so the summary uses "would …" phrasing.
    :return: the summarizer's stdout.
    """
    cmd: list[str] = ['awk']
    if dry:
        cmd += ['-v', 'dry=1']
    cmd += ['-f', str(SUMMARIZER)]

    result = subprocess.run(cmd, input=log, capture_output=True, text=True, check=True)
    return result.stdout


class TestSummarizeStow:
    """
    Categorization tests for the stow change summarizer
    """
    def test_noop_restow_reports_no_changes(self) -> None:
        """
        A restow where every relink reverts its unlink is a net no-op
        """
        log = (
            'UNLINK: .filea\n'
            'UNLINK: .fileb\n'
            'LINK: .filea => ../stow/pkg/.filea (reverts previous action)\n'
            'LINK: .fileb => ../stow/pkg/.fileb (reverts previous action)\n'
        )
        out = run_summarizer(log)
        assert out.strip() == 'stow: no changes (already current)'

    def test_new_file_is_added(self) -> None:
        """
        A LINK with no revert and no prior UNLINK is a newly added link
        """
        log = (
            'UNLINK: .filea\n'
            'LINK: .filea => ../stow/pkg/.filea (reverts previous action)\n'
            'LINK: .filec => ../stow/pkg/.filec\n'
        )
        out = run_summarizer(log)
        assert '+ ~/.filec (linked)'                 in out
        assert 'stow: 1 added, 0 updated, 0 removed' in out

    def test_removed_file_is_removed(self) -> None:
        """
        A genuine UNLINK with no replacement LINK is a removal
        """
        log = (
            'UNLINK: .filea\n'
            'UNLINK: .fileb\n'
            'LINK: .filea => ../stow/pkg/.filea (reverts previous action)\n'
        )
        out = run_summarizer(log)
        assert '- ~/.fileb (removed)'                in out
        assert 'stow: 0 added, 0 updated, 1 removed' in out

    def test_changed_target_is_updated(self) -> None:
        """
        A genuine UNLINK paired with a non-revert LINK means the link target changed
        """
        log = (
            'UNLINK: .zshrc\n'
            'LINK: .zshrc => ../stow/shell/.zshrc\n'
        )
        out = run_summarizer(log)
        assert '~ ~/.zshrc (updated)'                in out
        assert 'stow: 0 added, 1 updated, 0 removed' in out

    def test_path_spam_lines_are_ignored(self) -> None:
        """
        The spurious `/`-prefixed path lines GNU Stow 2.4.1 emits on macOS do not affect the counts
        """
        log = (
            'LINK: .new => ../stow/x/.new\n'
            '/private/tmp/home/.new\n'
            '/private/tmp/stow/x/.new\n'
            'WARNING: in simulation mode so not modifying filesystem.\n'
        )
        out = run_summarizer(log)
        assert '+ ~/.new (linked)'                   in out
        assert 'stow: 1 added, 0 updated, 0 removed' in out

    def test_mixed_changes_counted_correctly(self) -> None:
        """
        Added, updated, and removed entries are all classified within one log
        """
        log = (
            'LINK: .new => ../stow/x/.new\n'
            'UNLINK: .gone\n'
            'UNLINK: .chg\n'
            'LINK: .chg => ../stow/y/.chg\n'
        )
        out = run_summarizer(log)
        assert '+ ~/.new (linked)'                   in out
        assert '~ ~/.chg (updated)'                  in out
        assert '- ~/.gone (removed)'                 in out
        assert 'stow: 1 added, 1 updated, 1 removed' in out

    def test_dry_run_uses_would_phrasing(self) -> None:
        """
        With dry=1 the summary is phrased as a preview rather than an applied change
        """
        log = (
            'LINK: .new => ../stow/x/.new\n'
            'UNLINK: .gone\n'
            'UNLINK: .chg\n'
            'LINK: .chg => ../stow/y/.chg\n'
        )
        out = run_summarizer(log, dry=True)
        assert 'dry-run preview'          in out
        assert '+ ~/.new (would link)'    in out
        assert '~ ~/.chg (would update)'  in out
        assert '- ~/.gone (would remove)' in out

    def test_empty_log_reports_no_changes(self) -> None:
        """
        An empty log (stow ran silently with nothing to do) reports no changes
        """
        out = run_summarizer('')
        assert out.strip() == 'stow: no changes (already current)'

    @pytest.mark.parametrize(
        ('log', 'expected'),
        [
            ('LINK: .a => ../stow/p/.a\n',             'stow: 1 added, 0 updated, 0 removed'),
            ('UNLINK: .a\n',                           'stow: 0 added, 0 updated, 1 removed'),
            ('UNLINK: .a\nLINK: .a => ../stow/p/.a\n', 'stow: 0 added, 1 updated, 0 removed'),
        ],
    )
    def test_single_action_totals(self, log: str, expected: str) -> None:
        """
        Each elementary action maps to the expected totals line
        """
        assert expected in run_summarizer(log)
