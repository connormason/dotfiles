#!/usr/bin/env python3
"""
Standalone dotenv file parser and environment variable loader

Parses .env files and outputs values in JSON, shell export, or key-value pair format

Zero external dependencies — uses only Python standard library

Parser logic vendored from ezcli.dotenv v1.6.13.

Usage::

    python3 loadenv_standalone.py [--json|--export|--pairs] [--override] [--no-interpolate] [-q] [FILE]

"""
from __future__ import annotations

import abc
import argparse
import codecs
import json
import os
import re
import sys
from pathlib import Path
from typing import IO
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Literal as LiteralStr
from typing import NamedTuple
from typing import Union

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator
    from collections.abc import Mapping
    from collections.abc import Sequence

__version__ = '1.0.0'


PathLike = Union[str, Path]


class Error(Exception):
    """
    Parsing error raised when a regex match or read operation fails within the :class:`Reader`
    """
    ...


# =======
# Regexes
# =======

_newline              = re.compile(r'(\r\n|\n|\r)',               re.UNICODE)
_multiline_whitespace = re.compile(r'\s*',                        re.UNICODE | re.MULTILINE)
_whitespace           = re.compile(r'[^\S\r\n]*',                 re.UNICODE)
_export               = re.compile(r'(?:export[^\S\r\n]+)?',      re.UNICODE)
_single_quoted_key    = re.compile(r"'([^']+)'",                  re.UNICODE)
_unquoted_key         = re.compile(r'([^=\#\s]+)',                re.UNICODE)
_equal_sign           = re.compile(r'(=[^\S\r\n]*)',              re.UNICODE)
_single_quoted_value  = re.compile(r"'((?:\\'|[^'])*)'",          re.UNICODE)
_double_quoted_value  = re.compile(r'"((?:\\"|[^"])*)"',          re.UNICODE)
_unquoted_value       = re.compile(r'([^\r\n]*)',                 re.UNICODE)
_comment              = re.compile(r'(?:[^\S\r\n]*#[^\r\n]*)?',   re.UNICODE)
_end_of_line          = re.compile(r'[^\S\r\n]*(?:\r\n|\n|\r|$)', re.UNICODE)
_rest_of_line         = re.compile(r'[^\r\n]*(?:\r|\n|\r\n)?',    re.UNICODE)
_double_quote_escapes = re.compile(r"\\[\\'\"abfnrtv]",           re.UNICODE)
_single_quote_escapes = re.compile(r"\\[\\']",                    re.UNICODE)

_posix_variable = re.compile(
    r"""
    \$\{
        (?P<name>[^\}:]*)
        (?::-
            (?P<default>[^\}]*)
        )?
    \}
    """,
    re.VERBOSE,
)


# =======
# Parsing
# =======


class Original(NamedTuple):
    """
    The original text of a parsed line and its starting line number

    Preserves the raw string content so that lines can be rewritten verbatim when modifying a `.env` file
    """
    string: str
    line:   int


class Binding(NamedTuple):
    """
    A single parsed key-value binding from a `.env` file

    Represents one logical line of a dotenv file after parsing. Lines that could not be parsed have `error=True`
    with `key` and `value` set to `None`
    """
    key:      str | None
    value:    str | None
    original: Original
    error:    bool


class Position:
    """
    Tracks the current character offset and line number within a dotenv source string

    Used by :class:`Reader` to maintain cursor state as the parser advances through the input

    :param chars: character offset in line
    :param line: line number
    """
    def __init__(self, chars: int, line: int) -> None:
        self.chars = chars
        self.line  = line

    @classmethod
    def start(cls) -> Position:
        """
        Create a position representing the beginning of a source string

        :return: a new :class:`Position` at character 0, line 1
        """
        return cls(chars=0, line=1)

    def set(self, other: Position) -> None:
        """
        Copy the character offset and line number from another position

        :param other: the position to copy from
        """
        self.chars = other.chars
        self.line  = other.line

    def advance(self, string: str) -> None:
        """
        Advance the position by the length of the given string, counting newlines

        :param string: the text that was consumed from the source
        """
        self.chars += len(string)
        self.line  += len(re.findall(_newline, string))


