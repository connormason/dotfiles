#!/usr/bin/env python3
"""
Pre-commit hook that blocks employer-internal identifiers from entering this public repository.

File contents, file paths, and git identities are matched against a built-in public baseline plus an optional private
pattern file that lives outside the repository (supplied by the private work dotfiles overlay).
"""
# /// script
# requires-python = ">= 3.9"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import functools
import os
import re
import subprocess
import sys
import textwrap
from collections.abc import Iterable
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Union

# ==========================
# Constants/defaults/globals
# ==========================


VERBOSE:               bool = False
ALLOW_MARKER:          str  = 'leak-guard: allow'
PATTERNS_ENV_VAR:      str  = 'DOTFILES_LEAK_PATTERNS'
IDENTITY_SOURCE:       str  = '<identity>'
MAX_FINDINGS_PER_FILE: int  = 5
BINARY_SNIFF_BYTES:    int  = 8192

# Public vendor hosts that legitimately appear in public files (plist DTDs, App Store and developer links)
PUBLIC_VENDOR_HOSTS: tuple[str, ...] = ('apps', 'developer', 'support', 'www')
_PUBLIC_HOSTS_ALT:   str             = '|'.join(PUBLIC_VENDOR_HOSTS)

# Written so their own source text can never match them (escaped dot before the TLD, `/{2}` in place of a literal
# double slash), which lets this file be scanned like any other without an exclusion
BASELINE_PATTERNS: tuple[str, ...] = (
    # Corporate domain, any subdomain, and email addresses at it -- except the bare public vendor hosts above
    rf'(?<![\w.-])(?!(?:{_PUBLIC_HOSTS_ALT})\.apple\.com\b)(?:[\w-]+\.)*apple\.com\b',
    # Internal bug-tracker URL schemes
    r'\b(?:rdar|radar):/{2}',
)

# `git var GIT_*_IDENT` prints "Name <email> <timestamp> <tz>"; keep everything through the closing ">"
IDENT_RE: re.Pattern[str] = re.compile(r'^(?P<ident>.*?>)')


# ===============
# Types/protocols
# ===============


PathLike = Union[str, Path]


class LeakGuardError(Exception):
    """
    Raised for configuration or environment failures (bad pattern file, unavailable git identity).
    """


@dataclass(frozen=True)
class Finding:
    """
    A single pattern match.

    :param source: file path, or :data:`IDENTITY_SOURCE` for git identity matches
    :param line: 1-based line number, or 0 when the match is in a path or identity
    :param match: matched text (never printed unmasked)
    """
    source: str
    line:   int
    match:  str


# ==================
# Formatting/logging
# ==================


ANSI_COLOR: dict[str, int] = {
    'red':    31, 'bright_red':    91,
    'green':  32, 'bright_green':  92,
    'yellow': 33, 'bright_yellow': 93,
    'blue':   34, 'bright_blue':   94,
    'white':  37, 'bright_white':  97,
}
ANSI_RESET_ALL = '\033[0m'


def style(text: Any = '', *, fg: str | None = None, bold: bool | None = None, dim: bool | None = None) -> str:
    """
    Style text with ANSI escape codes.

    :param text: the value to style (converted with ``str()``)
    :param fg: foreground color name from :data:`ANSI_COLOR`
    :param bold: enable or disable bold mode
    :param dim: enable or disable dim mode
    :return: styled text
    """
    bits: list[str] = []
    if fg:
        bits.append(f'\033[{ANSI_COLOR[fg]}m')
    if bold is not None:
        bits.append(f'\033[{1 if bold else 22}m')
    if dim is not None:
        bits.append(f'\033[{2 if dim else 22}m')
    bits.append(str(text))
    bits.append(ANSI_RESET_ALL)
    return ''.join(bits)


def folduser(path: PathLike) -> str:
    """
    Replace the user's home directory with ``~`` in a path string.

    :param path: path
    :return: folded path string
    """
    return str(path).replace(str(Path.home()), '~')


