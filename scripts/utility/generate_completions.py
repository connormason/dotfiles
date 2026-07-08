#!/usr/bin/env python3
"""
Generate shell completion scripts for argparse-based CLI tools.

Supports bash, zsh, and fish. Can auto-detect an :class:`argparse.ArgumentParser` from a target script by looking for
well-known factory functions (``build_parser``, ``get_parser``, etc.) or module-level parser instances.

Usage::

    # Auto-detect parser factory in a script
    python scripts/utility/generate_completions.py scripts/maintain/update_prek.py zsh

    # Explicit parser factory function name
    python scripts/utility/generate_completions.py scripts/maintain/update_prek.py zsh --parser build_parser

    # Override the command name used in the completion script
    python scripts/utility/generate_completions.py scripts/maintain/update_prek.py zsh --name update_prek

"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import ClassVar
from typing import Literal
from typing import get_args

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Sequence
    from types import ModuleType


SupportedShell = Literal['bash', 'zsh', 'fish']

# Repo-relative path to this generator, used in the header comments of generated completion scripts.
GENERATOR_PATH: str = 'scripts/utility/generate_completions.py'

PARSER_FACTORY_NAMES: list[str] = [
    'build_parser',
    'get_parser',
    'create_parser',
    'make_parser',
    'parser',
]

# =========================
# String manipulation utils
# =========================


ANSI_PATTERN: re.Pattern[str] = re.compile(r'\033\[[;?0-9]*[a-zA-Z]')


def strip_ansi(text: str) -> str:
    """
    Remove ANSI escape sequences from a string.

    :param text: text potentially containing ANSI codes
    :return: cleaned text
    """
    return ANSI_PATTERN.sub('', text)


# ==========================
# Parser metadata extraction
# ==========================


@dataclass(frozen=True)
class CompletionOption:
    """
    Extracted argument metadata for shell completion generation.
    """
    flags:       tuple[str, ...]
    help:        str
    takes_value: bool
    metavar:     str | None             = None
    choices:     tuple[str, ...] | None = None


def extract_parser_options(parser: argparse.ArgumentParser) -> list[CompletionOption]:
    """
    Extract option metadata from an :class:`argparse.ArgumentParser` for completion generation.

    Skips subparser actions and positional arguments. Splits :class:`argparse.BooleanOptionalAction` into separate
    entries for ``--flag`` and ``--no-flag``.

    :param parser: the parser to introspect
    :return: list of extracted option info
    """
    options: list[CompletionOption] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if not action.option_strings:
            continue

        help_text = ''
        if action.help and (action.help != argparse.SUPPRESS):
            help_text = strip_ansi(str(action.help))
            help_text = help_text.split('[')[0].strip()
            help_text = help_text.splitlines()[0].strip() if help_text else ''

        takes_value = not isinstance(
            action,
            (
                argparse._StoreTrueAction,
                argparse._StoreFalseAction,
                argparse._StoreConstAction,
                argparse._CountAction,
                argparse._HelpAction,
                argparse.BooleanOptionalAction,
            ),
        )

        choices = tuple(str(c) for c in action.choices) if action.choices else None
        metavar = action.metavar if isinstance(action.metavar, str) else None

        if isinstance(action, argparse.BooleanOptionalAction):
            options.extend(
                CompletionOption(
                    flags=(opt_str,),
                    help=help_text if not opt_str.startswith('--no-') else '',
                    takes_value=False,
                )
                for opt_str in action.option_strings
            )

        else:
            options.append(
                CompletionOption(
                    flags=tuple(action.option_strings),
                    help=help_text,
                    takes_value=takes_value,
                    metavar=metavar,
                    choices=choices,
                )
            )

    return options


def extract_subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """
    Extract the subcommand-name-to-subparser mapping from a parser.

    :param parser: the root parser
    :return: mapping of command name to its subparser
    """
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def extract_positional_choices(parser: argparse.ArgumentParser) -> list[tuple[str, tuple[str, ...]]]:
    """
    Extract positional arguments with constrained choices from a parser.

    :param parser: the parser to introspect
    :return: list of ``(help_text, choices)`` tuples for positional arguments that define choices
    """
    positionals: list[tuple[str, tuple[str, ...]]] = []
    for action in parser._actions:
        if action.option_strings or isinstance(action, (argparse._SubParsersAction, argparse._HelpAction)):
            continue
        if action.choices:
            help_text = ''
            if action.help and (action.help != argparse.SUPPRESS):
                help_text = strip_ansi(str(action.help)).split('[')[0].strip()
            positionals.append((help_text, tuple(str(c) for c in action.choices)))
    return positionals


def get_subparser_description(subparser: argparse.ArgumentParser) -> str:
    """
    Get the first line of a subparser's description, with ANSI codes stripped.

    :param subparser: the subparser
    :return: first line of description, or empty string
    """
    desc = subparser.description or ''
    desc = strip_ansi(desc)
    return desc.splitlines()[0].strip() if desc else ''


# ===========
# zsh helpers
# ===========


def zsh_escape(text: str) -> str:
    """
    Escape text for zsh completion spec strings.

    :param text: raw description text
    :return: text safe for use inside single-quoted zsh specs
    """
    return text.replace("'", "'\\''").replace('[', '\\[').replace(']', '\\]').replace(':', '\\:')


def zsh_option_specs(opt: CompletionOption) -> list[str]:
    """
    Format a :class:`CompletionOption` as one or more zsh ``_arguments`` spec strings.

    Generates a separate spec for each flag string (short and long variants).

    :param opt: the option to format
    :return: list of single-quoted zsh _arguments specs
    """
    desc = zsh_escape(opt.help) if opt.help else ''

    specs: list[str] = []
    for flag in opt.flags:
        if opt.takes_value:
            eq          = '=' if flag.startswith('--') else ''
            argname     = opt.metavar or 'value'
            choices_str = f'({" ".join(opt.choices)})' if opt.choices else ''
            specs.append(f"'{flag}{eq}[{desc}]:{argname}:{choices_str}'")
        else:
            specs.append(f"'{flag}[{desc}]'")
    return specs


# =====================
# Completion generators
# =====================


@dataclass
class CompletionConfig:
    """
    Configuration for completion script generation.

    :param command_name: command name for the completion function (e.g. ``update_prek.py``)
    :param script_path: display path to the script (for header comments)
    :param project_name: project name (for header comments)
    """
    command_name: str
    script_path:  str = ''
    project_name: str = ''

    FUNC_NAME_CHARS: ClassVar[re.Pattern[str]] = re.compile(r'[^a-zA-Z0-9_]')

    @property
    def func_name(self) -> str:
        """
        Shell-safe function name derived from the command name.

        :return: function name prefixed with ``_``
        """
        return '_' + self.FUNC_NAME_CHARS.sub('_', self.command_name)


def generate_zsh_completions(parser: argparse.ArgumentParser, config: CompletionConfig) -> str:
    """
    Generate a zsh completion script from an argument parser.

    :param parser: the fully built root argument parser (with subparsers)
    :param config: completion configuration
    :return: the complete zsh completion script
    """
    cmd  = config.command_name
    func = config.func_name

    lines: list[str] = [
        f'#compdef {cmd}',
        '',
        f'# Shell completions for {cmd}' + (f' ({config.project_name})' if config.project_name else ''),
    ]
    if config.script_path:
        lines.extend([
            f'# Generated by: python {GENERATOR_PATH} {config.script_path} zsh',
            '#',
            '# Installation:',
            f'#   eval "$(python {GENERATOR_PATH} {config.script_path} zsh)"',
            '#',
            '#   Or save to a file in your fpath:',
            f'#   python {GENERATOR_PATH} {config.script_path} zsh > ~/.zsh/completions/_{cmd}',
            '#',
            f"#   For aliases (e.g. alias myalias='python {config.script_path}'):",
            f'#   compdef {func} myalias',
        ])
    lines.extend(['', f'{func}() {{', '    local state', ''])

    # Build _arguments spec with root options + subcommand dispatch
    root_options = extract_parser_options(parser)

    specs: list[str] = [spec for opt in root_options for spec in zsh_option_specs(opt)]
    specs.append("'1:command:->commands'")
    specs.append("'*::arg:->args'")

    lines.append('    _arguments -C \\')
    for i, spec in enumerate(specs):
        sep = ' \\' if i < len(specs) - 1 else ''
        lines.append(f'        {spec}{sep}')

    # Command completion
    subparser_choices = extract_subparser_choices(parser)
    lines.extend([
        '',
        '    case $state in',
        '        commands)',
        '            local -a commands=(',
    ])
    for cmd_name, subparser in subparser_choices.items():
        desc = zsh_escape(get_subparser_description(subparser))
        lines.append(f"                '{cmd_name}:{desc}'")

    lines.extend([
        '            )',
        "            _describe 'command' commands",
        '            ;;',
    ])

    # Per-command argument completion
    lines.extend(['        args)', '            case $words[1] in'])
    for cmd_name, subparser in subparser_choices.items():
        cmd_options     = extract_parser_options(subparser)
        cmd_positionals = extract_positional_choices(subparser)
        if (not cmd_options) and (not cmd_positionals):
            continue

        cmd_specs = [spec for opt in cmd_options for spec in zsh_option_specs(opt)]
        for pos_help, pos_choices in cmd_positionals:
            desc = zsh_escape(pos_help) if pos_help else ''
            cmd_specs.append(f"':{desc}:({' '.join(pos_choices)})'")

        lines.extend([
            f'                {cmd_name})',
            '                    _arguments \\'
        ])
        for i, spec in enumerate(cmd_specs):
            sep = ' \\' if i < len(cmd_specs) - 1 else ''
            lines.append(f'                        {spec}{sep}')
        lines.append('                    ;;')

    lines.extend([
        '            esac',
        '            ;;',
        '    esac',
        '}',
        '',
        f'{func} "$@"',
        '',
    ])
    return '\n'.join(lines)


def generate_bash_completions(parser: argparse.ArgumentParser, config: CompletionConfig) -> str:
    """
    Generate a bash completion script from an argument parser.

    :param parser: the fully built root argument parser (with subparsers)
    :param config: completion configuration
    :return: the complete bash completion script
    """
    cmd  = config.command_name
    func = config.func_name
    subparser_choices = extract_subparser_choices(parser)

    # Collect all command names
    cmd_names = list(subparser_choices.keys())

    # Collect global option strings
    root_options = extract_parser_options(parser)
    global_opts  = ' '.join(flag for opt in root_options for flag in opt.flags)

    lines: list[str] = [
        '#!/usr/bin/env bash',
        '',
        f'# Shell completions for {cmd}' + (f' ({config.project_name})' if config.project_name else ''),
    ]
    if config.script_path:
        lines.extend([
            f'# Generated by: python {GENERATOR_PATH} {config.script_path} bash',
            '#',
            '# Installation:',
            f'#   eval "$(python {GENERATOR_PATH} {config.script_path} bash)"',
            '#',
            '#   Or save to a file:',
            f'#   python {GENERATOR_PATH} {config.script_path} bash > ~/.bash_completions/{cmd}',
            '#',
            f"#   For aliases (e.g. alias myalias='python {config.script_path}'):",
            f'#   complete -F {func} myalias',
        ])
    lines.extend([
        '',
        f'{func}() {{',
        '    local cur cmd',
        '    COMPREPLY=()',
        '    cur="${COMP_WORDS[COMP_CWORD]}"',
        '',
        '    # Find the subcommand',
        '    cmd=""',
        '    local i',
        '    for ((i=1; i<COMP_CWORD; i++)); do',
        '        case "${COMP_WORDS[$i]}" in',
        '            -*) ;;',
        '            *) cmd="${COMP_WORDS[$i]}"; break ;;',
        '        esac',
        '    done',
        '',
        '    # No subcommand yet: offer commands and global options',
        '    if [[ -z "$cmd" ]]; then',
        f'        COMPREPLY=( $(compgen -W "{" ".join(cmd_names)} {global_opts}" -- "$cur") )',
        '        return',
        '    fi',
        '',
        '    # Per-command options',
        '    case "$cmd" in',
    ])

    for cmd_name, subparser in subparser_choices.items():
        cmd_options     = extract_parser_options(subparser)
        cmd_positionals = extract_positional_choices(subparser)

        all_flags   = ' '.join(flag for opt in cmd_options for flag in opt.flags)
        all_choices = ' '.join(choice for _, choices in cmd_positionals for choice in choices)
        all_words   = f'{all_flags} {all_choices}'.strip()
        if all_words:
            lines.extend([
                f'        {cmd_name})',
                f'            COMPREPLY=( $(compgen -W "{all_words}" -- "$cur") )',
                '            ;;',
            ])

    lines.extend([
        '    esac',
        '}',
        '',
        f'complete -F {func} {cmd}',
        '',
    ])
    return '\n'.join(lines)


def generate_fish_completions(parser: argparse.ArgumentParser, config: CompletionConfig) -> str:
    """
    Generate a fish completion script from an argument parser.

    :param parser: the fully built root argument parser (with subparsers)
    :param config: completion configuration
    :return: the complete fish completion script
    """
    cmd = config.command_name
    subparser_choices = extract_subparser_choices(parser)

    lines: list[str] = [
        f'# Shell completions for {cmd}' + (f' ({config.project_name})' if config.project_name else ''),
    ]
    if config.script_path:
        lines.extend([
            f'# Generated by: python {GENERATOR_PATH} {config.script_path} fish',
            '#',
            '# Installation:',
            f'#   python {GENERATOR_PATH} {config.script_path} fish > ~/.config/fish/completions/{cmd}.fish',
            '#',
            '#   For aliases, add:',
            f"#   alias myalias='python {config.script_path}'",
            f'#   complete -c myalias --wraps {cmd}',
        ])
    lines.extend([
        '',
        '# Disable file completions by default',
        f'complete -c {cmd} -f',
        '',
        '# Commands',
    ])

    for cmd_name, subparser in subparser_choices.items():
        desc = get_subparser_description(subparser).replace("'", "\\'")
        lines.append(f"complete -c {cmd} -n '__fish_use_subcommand' -a '{cmd_name}' -d '{desc}'")

    # Global options
    if root_options := extract_parser_options(parser):
        lines.extend([
            '',
            '# Global options',
        ])
        for opt in root_options:
            desc = opt.help.replace("'", "\\'") if opt.help else ''
            for flag in opt.flags:
                if flag.startswith('--'):
                    long_name = flag[2:]
                    req_arg   = ' -r' if opt.takes_value else ''
                    lines.append(f"complete -c {cmd} -l '{long_name}'{req_arg} -d '{desc}'")
                elif flag.startswith('-') and len(flag) == 2:
                    short_name = flag[1]
                    req_arg    = ' -r' if opt.takes_value else ''
                    lines.append(f"complete -c {cmd} -s '{short_name}'{req_arg} -d '{desc}'")

    # Per-command options
    for cmd_name, subparser in subparser_choices.items():
        cmd_options     = extract_parser_options(subparser)
        cmd_positionals = extract_positional_choices(subparser)
        if (not cmd_options) and (not cmd_positionals):
            continue

        lines.extend(['', f'# Options for: {cmd_name}'])
        for opt in cmd_options:
            desc = opt.help.replace("'", "\\'") if opt.help else ''
            for flag in opt.flags:
                if flag.startswith('--'):
                    long_name = flag[2:]
                    req_arg   = ' -r' if opt.takes_value else ''
                    lines.append(
                        f"complete -c {cmd} -n '__fish_seen_subcommand_from {cmd_name}'"
                        f" -l '{long_name}'{req_arg} -d '{desc}'"
                    )
                elif flag.startswith('-') and (len(flag) == 2):
                    short_name = flag[1]
                    req_arg    = ' -r' if opt.takes_value else ''
                    lines.append(
                        f"complete -c {cmd} -n '__fish_seen_subcommand_from {cmd_name}'"
                        f" -s '{short_name}'{req_arg} -d '{desc}'"
                    )
        for pos_help, pos_choices in cmd_positionals:
            desc = pos_help.replace("'", "\\'") if pos_help else ''
            lines.append(
                f"complete -c {cmd} -n '__fish_seen_subcommand_from {cmd_name}'"
                f" -a '{' '.join(pos_choices)}' -d '{desc}'"
            )

    lines.append('')
    return '\n'.join(lines)


COMPLETION_GENERATORS: dict[SupportedShell, Callable[[argparse.ArgumentParser, CompletionConfig], str]] = {
    'bash': generate_bash_completions,
    'zsh':  generate_zsh_completions,
    'fish': generate_fish_completions,
}


def generate_completions(
    shell: SupportedShell,
    parser: argparse.ArgumentParser,
    *,
    command_name: str | None = None,
    script_path: str | None = None,
    project_name: str | None = None,
) -> str:
    """
    Generate a shell completion script for the given shell.

    :param shell: target shell (bash, zsh, or fish)
    :param parser: the fully built root argument parser
    :param command_name: command name for the completion function (defaults to "cli")
    :param script_path: display path to the script (for header comments)
    :param project_name: project name (for header comments)
    :raises ValueError: if *shell* is not a supported shell name
    :return: the complete shell completion script
    """
    generator = COMPLETION_GENERATORS.get(shell)
    if generator is None:
        raise ValueError(
            f'Unsupported shell: {shell!r}. '
            f'Supported shells: {", ".join(sorted(get_args(SupportedShell)))}'
        )

    return generator(
        parser,
        CompletionConfig(
            command_name=command_name or 'cli',
            script_path=script_path   or '',
            project_name=project_name or '',
        ),
    )


# ==============
# Auto-detection
# ==============


def import_module_from_path(script_path: Path) -> ModuleType:
    """
    Dynamically import a Python script as a module.

    :param script_path: path to the script file
    :raises FileNotFoundError: if the script does not exist
    :raises ImportError: if the script cannot be loaded
    :return: the imported module
    """
    if not script_path.is_file():
        raise FileNotFoundError(f'Script not found: {script_path}')

    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    if (spec is None) or (spec.loader is None):
        raise ImportError(f'Cannot load module spec from: {script_path}')

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def detect_parser(module: ModuleType) -> argparse.ArgumentParser:
    """
    Auto-detect an :class:`argparse.ArgumentParser` from a loaded module.

    Tries calling well-known factory functions first (``build_parser``, ``get_parser``, ``create_parser``,
    ``make_parser``, ``parser``), then falls back to searching for module-level ``ArgumentParser`` instances.

    :param module: the imported module to inspect
    :raises RuntimeError: if no parser can be detected
    :return: the detected argument parser
    """

    # Try well-known factory function names
    for name in PARSER_FACTORY_NAMES:
        attr = getattr(module, name, None)
        if not callable(attr):
            continue

        try:
            result = attr()
        except Exception:  # noqa: S112 — intentional: probing unknown callables during auto-detection
            continue
        if isinstance(result, argparse.ArgumentParser):
            return result

    # Fall back to module-level ArgumentParser instances
    for name in dir(module):
        if name.startswith('_'):
            continue
        attr = getattr(module, name, None)
        if isinstance(attr, argparse.ArgumentParser):
            return attr

    raise RuntimeError(
        f'Could not auto-detect an ArgumentParser in {module.__name__!r}. '
        f'Looked for factory functions ({", ".join(PARSER_FACTORY_NAMES)}) and module-level ArgumentParser instances. '
        f'Use --parser to specify the factory function name explicitly.'
    )


def resolve_parser(script_path: Path, *, parser_name: str | None = None) -> argparse.ArgumentParser:
    """
    Import a script and resolve its argument parser.

    When *parser_name* is provided, it is looked up as an attribute on the imported module and called (if callable).
    Otherwise, :func:`detect_parser` is used for auto-detection.

    :param script_path: path to the target script
    :param parser_name: optional name of a callable or attribute that provides the parser
    :raises RuntimeError: if the parser cannot be resolved
    :return: the resolved argument parser
    """
    module = import_module_from_path(script_path)

    if parser_name is not None:
        attr = getattr(module, parser_name, None)
        if attr is None:
            raise RuntimeError(f'Attribute {parser_name!r} not found in {script_path}')

        if callable(attr):
            result = attr()
            if not isinstance(result, argparse.ArgumentParser):
                raise RuntimeError(f'{parser_name}() returned {type(result).__name__}, expected ArgumentParser')
            return result

        if isinstance(attr, argparse.ArgumentParser):
            return attr

        raise RuntimeError(f'{parser_name!r} is {type(attr).__name__}, expected a callable or ArgumentParser instance')

    return detect_parser(module)


# ===============
# CLI entry point
# ===============


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` returned by :func:`parse_args`.
    """
    script:  Path               # first positional arg
    shell:   SupportedShell     # second positional arg
    parser:  str                # --parser
    name:    str                # --name
    project: str                # --project


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Parse command-line arguments.

    :param argv: argument list to parse, defaults to sys.argv[1:]
    :return: annotated namespace of parsed args (:class:`Args`)
    """
    parser = argparse.ArgumentParser(
        description='Generate shell completion scripts for argparse-based CLI tools.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        epilog='\n'.join([
            'examples:',
            '  %(prog)s scripts/maintain/update_prek.py zsh',
            '  %(prog)s scripts/maintain/update_prek.py bash --parser build_parser',
            '  %(prog)s scripts/maintain/update_prek.py fish --name update_prek',
        ]),
    )

    def add_positional_args() -> None:
        parser.add_argument(
            'script',
            type=Path,
            help='path to the target argparse-based script',
        )
        parser.add_argument(
            'shell',
            choices=get_args(SupportedShell),
            help=f'target shell ({", ".join(get_args(SupportedShell))})',
        )
    add_positional_args()

    def add_options() -> None:
        parser.add_argument(
            '--parser',
            metavar='NAME',
            default=None,
            help='name of the function or attribute that provides the ArgumentParser (auto-detected if omitted)',
        )
        parser.add_argument(
            '--name',
            metavar='CMD',
            default=None,
            help='command name for the completion script (defaults to the script filename)',
        )
        parser.add_argument(
            '--project',
            metavar='NAME',
            default=None,
            help='project name for header comments',
        )
        parser.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='show this help message and exit',
        )
    add_options()

    return parser.parse_args(argv, namespace=Args())


def main(argv: Sequence[str] | None = None) -> None:
    """
    CLI entry point for generating shell completions from an argparse-based script.

    :param argv: argument list to parse (defaults to ``sys.argv[1:]``)
    """
    args = parse_args(argv)
    try:
        parser = resolve_parser(args.script, parser_name=args.parser)
    except (FileNotFoundError, ImportError, RuntimeError) as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(1)
    else:
        print(
            generate_completions(
                args.shell,
                parser,
                command_name=args.name or args.script.name,
                script_path=str(args.script),
                project_name=args.project or '',
            )
        )


if __name__ == '__main__':
    main()