class Reader:
    """
    Buffered reader that tokenizes a dotenv source string using regex-based pattern matching

    Reads the entire stream into memory, then provides methods to consume characters and match regex patterns while
    tracking the current :class:`Position`. Supports marking regions of text so that the original raw content can be
    captured as :class:`Original` instances

    :param stream: stream to read into memory (`.env` file stream)
    """
    def __init__(self, stream: IO[str]) -> None:
        self.string   = stream.read()
        self.position = Position.start()
        self.mark     = Position.start()

    def has_next(self) -> bool:
        """
        Check if there are remaining characters to read

        :return: ``True`` if the cursor has not reached the end of the string
        """
        return self.position.chars < len(self.string)

    def set_mark(self) -> None:
        """
        Save the current position as a mark for later retrieval via :meth:`get_marked`
        """
        self.mark.set(self.position)

    def get_marked(self) -> Original:
        """
        Return the text between the last mark and the current position as an :class:`Original`

        :return: the raw substring and starting line number since :meth:`set_mark` was last called
        """
        return Original(
            string=self.string[self.mark.chars:self.position.chars],
            line=self.mark.line,
        )

    def peek(self, count: int) -> str:
        """
        Return upcoming characters without advancing the position

        :param count: number of characters to peek at
        :return: up to `count` characters from the current position
        """
        return self.string[self.position.chars:self.position.chars + count]

    def read(self, count: int) -> str:
        """
        Consume and return the next `count` characters, advancing the position

        :param count: number of characters to read
        :raises Error: if fewer than `count` characters remain
        :return: the consumed characters
        """
        result = self.string[self.position.chars:self.position.chars + count]
        if len(result) < count:
            raise Error('read: End of string')
        self.position.advance(result)
        return result

    def read_regex(self, regex: re.Pattern[str]) -> Sequence[str]:
        """
        Match a regex at the current position, consume the matched text, and return capture groups

        :param regex: compiled regex pattern to match at the current cursor position
        :raises Error: if the pattern does not match at the current position
        :return: tuple of captured groups from the match
        """
        match = regex.match(self.string, self.position.chars)
        if match is None:
            raise Error('read_regex: Pattern not found')
        self.position.advance(self.string[match.start():match.end()])
        return match.groups()


def parse_key(reader: Reader) -> str | None:
    """
    Parse a dotenv key from the current reader position

    Handles both single-quoted keys (e.g. ``"MY KEY"``) and unquoted keys. Lines starting with "#" are treated as
    comments and return `None`

    :param reader: the :class:`Reader` positioned at the start of a key
    :return: the parsed key string, or `None` if the line is a comment
    """
    char = reader.peek(1)
    if char == '#':
        return None
    elif char == "'":
        key, *_ = reader.read_regex(_single_quoted_key)
    else:
        key, *_ = reader.read_regex(_unquoted_key)
    return key


def parse_value(reader: Reader) -> str:
    """
    Parse a dotenv value from the current reader position

    Handles single-quoted values (with ``\\'`` escapes), double-quoted values (with standard backslash escapes),
    unquoted values (trimming inline comments and trailing whitespace), and empty values

    :param reader: the :class:`Reader` positioned at the start of a value (after the "=")
    :return: the parsed and unescaped value string
    """
    def decode_escapes(regex: re.Pattern[str], string: str) -> str:
        def decode_match(match: re.Match[str]) -> str:
            return codecs.decode(match.group(0), 'unicode-escape')
        return regex.sub(decode_match, string)

    char = reader.peek(1)
    if char == "'":
        value, *_ = reader.read_regex(_single_quoted_value)
        return decode_escapes(_single_quote_escapes, value)
    elif char == '"':
        value, *_ = reader.read_regex(_double_quoted_value)
        return decode_escapes(_double_quote_escapes, value)
    elif char in ('', '\n', '\r'):
        return ''
    else:
        part, *_ = reader.read_regex(_unquoted_value)
        return re.sub(r'\s+#.*', '', part).rstrip()


def parse_binding(reader: Reader) -> Binding:
    """
    Parse a single key-value binding from the current reader position

    Consumes one logical line of dotenv content including leading whitespace, optional ``export`` prefix, key,
    equals sign, value, inline comment, and line ending. If parsing fails, the remainder of the line is consumed
    and an error :class:`Binding` is returned

    :param reader: the :class:`Reader` positioned at the start of a binding line
    :return: a :class:`Binding` with the parsed key/value or `error=True` if the line could not be parsed
    """
    reader.set_mark()
    try:
        reader.read_regex(_multiline_whitespace)
        if not reader.has_next():
            return Binding(
                key=None,
                value=None,
                original=reader.get_marked(),
                error=False,
            )

        reader.read_regex(_export)
        key = parse_key(reader)
        reader.read_regex(_whitespace)

        value: str | None = None
        if reader.peek(1) == '=':
            reader.read_regex(_equal_sign)
            value = parse_value(reader)

        reader.read_regex(_comment)
        reader.read_regex(_end_of_line)
        return Binding(
            key=key,
            value=value,
            original=reader.get_marked(),
            error=False,
        )

    except Error:
        reader.read_regex(_rest_of_line)
        return Binding(
            key=None,
            value=None,
            original=reader.get_marked(),
            error=True,
        )


