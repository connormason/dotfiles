#!/usr/bin/env python3
"""
UserPromptSubmit hook.

Nudge the main agent to delegate information-finding work to the lightweight
``file-searcher`` (Haiku) / ``file-explorer`` (Sonnet) subagents.

When a prompt looks like a "find information" or "understand how this works" request, this hook
injects a short reminder so the heavy grepping/reading happens on a cheaper model in an isolated
context window, keeping the main (Opus) session lean. The reminder is advisory — the main agent
still decides whether to delegate.
"""
from __future__ import annotations

import json
import re
import sys

# Patterns that signal a flat "locate this" request -> file-searcher (Haiku) is the cheap fit.
SEARCH_PATTERNS: tuple[str, ...] = (
    r'\bwhere\s+(is|are|does|do)\b',
    r'\bwhich\s+file',
    r'\bfind\b',
    r'\blocate\b',
    r'\bsearch\s+for\b',
    r'\blook\s+for\b',
    r'\bgrep\b',
    r'\bany\s+(file|files|place|references?|usages?)\b',
    r'\blist\s+all\b',
    r'\b(does|do)\b.*\b(contain|exist|reference|define)',
    r'\bwhat\s+(references?|uses?|calls?|defines?|imports?)\b',
)

# Patterns that signal multi-hop / "explain how it works" reasoning -> file-explorer (Sonnet).
EXPLORE_PATTERNS: tuple[str, ...] = (
    r'\bhow\s+does\b',
    r'\bhow\s+(is|are)\b.*\b(wired|connected|structured|organized|set\s*up)\b',
    r'\btrace\b',
    r'\bwalk\s+me\s+through\b',
    r'\bunderstand\s+(how|the|this)\b',
    r'\bexplain\s+how\b',
    r'\bhow\s+.*\b(relate|relates|interact|flow|flows)\b',
    r'\bend[\s-]to[\s-]end\b',
)

NUDGE = (
    '💡 This looks like an information-finding task. Consider delegating it to a lightweight, '
    'read-only subagent to keep this session cheap and its context clean:\n'
    '- **file-searcher** (Haiku) — fast flat lookups: "where is X", "what references Y", '
    '"find all …". Returns a distilled answer with `file:line` refs.\n'
    '- **file-explorer** (Sonnet) — multi-hop reasoning: tracing how something is wired across '
    'files, explaining a flow, mapping relationships.\n'
    'Both work on any file type (code, JSON/JSON5/YAML, docs, data). Dispatch via the Agent tool '
    'with the matching subagent_type. Skip delegation if the lookup is a single trivial fact you '
    'already know the location of.'
)


def detect_intent(prompt: str) -> str | None:
    """
    Classify a user prompt as a search, explore, or non-matching request.

    Explore patterns are checked first because "how does X work" requests also tend to contain
    search-flavored words, and the explorer is the better default for that class.

    :param prompt: the raw user prompt text.
    :return: ``'explore'``, ``'search'``, or ``None`` when no find-information intent is detected.
    """
    lowered = prompt.lower()
    if any(re.search(pat, lowered) for pat in EXPLORE_PATTERNS):
        return 'explore'
    if any(re.search(pat, lowered) for pat in SEARCH_PATTERNS):
        return 'search'
    return None


def main() -> None:
    """
    Inject the delegation nudge as additional context when the prompt signals find-information intent.

    Detection failures and malformed input are swallowed: a nudge must never block a prompt.
    """
    try:
        payload = json.loads(sys.stdin.read() or '{}')
    except (ValueError, OSError):
        sys.exit(0)

    prompt = str(payload.get('prompt', '')).strip()
    if len(prompt) < 8:
        sys.exit(0)

    if detect_intent(prompt) is None:
        sys.exit(0)

    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName':     'UserPromptSubmit',
            'additionalContext': NUDGE,
        }
    }))


if __name__ == '__main__':
    main()