ERROR = style('ERROR', fg='bright_red',  bold=True)
INFO  = style('INFO',  fg='bright_blue', bold=True)


def printf(
    text: str = '',
    *,
    fg: str | None = None,
    bold: bool | None = None,
    dim: bool | None = None,
    indent: int = 0,
    verbose: bool = False,
) -> None:
    """
    Print styled text with optional indent and verbose gating.

    :param text: text to print
    :param fg: foreground color
    :param bold: bold mode
    :param dim: dim mode
    :param indent: number of spaces to indent output by
    :param verbose: only print when global ``VERBOSE`` is True. Output is dim and sent to stderr
    """
    if verbose and not VERBOSE:
        return
    if verbose:
        fg   = fg or 'bright_white'
        dim  = True if dim is None else dim
        file = sys.stderr
    else:
        file = None

    print(
        style(textwrap.indent(text, ' ' * indent), fg=fg, bold=bold, dim=dim),
        file=file,
    )


# ======================
# Command-line arguments
# ======================


class Args(argparse.Namespace):
    """
    :class:`argparse.Namespace` annotated with args supported by this script.
    """
    filenames:       Sequence[str]  # positional arg(s)
    identity:        bool
    identities_from: str | None
    patterns_file:   str | None
    verbose:         bool


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Parse command-line arguments.

    :param argv: argument list (default: ``sys.argv[1:]``)
    :return: :class:`Args` (typed :class:`argparse.Namespace` subclass)
    """
    global VERBOSE

    parser = argparse.ArgumentParser(
        description='Block employer-internal identifiers from entering this public repository',
        formatter_class=functools.partial(argparse.RawTextHelpFormatter, max_help_position=50),
        add_help=False,
    )

    def add_positional_args() -> None:
        """
        Register the positional arguments group on the parser.
        """
        positional_args = parser.add_argument_group('Positional arguments')
        positional_args.add_argument('filenames', nargs='*', help='Files whose paths and contents are scanned')
    add_positional_args()

    def add_identity_opts() -> None:
        """
        Register the identity options group on the parser.
        """
        identity_opts = parser.add_argument_group('Identity options')
        identity_opts.add_argument(
            '--identity',
            action='store_true',
            help='Also check the git author/committer identity of the commit being made',
        )
        identity_opts.add_argument(
            '--identities-from',
            metavar='FILE',
            help="Check one 'Name <email>' identity per line from FILE ('-' for stdin)",
        )
    add_identity_opts()

    def add_pattern_opts() -> None:
        """
        Register the pattern options group on the parser.
        """
        pattern_opts = parser.add_argument_group('Pattern options')
        pattern_opts.add_argument(
            '--patterns-file',
            metavar='PATH',
            help=(
                f'Private pattern file; must exist when given (default: ${PATTERNS_ENV_VAR}, else\n'
                f'{folduser(default_patterns_file())} if present)'
            ),
        )
    add_pattern_opts()

    def add_output_opts() -> None:
        """
        Register the output options group on the parser.
        """
        output_opts = parser.add_argument_group('Output options')
        output_opts.add_argument('-v', '--verbose', action='store_true', help='Report clean results too')
    add_output_opts()

    def add_other_opts() -> None:
        """
        Register the miscellaneous options group on the parser.
        """
        other_opts = parser.add_argument_group('Other options')
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show this help message and exit',
        )
    add_other_opts()

    args    = parser.parse_args(argv, namespace=Args())
    VERBOSE = args.verbose
    return args


# =================
# Core script logic
# =================


def default_patterns_file() -> Path:
    """
    Location of the private pattern file when neither ``--patterns-file`` nor the env var is given.

    :return: ``$XDG_CONFIG_HOME/dotfiles/leak-patterns.txt`` (``~/.config`` when ``XDG_CONFIG_HOME`` is unset)
    """
    config_home = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(config_home) / 'dotfiles' / 'leak-patterns.txt'


def mask(text: str) -> str:
    """
    Mask matched text so reports never re-publish it.

    :param text: matched text
    :return: ``text`` with every character except the first and last replaced by ``*``
    """
    if len(text) <= 2:
        return '*' * len(text)
    return f'{text[0]}{"*" * (len(text) - 2)}{text[-1]}'


def load_patterns(patterns_file: Path | None, *, required: bool) -> list[re.Pattern[str]]:
    """
    Compile the baseline patterns plus any private patterns.

    :param patterns_file: private pattern file (one regex per line; blank lines and ``#`` comments are ignored)
    :param required: raise when ``patterns_file`` does not exist instead of falling back to the baseline. A path that
        exists but is not a readable regular file (dangling symlink, directory) always raises
    :raises LeakGuardError: if a required file is missing, the file is unreadable or not UTF-8, or a pattern is invalid
    :return: compiled, case-insensitive patterns
    """
    sources: list[str] = list(BASELINE_PATTERNS)
    if patterns_file is not None:
        if not os.path.lexists(patterns_file):
            if required:
                raise LeakGuardError(f'Pattern file not found: {folduser(patterns_file)}')
        elif not patterns_file.is_file():
            raise LeakGuardError(f'Pattern file is not a regular file: {folduser(patterns_file)}')
        else:
            try:
                lines = patterns_file.read_text(encoding='utf-8').splitlines()
            except (OSError, UnicodeDecodeError) as exc:
                raise LeakGuardError(f'Unable to read {folduser(patterns_file)}: {exc!s}') from exc
            sources.extend(line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#'))

    compiled: list[re.Pattern[str]] = []
    for source in sources:
        try:
            compiled.append(re.compile(source, re.IGNORECASE))
        except re.error as exc:
            raise LeakGuardError(f'Invalid pattern {mask(source)!r}: {exc!s}') from exc
        if compiled[-1].search(''):
            raise LeakGuardError(f'Pattern {mask(source)!r} matches the empty string (it would flag every line)')
    return compiled


def mask_matches(text: str, patterns: Sequence[re.Pattern[str]]) -> str:
    """
    Mask every pattern match inside a string so headers and error messages never re-publish a leak.

    :param text: string that may contain matches (e.g. a file path or an OS error message)
    :param patterns: compiled patterns
    :return: ``text`` with each match replaced by :func:`mask` of itself
    """
    for pattern in patterns:
        text = pattern.sub(lambda match: mask(match.group(0)), text)
    return text


def scan_text(text: str, patterns: Sequence[re.Pattern[str]]) -> list[tuple[int, str]]:
    """
    Find pattern matches in text, line by line.

    :param text: text to scan
    :param patterns: compiled patterns
    :return: ``(line_number, matched_text)`` pairs; lines containing :data:`ALLOW_MARKER` are skipped
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for pattern in patterns:
            hits.extend((lineno, match.group(0)) for match in pattern.finditer(line))
    return hits


def scan_file(path: Path, patterns: Sequence[re.Pattern[str]]) -> list[Finding]:
    """
    Scan a file's path and (unless binary) its contents.

    :param path: file to scan
    :param patterns: compiled patterns
    :raises OSError: if the file cannot be read
    :return: findings, path matches first (line 0)
    """
    findings = [Finding(str(path), 0, match.group(0)) for pattern in patterns for match in pattern.finditer(str(path))]

    data = path.read_bytes()
    if b'\0' in data[:BINARY_SNIFF_BYTES]:
        return findings

    text = data.decode('utf-8', errors='replace')
    findings.extend(Finding(str(path), lineno, match) for lineno, match in scan_text(text, patterns))
    return findings


def git_identities() -> list[str]:
    """
    Resolve the author and committer identity git will record for the next commit.

    :raises LeakGuardError: if git cannot determine an identity
    :return: ``Name <email>`` strings for the author and committer
    """
    identities: list[str] = []
    for var in ('GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT'):
        result = subprocess.run(['git', 'var', var], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise LeakGuardError(f'git var {var} failed: {result.stderr.strip()}')
        ident = result.stdout.strip()
        match = IDENT_RE.match(ident)
        identities.append(match.group('ident') if match else ident)
    return identities


def scan_identities(identities: Iterable[str], patterns: Sequence[re.Pattern[str]]) -> list[Finding]:
    """
    Scan git identities.

    :param identities: ``Name <email>`` strings (blank entries are ignored)
    :param patterns: compiled patterns
    :return: findings with source :data:`IDENTITY_SOURCE`
    """
    return [
        Finding(IDENTITY_SOURCE, 0, match.group(0))
        for identity in identities
        if identity.strip()
        for pattern in patterns
        for match in pattern.finditer(identity)
    ]


def report(findings: Sequence[Finding], patterns: Sequence[re.Pattern[str]]) -> None:
    """
    Print findings grouped by source, masked, capped at :data:`MAX_FINDINGS_PER_FILE` per source.

    :param findings: findings to print
    :param patterns: compiled patterns, used to mask matches inside source paths
    """
    by_source: dict[str, list[Finding]] = {}
    for finding in findings:
        by_source.setdefault(finding.source, []).append(finding)

    for source, items in by_source.items():
        printf(f'{ERROR}   {style(mask_matches(source, patterns), fg="bright_white")}')
        for item in items[:MAX_FINDINGS_PER_FILE]:
            if item.line:
                label = f'line {item.line}'
            elif source == IDENTITY_SOURCE:
                label = 'identity'
            else:
                label = 'path'
            printf(f'{label}: internal identifier {mask(item.match)}', fg='bright_red', indent=8)
        if len(items) > MAX_FINDINGS_PER_FILE:
            printf(f'... and {len(items) - MAX_FINDINGS_PER_FILE} more', dim=True, indent=8)


def main(argv: Sequence[str] | None = None) -> int:
    """
    Scan files and identities for employer-internal identifiers.

    :param argv: command-line arguments (default: ``sys.argv[1:]``)
    :return: 0 if clean, 1 on findings or unreadable files, 2 on configuration errors
    """
    args = parse_args(argv)

    explicit = args.patterns_file or os.environ.get(PATTERNS_ENV_VAR)
    try:
        patterns = load_patterns(
            Path(explicit).expanduser() if explicit else default_patterns_file(),
            required=bool(explicit),
        )
    except LeakGuardError as exc:
        printf(f'{ERROR}   {exc!s}')
        return 2

    retval:   int           = 0
    findings: list[Finding] = []
    for filename in args.filenames:
        try:
            findings.extend(scan_file(Path(filename), patterns))
        except OSError as exc:
            printf(f'{ERROR}   {style(mask_matches(filename, patterns), fg="bright_white")}')
            printf(f'Unable to read file: {mask_matches(str(exc), patterns)}', fg='bright_red', indent=8)
            retval = 1

    identities: list[str] = []
    if args.identity:
        try:
            identities.extend(git_identities())
        except LeakGuardError as exc:
            printf(f'{ERROR}   {exc!s}')
            return 2
    if args.identities_from:
        try:
            if args.identities_from == '-':
                identities.extend(sys.stdin.read().splitlines())
            else:
                identities.extend(Path(args.identities_from).read_text(encoding='utf-8').splitlines())
        except (OSError, UnicodeDecodeError) as exc:
            printf(f'{ERROR}   Unable to read identities: {mask_matches(str(exc), patterns)}')
            return 2
    findings.extend(scan_identities(identities, patterns))

    if findings:
        report(findings, patterns)
        return 1

    printf(f'{INFO}    No internal identifiers found ({len(patterns)} patterns)', verbose=True)
    return retval


if __name__ == '__main__':
    sys.exit(main())