def parse_stream(stream: IO[str]) -> Iterator[Binding]:
    """
    Parse an entire dotenv stream into a sequence of :class:`Binding` objects

    Reads the stream and yields one :class:`Binding` per logical line until all content has been consumed

    :param stream: a text stream (e.g. an open file or :class:`io.StringIO`) containing dotenv content
    :yields: :class:`Binding` objects representing each line
    """
    reader = Reader(stream)
    while reader.has_next():
        yield parse_binding(reader)


# ===============
# Variables (AST)
# ===============


class Atom(metaclass=abc.ABCMeta):
    """
    Abstract base class for parsed components of a dotenv value string

    Each atom represents either a literal text segment or a variable reference that can be resolved against an
    environment mapping
    """
    def __ne__(self, other: Any) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return NotImplemented
        return not result

    @abc.abstractmethod
    def resolve(self, env: Mapping[str, str | None]) -> str:
        """
        Resolve this atom to a concrete string value

        :param env: environment mapping of variable names to their values
        :return: the resolved string value
        """
        raise NotImplementedError


class Literal(Atom):
    """
    A literal text segment within a dotenv value

    Represents a portion of a value string that contains no variable references and resolves to its stored text
    verbatim

    :param value: literal text value
    """
    def __init__(self, value: str) -> None:
        self.value = value

    def __repr__(self) -> str:
        return f'Literal(value={self.value})'

    def __hash__(self) -> int:
        return hash((self.__class__, self.value))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self.value == other.value
        else:
            return NotImplemented

    def resolve(self, env: Mapping[str, str | None]) -> str:
        """
        Return the literal value unchanged

        :param env: environment mapping (unused for literal)
        :return: the stored literal text
        """
        return self.value


class Variable(Atom):
    """
    A POSIX-style variable reference within a dotenv value

    Represents a ``${NAME}`` or ``${NAME:-default}`` reference that resolves by looking up the variable name in the
    provided environment mapping, falling back to the default value when the variable is not found

    :param name: variable name
    :param default: default value to use when variable value is not found
    """
    def __init__(self, name: str, default: str | None) -> None:
        self.name    = name
        self.default = default

    def __repr__(self) -> str:
        return f'Variable(name={self.name}, default={self.default})'

    def __hash__(self) -> int:
        return hash((self.__class__, self.name, self.default))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return (self.name, self.default) == (other.name, other.default)
        else:
            return NotImplemented

    def resolve(self, env: Mapping[str, str | None]) -> str:
        """
        Resolve the variable reference against the given environment

        Looks up :attr:`name` in `env`. If not found, or the value is `None`, falls back to :attr:`default`
        (or an empty string if no default was specified)

        :param env: environment mapping of variable names to their values
        :return: the resolved value from the environment, the default, or an empty string
        """
        default = self.default if self.default is not None else ''
        result  = env.get(self.name, default)
        return result if result is not None else ''


def parse_variables(value: str) -> Iterator[Atom]:
    """
    Parse a dotenv value string into a sequence of :class:`Atom` nodes

    Scans for POSIX-style ``${NAME}`` and ``${NAME:-default}`` variable references, yielding :class:`Variable` nodes
    for each match and :class:`Literal` nodes for the text between them

    :param value: the raw value string to parse
    :yields: :class:`Literal` and :class:`Variable` atoms
    """
    cursor = 0
    for match in _posix_variable.finditer(value):
        (start, end) = match.span()
        name    = match['name']
        default = match['default']
        if start > cursor:
            yield Literal(value=value[cursor:start])

        yield Variable(name=name, default=default)
        cursor = end

    length = len(value)
    if cursor < length:
        yield Literal(value=value[cursor:length])


# ==========
# Resolution
# ==========


