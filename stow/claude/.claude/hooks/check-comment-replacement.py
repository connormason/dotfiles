#!/usr/bin/env python3
"""
PostToolUse hook: detect when code is replaced with comments.
"""
from __future__ import annotations

import json
import re
import sys

COMMENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'^\s*//.*'),          # // comment
    re.compile(r'^\s*/\*.*\*/\s*$'),  # /* comment */
    re.compile(r'^\s*#(?!#).*'),      # # comment (not ## markdown headers)
    re.compile(r'^\s*--.*'),          # -- comment (SQL/Lua)
    re.compile(r'^\s*\*\s+.*'),       # * comment (block continuation)
    re.compile(r'^\s*<!--.*-->\s*$'), # <!-- comment -->
]

DOC_EXTENSIONS: set[str] = {'md', 'mdx', 'txt', 'rst'}


def is_comment(line: str) -> bool:
    """
    Determine whether a line consists solely of a comment.

    :param line: the source line to inspect.
    :return: ``True`` if the line matches a known comment pattern.
    """
    return any(p.match(line) for p in COMMENT_PATTERNS)


def analyze_edit(old_str: str, new_str: str, *, file_path: str | None = None) -> str | None:
    """
    Inspect a single edit for a code-replaced-with-comments violation.

    :param old_str: the original text being replaced.
    :param new_str: the replacement text.
    :param file_path: the path of the file being edited, used to skip documentation files.
    :return: a violation message if the edit replaces code with comments, otherwise ``None``.
    """
    if file_path:
        ext = file_path.rsplit('.', 1)[-1].lower()
        if ext in DOC_EXTENSIONS:
            return None

    old_lines: list[str] = [line for line in old_str.split('\n') if line.strip()]
    new_lines: list[str] = [line for line in new_str.split('\n') if line.strip()]

    if (not old_lines) or (not new_lines):
        return None

    old_code_lines: list[str] = [line for line in old_lines if not is_comment(line)]
    if not old_code_lines:
        return None
    if not all(is_comment(line) for line in new_lines):
        return None

    size_diff = abs(len(old_lines) - len(new_lines))
    if size_diff <= max(2, len(old_lines) * 0.5):
        return 'Code replaced with comments - if removing code, delete it cleanly without explanatory comments'
    return None


def main() -> None:
    """
    Read the tool payload from stdin and block edits that replace code with comments.
    """
    payload   = json.loads(sys.stdin.read() or '{}')
    tool_name = payload.get('tool_name', '')

    if tool_name not in ('Edit', 'MultiEdit'):
        sys.exit(0)

    tool_input = payload.get('tool_input', {})

    violations: list[str] = []
    if tool_name == 'Edit':
        old_str = tool_input.get('old_string', '')
        new_str = tool_input.get('new_string', '')
        if old_str and new_str and (reason := analyze_edit(old_str, new_str, file_path=tool_input.get('file_path'))):
            violations.append(reason)

    elif tool_name == 'MultiEdit':
        file_path = tool_input.get('file_path')
        for edit in tool_input.get('edits', []):
            old_str = edit.get('old_string', '')
            new_str = edit.get('new_string', '')
            if old_str and new_str and (reason := analyze_edit(old_str, new_str, file_path=file_path)):
                violations.append(reason)

    if violations:
        count = len(violations)
        print(
            f"⚠️ Code Replaced with Comments\n\n"
            f"Found {count} instance{'s' if count != 1 else ''} where code is replaced with comments.\n\n"
            "When removing code, delete it completely — do not replace it with explanatory comments.\n"
            "Use git commit messages to document why code was removed, not inline comments.",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == '__main__':
    main()
