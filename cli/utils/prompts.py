"""
Interactive prompting helpers
"""
from __future__ import annotations

from collections.abc import Sequence

from cli.utils.styling import printf

__all__ = [
    'confirm',
    'select_option',
]


# ==================================================================================================
# Prompting helpers
# ==================================================================================================


def confirm(prompt_text: str, *, default: bool = True, indent: int = 0) -> bool:
    """
    Prompt the user for Y/n confirmation. Returns ``default`` without prompting in CI mode

    :param prompt_text: the question to display
    :param default: the answer used when the user presses Enter without typing
    :param indent: number of spaces to indent the prompt by
    :return: True if the user confirmed; False if they declined or stdin is closed (EOF). Ctrl-C is not caught, so it
             cancels the whole run through :func:`main`
    """
    suffix = '[Y/n]' if default else '[y/N]'
    try:
        answer = input(f'{" " * indent}{prompt_text} {suffix}: ').strip().lower()
    except EOFError:
        printf('')
        return False

    if not answer:
        return default
    return answer in ('y', 'yes')


def select_option(prompt_text: str, options: Sequence[str], *, indent: int = 0) -> str | None:
    """
    Prompt the user to pick one of ``options`` from a numbered menu, by number or by name

    :param prompt_text: heading displayed above the menu
    :param options: the choices, listed in order and numbered from 1
    :param indent: number of spaces to indent the menu by
    :return: the chosen option, or None if the user entered nothing or stdin is closed (EOF). An unrecognized entry
             re-prompts. Ctrl-C is not caught, so it cancels the whole run through :func:`main`
    """
    width = len(str(len(options)))

    printf(prompt_text, fg='bright_white', bold=True, indent=indent)
    for number, option in enumerate(options, start=1):
        printf(f'{number:>{width}}) {option}', indent=indent + 3)

    while True:
        try:
            answer = input(f'{" " * indent}Choice [1-{len(options)}]: ').strip()
        except EOFError:
            printf('')
            return None

        if not answer:
            return None
        if answer.isdecimal() and (1 <= int(answer) <= len(options)):
            return options[int(answer) - 1]
        if answer in options:
            return answer
        printf(f'Not a valid choice: {answer}', fg='bright_yellow', indent=indent)