def resolve_variables(values: Iterable[tuple[str, str | None]], override: bool) -> Mapping[str, str | None]:
    """
    Resolve ``${VAR}``-style variable references across a sequence of key-value pairs

    Processes values in order, building up a mapping of resolved names. Each value's variable references are resolved
    against the combination of previously resolved values and :attr:`os.environ`.

    When `override=True`,  :attr:`os.environ` takes lower precedence than already-resolved dotenv values.
    When `override=False`, :attr:`os.environ` values take priority

    :param values: iterable of ``(key, value)`` tuples with unresolved variable references
    :param override: if True, dotenv values take precedence over :attr:`os.environ` for interpolation
    :return: ordered mapping of keys to their fully resolved values
    """
    new_values: dict[str, str | None] = {}
    for name, value in values:
        if value is None:
            result = None
        else:
            atoms = parse_variables(value)

            env: dict[str, str | None] = {}
            if override:
                env.update(os.environ)
                env.update(new_values)
            else:
                env.update(new_values)
                env.update(os.environ)
            result = ''.join(atom.resolve(env) for atom in atoms)

        new_values[name] = result

    return new_values


def _walk_to_root(path: PathLike) -> Iterator[Path]:
    """
    Yield directories starting from the given path up to the filesystem root

    If `path` points to a file, iteration begins from its parent directory. Each iteration yields the next parent
    directory until the root is reached

    :param path: starting file or directory path
    :raises OSError: if `path` does not exist
    :yields: :class:`~pathlib.Path` objects from `path` up to the root
    """
    _path = Path(path)
    if not _path.exists():
        raise OSError('Starting path not found')
    if _path.is_file():
        _path = _path.parent

    last_dir:    Path | None = None
    current_dir: Path        = _path.absolute()

    while last_dir != current_dir:
        yield current_dir
        parent_dir = Path(current_dir / os.path.pardir).resolve()
        last_dir, current_dir = current_dir, Path(parent_dir)


def find_dotenv(filename: str = '.env', *, raise_error_if_not_found: bool = False) -> str:
    """
    Search from CWD upward for the given dotenv file

    :param filename: the dotenv filename to search for
    :param raise_error_if_not_found: whether to raise :class:`OSError` if the file is not found
    :return: the absolute path to the file if found, or an empty string otherwise
    """
    for dir_path in _walk_to_root(Path.cwd()):
        check_path = dir_path / filename
        if check_path.is_file():
            return str(check_path)

    if raise_error_if_not_found:
        raise OSError('File not found')
    return ''


def dotenv_values(
    dotenv_path: PathLike,
    *,
    interpolate: bool = True,
    override: bool = False,
    encoding: str = 'utf-8',
    quiet: bool = False,
) -> tuple[dict[str, str | None], bool]:
    """
    Parse a .env file and return (values_dict, has_errors)

    :param dotenv_path: absolute or relative path to the `.env` file
    :param interpolate: whether to resolve ``${VAR}``-style variable references in values
    :param override: whether to override existing system environment variables with values from the `.env` file
    :param encoding: character encoding for reading the file
    :param quiet: suppress warning and error output
    """
    path = Path(dotenv_path)
    if not path.is_file():
        return {}, False

    has_errors: bool = False

    raw_values: list[tuple[str, str | None]] = []
    with path.open(encoding=encoding) as stream:
        for binding in parse_stream(stream):
            if binding.error:
                has_errors = True
                if not quiet:
                    print(f'Warning: could not parse statement at line {binding.original.line}', file=sys.stderr)
            elif binding.key is not None:
                raw_values.append((binding.key, binding.value))

    if interpolate:
        return dict(resolve_variables(raw_values, override=override)), has_errors
    else:
        return dict(raw_values), has_errors


# =================
# Output formatting
# =================


OutputFormat = LiteralStr['json', 'export', 'pairs']


def _shell_escape(value: str) -> str:
    """
    Escape a value for safe use inside double-quoted shell strings
    """
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('$', '\\$')
    value = value.replace('`', '\\`')
    return value


def format_json(values: dict[str, str | None], **kwargs: Any) -> str:
    """
    Format parsed values as a JSON object
    """
    return json.dumps(
        values,
        indent=kwargs.pop('indent', 2),
        ensure_ascii=kwargs.pop('ensure_ascii', False),
    )


def format_export(values: dict[str, str | None]) -> str:
    """
    Format parsed values as shell export statements
    """
    lines: list[str] = [
        f'export {key}="{_shell_escape(val)}"' for key, val in values.items()
        if val is not None
    ]
    return '\n'.join(lines) + '\n' if lines else ''


def format_pairs(values: dict[str, str | None]) -> str:
    """
    Format parsed values as KEY=value pairs
    """
    lines: list[str] = [
        key if val is None else f'{key}={val}' for key, val in values.items()
    ]
    return '\n'.join(lines) + '\n' if lines else ''


