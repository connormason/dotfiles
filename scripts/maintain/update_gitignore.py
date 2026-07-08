#!/usr/bin/env python3
"""
Script to update .gitignore file with latest patterns from gitignore.io while preserving custom patterns.

Usage:

    python scripts/maintain/update_gitignore.py [--dry-run] [--force]

"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.request import urlopen

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    'extract_custom_patterns',
    'extract_templates_from_gitignore',
    'fetch_gitignore_content',
    'generate_updated_gitignore',
]


def extract_templates_from_gitignore(gitignore_content: str) -> list[str]:
    """
    Extract template list from gitignore.io URL in the current .gitignore file.

    :param gitignore_content: Content of the current .gitignore file
    :return: list of template names used
    """
    if m := re.search(r'https://www\.toptal\.com/developers/gitignore/api/([a-zA-Z0-9+,]+)', gitignore_content):
        templates_string = m.group(1)
        return templates_string.split(',')
    raise ValueError('Could not find gitignore.io URL in current .gitignore file')


def extract_custom_patterns(gitignore_content: str) -> list[str]:
    """
    Extract custom patterns added after the gitignore.io generated content.

    :param gitignore_content: context of the current .gitignore file
    :return: list of custom pattern lines
    """
    lines = gitignore_content.splitlines()

    # Find the end marker for gitignore.io content
    end_marker_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r'# End of https://www\.toptal\.com/developers/gitignore/api/', line):
            end_marker_idx = i
            break

    if end_marker_idx is None:
        print('Warning: Could not find end marker for gitignore.io content', file=sys.stderr)
        return []

    # Extract everything after the end marker, ignoring empty lines
    custom_lines: list[str] = []
    for line in lines[end_marker_idx + 1:]:
        if (not custom_lines) and (not line.strip()):           # Skip empty lines at the beginning
            continue
        custom_lines.append(line)

    # Remove trailing empty lines
    while custom_lines and not custom_lines[-1].strip():
        custom_lines.pop()
    return custom_lines


def fetch_gitignore_content(templates: list[str]) -> str:
    """
    Fetch fresh .gitignore content from gitignore.io for the given templates. Tries multiple methods as fallbacks.

    :param templates: list of template names
    :return: fresh gitignore content from gitignore.io
    """
    templates_str = ','.join(templates)
    url = f'https://www.toptal.com/developers/gitignore/api/{templates_str}'

    # Method 1: Try Python's urllib first
    try:
        with urlopen(url) as response:                  # noqa: S310
            content = response.read().decode('utf-8')
        print('✅ Successfully fetched content using Python urllib')
        return content

    except URLError as e:
        print(f'⚠️ urllib failed ({e}), trying curl...')

    # Method 2: Try curl as fallback
    try:
        result = subprocess.run(
            ['curl', '-sSL', url],
            check=False,
            capture_output=True,
            text=True,
            timeout=30
        )
        if (result.returncode == 0) and result.stdout:
            print('✅ Successfully fetched content using curl')
            return result.stdout
        print(f'⚠️ curl failed (exit code {result.returncode}), trying git-ignore-io...')

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f'⚠️ curl failed ({e}), trying git-ignore-io...')

    # Method 3: Try git-ignore-io as final fallback
    try:
        result = subprocess.run(
            ['git-ignore-io', templates_str],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            print('✅ Successfully fetched content using git-ignore-io')
            return result.stdout
        raise RuntimeError(f'git-ignore-io failed with exit code {result.returncode}')

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise RuntimeError(f'All methods failed. Final attempt (git-ignore-io): {e}') from e


def generate_updated_gitignore(fresh_content: str, custom_patterns: list[str]) -> str:
    """
    Combine fresh gitignore.io content with custom patterns.

    :param fresh_content: fresh content from gitignore.io
    :param custom_patterns: custom patterns to preserve
    :return: combined gitignore content
    """

    # Ensure fresh content ends with exactly one newline
    fresh_content = fresh_content.rstrip('\n') + '\n'
    if not custom_patterns:
        return fresh_content

    # Add custom patterns after a blank line
    result = fresh_content + '\n'
    for pattern in custom_patterns:
        result += pattern + '\n'
    return result


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` returned by :func:`parse_args`.
    """
    gitignore_path: Path        # --gitignore-path
    dry_run:        bool        # --dry-run
    force:          bool        # --force


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser with auto-generated help from command docstrings.

    :return: :class:`argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser(
        description='Update .gitignore file with latest patterns from gitignore.io',
        formatter_class=partial(argparse.HelpFormatter, max_help_position=80),
        add_help=False,
    )

    def add_file_opts() -> None:
        """
        Add file path options to the argument parser.
        """
        file_opts = parser.add_argument_group('File options')
        file_opts.add_argument(
            '--gitignore-path',
            type=Path,
            default=Path('.gitignore'),
            help='Path to .gitignore file (default: .gitignore)',
        )
    add_file_opts()

    def add_execution_opts() -> None:
        """
        Add execution control options to the argument parser.
        """
        execution_opts = parser.add_argument_group('Execution opts')
        execution_opts.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually updating the file',
        )
        execution_opts.add_argument(
            '--force',
            action='store_true',
            help='Update the file even if no changes are detected',
        )
    add_execution_opts()

    def add_other_opts() -> None:
        """
        Add help and miscellaneous options to the argument parser.
        """
        other_opts = parser.add_argument_group('Other options')
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show help message and exit',
        )
    add_other_opts()

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Main entry point for the script.

    :param argv: argument list of parse. Defaults to ``sys.argv[1:]``
    :return: int script exit code
    """
    parser = build_parser()
    args   = parser.parse_args(argv, namespace=Args())

    # Resolve gitignore path
    if not args.gitignore_path.exists():
        print(f'Error: .gitignore file not found at {args.gitignore_path}', file=sys.stderr)
        return 1

    try:

        # Read current .gitignore
        current_content = args.gitignore_path.read_text(encoding='utf-8')

        # Extract templates and custom patterns
        print('Extracting templates and custom patterns...')
        templates       = extract_templates_from_gitignore(current_content)
        custom_patterns = extract_custom_patterns(current_content)

        print(f"Found templates: {', '.join(templates)}")
        if custom_patterns:
            print(f'Found {len(custom_patterns)} custom pattern(s)')
        else:
            print('No custom patterns found')

        # Fetch fresh content from gitignore.io
        print('Fetching fresh content from gitignore.io...')
        fresh_content = fetch_gitignore_content(templates)

        # Generate updated content
        updated_content = generate_updated_gitignore(fresh_content, custom_patterns)

        # Check if content has actually changed
        if (not args.force) and (updated_content == current_content):
            print('✅ .gitignore file is already up to date')
            return 0
        if args.dry_run:
            print('🔍 Dry run - would update .gitignore file with the following content:')
            print('=' * 50)
            print(updated_content)
            print('=' * 50)
            return 0

        # Write updated content
        args.gitignore_path.write_text(updated_content, encoding='utf-8')
        print(f'✅ Successfully updated {args.gitignore_path}')
        return 0

    except KeyboardInterrupt:
        print('Cancelled')
        return 1

    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