OUTPUT_FORMATTERS: dict[OutputFormat, Callable[[dict[str, str | None]], str]] = {
    'json':   format_json,
    'export': format_export,
    'pairs':  format_pairs,
}


# ============================================
# Argument parsing and core script entry point
# ============================================


class Args(argparse.Namespace):
    """
    Annotated :class:`argparse.Namespace` for script command-line arguments, returned by :func:`parse_args`
    """
    file:           Path | None     # positional script arg
    mode:           OutputFormat    # --json/--export/--pairs
    override:       bool            # --override
    no_interpolate: bool            # --no-interpolate
    quiet:          bool            # --quiet


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """
    Parse command-line arguments

    :param argv: argument list to parse, defaults to sys.argv[1:]
    :return: parsed namespace (:class:`Args`)
    """
    parser = argparse.ArgumentParser(
        description='Parse .env files and output as JSON, shell exports, or key-value pairs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'examples:\n'
            '  %(prog)s .env                       Output as JSON (default)\n'
            '  %(prog)s --export .env              Output as shell export statements\n'
            '  %(prog)s --pairs .env               Output as KEY=value pairs\n'
            '  eval "$(%(prog)s --export .env)"    Source into current shell\n'
        ),
        add_help=False
    )

    def add_positional_args() -> None:
        parser.add_argument(
            'file',
            nargs='?',
            default=None,
            type=Path,
            metavar='FILE',
            help='path to .env file (default: auto-discover from current working directory)',
        )

    def add_mode_opts() -> None:
        mode_opts = parser.add_argument_group('output format options')
        mode_opts.add_argument(
            '-j',
            '--json',
            dest='mode',
            action='store_const',
            const='json',
            default='json',
            help='output as JSON object (default)',
        )
        mode_opts.add_argument(
            '-e',
            '--export',
            dest='mode',
            action='store_const',
            const='export',
            help='output as export KEY="value" statements',
        )
        mode_opts.add_argument(
            '-p',
            '--pairs',
            dest='mode',
            action='store_const',
            const='pairs',
            help='output as KEY=value pairs',
        )

    def add_resolution_opts() -> None:
        resolution_opts = parser.add_argument_group('variable resolution options')
        resolution_opts.add_argument(
            '--override',
            action='store_true',
            default=False,
            help='.env values override existing env vars during interpolation',
        )
        resolution_opts.add_argument(
            '--no-interpolate',
            dest='interpolate',
            action='store_false',
            default=True,
            help='disable ${VAR} variable expansion',
        )

    def add_other_opts() -> None:
        other_opts = parser.add_argument_group('other options')
        other_opts.add_argument(
            '-q',
            '--quiet',
            action='store_true',
            default=False,
            help='suppress warnings and errors to stderr',
        )
        other_opts.add_argument(
            '-v',
            '--version',
            action='version',
            version=f'%(prog)s {__version__}',
            help='show script version and exit'
        )
        other_opts.add_argument(
            '-h',
            '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='show this help message and exit',
        )

    add_positional_args()
    add_mode_opts()
    add_resolution_opts()
    add_other_opts()

    return parser.parse_args(argv, namespace=Args())


def main(argv: Sequence[str] | None = None) -> int:
    """
    Standalone dotenv file parser and environment variable loader

    Parses .env files and outputs values in JSON, shell export, or key-value pair format

    :param argv: argument list to parse, defaults to sys.argv[1:]
    :return: int script exit code
    """
    args = parse_args(argv)

    # Resolve file path
    dotenv_path: Path
    if args.file is not None:
        dotenv_path = Path(args.file)
        if not dotenv_path.is_file():
            if not args.quiet:
                print(f'Error: file not found: {dotenv_path}', file=sys.stderr)
            return 1
    elif dotenv := find_dotenv():
        dotenv_path = Path(dotenv)
    else:
        if not args.quiet:
            print('Error: no .env file found (searched from current working directory upward)', file=sys.stderr)
        return 1

    # Parse
    values, has_errors = dotenv_values(
        dotenv_path,
        interpolate=args.interpolate,
        override=args.override,
        quiet=args.quiet,
    )

    # Format and output
    formatter = OUTPUT_FORMATTERS[args.mode]
    if output := formatter(values):
        sys.stdout.write(output)
        if not output.endswith('\n'):
            sys.stdout.write('\n')

    return 2 if has_errors else 0


if __name__ == '__main__':
    sys.exit(main())
