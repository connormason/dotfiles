#!/usr/bin/env python3
"""
Programmatically install UV using the official installer script
"""
from __future__ import annotations

import argparse
import enum
import functools
import os
import platform
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from typing import Protocol
from typing import TypeVar
from typing import Union

# Configuration
MIN_PYTHON:           tuple[int, int] = (3, 8)   # Minimum supported python version. Script exits with error if not met
DOWNLOAD_TIMEOUT:     float           = 30.0     # Installer download timeout in seconds (default for --timeout)
DOWNLOAD_RETRIES:     int             = 3        # Maximum number of download retry attempts (default for --retries)
DOWNLOAD_RETRY_DELAY: float           = 2        # Initial delay in seconds between retries (default for --retry-delay)

# Reference URLs
DOCS_URL:               str = 'https://docs.astral.sh/uv/'
INSTALLATION_GUIDE_URL: str = 'https://docs.astral.sh/uv/getting-started/installation/'

# Global verbose flag
VERBOSE: bool = False


PathLike = Union[Path, str]

T_contra = TypeVar('T_contra', contravariant=True)

class SupportsWrite(Protocol[T_contra]):
    def write(self, s: T_contra, /) -> object: ...


class ExitCode(int, enum.Enum):
    """
    Script exit codes
    """
    SUCCESS              = 0
    ALREADY_INSTALLED    = 0
    INVALID_PARAMETERS   = 1
    DOWNLOAD_FAILED      = 2
    INSTALL_FAILED       = 3
    VERIFICATION_FAILED  = 4
    UNSUPPORTED_PLATFORM = 5
    PYTHON_VERSION       = 6


def vprint(*args: Any, **kwargs: Any) -> None:
    """
    Print only if verbose mode is enabled
    """
    if VERBOSE:
        print(*args, file=kwargs.pop('file', sys.stderr), **kwargs)


def indent(s: str, num: int) -> str:
    """
    Indent string by given number of spaces

    :param s: string to indent
    :param num: number of spaces to indent each line in string `s` with
    :return: indented string
    """
    return textwrap.indent(s, ' ' * num)


def check_python_version() -> bool:
    """
    Check minimum Python version requirement (:attr:`MAX_PYTHON` above)

    :return: True if minimum python version requirement met, False if not
    """
    if sys.version_info < MIN_PYTHON:
        print(
            f'❌ Error: '
            f'Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, '
            f'but you have Python {sys.version_info.major}.{sys.version_info.minor}',
            file=sys.stderr,
        )
        return False
    else:
        vprint(f'✅ Python version {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
        return True


def detect_shell() -> str | None:
    """
    Detect the user's shell

    :return: current shell
    """
    if shell := os.environ.get('SHELL', ''):
        return Path(shell).name
    else:
        return None


def get_shell_rc_file() -> Path | None:
    """
    Get the appropriate shell RC file path

    :return: path to shell RC file for current shell
    """
    shell = detect_shell()
    home  = Path.home()

    shell_rc_map: dict[str, Path] = {
        'bash': home / '.bashrc',
        'zsh':  home / '.zshrc',
        'fish': home / '.config' / 'fish' / 'config.fish',
        'tcsh': home / '.tcshrc',
        'csh':  home / '.cshrc',
    }

    # For macOS, bash uses .bash_profile instead of .bashrc
    if (shell == 'bash') and (platform.system() == 'Darwin'):
        bash_profile = home / '.bash_profile'
        if bash_profile.exists():
            return bash_profile

    return shell_rc_map.get(shell) if shell else None


def get_path_export_command(install_dir: Path) -> str | None:
    """
    Get the command to add directory to PATH based on shell

    :param install_dir: directory path
    :return: str shell command
    """
    shell = detect_shell()
    if shell in ('bash', 'zsh'):
        return f'export PATH="{install_dir}:$PATH"'
    elif shell == 'fish':
        return f'set -gx PATH "{install_dir}" $PATH'
    elif shell in ('tcsh', 'csh'):
        return f'setenv PATH "{install_dir}:$PATH"'
    else:
        return None


# TODO: support brew install location as well
# TODO: allow installation from current environment as well (from `pip install`)
def get_common_install_locations() -> list[Path]:
    """
    Get common installation locations for UV based on platform

    :return: list of filepaths (:class:`pathlib.Path`)
    """
    home   = Path.home()
    system = platform.system().lower()

    locations: list[Path] = []
    if system in ('linux', 'darwin'):
        locations = [
            home / '.cargo' / 'bin' / 'uv',
            home / '.local' / 'bin' / 'uv',
            Path('/usr/local/bin/uv'),
            Path('/usr/bin/uv'),
        ]
    elif system == 'windows':
        locations = [
            home / '.cargo' / 'bin' / 'uv.exe',
            home / '.local' / 'bin' / 'uv.exe',
            home / 'AppData' / 'Local' / 'uv' / 'uv.exe',
            Path('C:/Program Files/uv/uv.exe'),
        ]
    return locations


def find_executable(*, path_only: bool = False) -> tuple[str | None, str | None]:
    """
    Try to find the UV executable in common locations

    :param path_only: if True, only look for executable in PATH. If False, look for executable in other common locations
                      where UV might be installed
    :return: tuple (executable path, version)
    """

    # First check if it's in PATH
    try:
        result = subprocess.run(
            ['uv', '--version'],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    else:
        return 'uv', result.stdout.strip()

    # Check common installation locations
    if not path_only:
        for location in get_common_install_locations():
            if location.exists() and location.is_file():
                try:
                    result = subprocess.run(
                        [str(location), '--version'],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except (subprocess.CalledProcessError, PermissionError):
                    continue
                else:
                    return str(location), result.stdout.strip()

    return None, None


def is_installed(*, quiet: bool = False) -> bool:
    """
    Check if UV is already installed

    :param quiet: suppress console output if True
    :return: True if `uv` already installed, False if not
    """
    executable, version = find_executable()
    if executable:
        if not quiet:
            print(f'✅ UV is already installed: {version}')
            if executable != 'uv':
                print(f'   📍 Found at: {executable}')
                print('   💡 Note: Consider adding this location to your PATH')
        return True
    else:
        return False


def get_installer_url() -> str:
    """
    Get the appropriate UV installer URL based on the platform

    :raises OSError: if current platform/operating system is not supported
    :return: installer URL
    """
    system = platform.system().lower()
    if system in ('linux', 'darwin'):
        return 'https://astral.sh/uv/install.sh'
    elif system == 'windows':
        return 'https://astral.sh/uv/install.ps1'
    else:
        raise OSError(f'Unsupported operating system: {system}')


def download_installer(
    url: str,
    dest: PathLike,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
    retries: int = DOWNLOAD_RETRIES,
    retry_delay: float = DOWNLOAD_RETRY_DELAY,
) -> bool:
    """
    Download the installer script with retry logic

    :param url: installer URL
    :param dest: where to download installer to
    :param timeout: download timeout in seconds
    :param retries: maximum number of download retry attempts
    :param retry_delay: initial delay in seconds between retries, before exponential backoff
    :return: True if successful, False if not
    """
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                delay = retry_delay * (2 ** (attempt - 2))      # Exponential backoff
                print(f'⏱️  Retrying in {delay} seconds... (attempt {attempt}/{retries})')
                time.sleep(delay)

            print(f'⏬ Downloading installer from {url}...')
            vprint(f'   Attempt {attempt}/{retries}')

            with urllib.request.urlopen(url, timeout=timeout) as response:
                content = response.read()
            with Path(dest).expanduser().open('wb') as f:
                f.write(content)

        except urllib.error.URLError as e:
            print(f'❌ Download failed: {e}', file=sys.stderr)
            if attempt == retries:
                print('',                                                   file=sys.stderr)
                print('🔧 Troubleshooting:',                                file=sys.stderr)
                print('   1. Check your internet connection',               file=sys.stderr)
                print('   2. Verify you can access https://astral.sh',      file=sys.stderr)
                print('   3. Check if a proxy is required in your network', file=sys.stderr)
                return False

        except Exception as e:
            print(f'❌ Unexpected error during download: {e}', file=sys.stderr)
            if attempt == retries:
                return False

        else:
            print(f'✅ Downloaded to {dest}')
            return True

    return False


def run_installer_unix(installer_path: PathLike) -> bool:
    """
    Execute the UV installer script on Unix-like systems

    :param installer_path: path to installer script
    :return: True on success, False on failure
    """
    print('💿 Running UV installer...')
    try:
        result = subprocess.run(
            ['sh', str(installer_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f'❌ Installation failed: {e}', file=sys.stderr)
        print(indent(e.stderr, 3),            file=sys.stderr)
        return False
    else:
        print(indent(result.stdout, 3))
        if result.stderr:
            print(indent(result.stderr, 3))
        return True


def run_installer_windows(installer_path: PathLike) -> bool:
    """
    Execute the UV installer script on Windows

    :param installer_path: path to installer script
    :return: True on success, False on failure
    """
    print('💿 Running UV installer...')
    try:
        result = subprocess.run(
            ['powershell', '-ExecutionPolicy', 'Bypass', '-File', str(installer_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f'❌ Installation failed: {e}', file=sys.stderr)
        print(indent(e.stderr, 3),            file=sys.stderr)
        return False
    else:
        print(indent(result.stdout, 3))
        if result.stderr:
            print(indent(result.stderr, 3))
        return True


def run_installer(installer_path: PathLike) -> bool:
    """
    Execute the UV installer script based on platform

    :param installer_path: path to installer script
    :return: True on success, False on failure
    """
    system = platform.system().lower()
    if system in ('linux', 'darwin'):
        return run_installer_unix(installer_path)
    elif system == 'windows':
        return run_installer_windows(installer_path)
    else:
        print(f'❌ Unsupported platform: {system}', file=sys.stderr)
        return False


def verify_installation() -> bool:
    """
    Verify that UV was installed successfully. Provides detailed guidance if tool is installed but not in PATH

    :return: True on success, False on failure
    """
    print('')
    print('🔍 Verifying installation...')
    vprint('Checking all known installation locations...')

    # Use find_executable to check all locations
    executable, version = find_executable()
    if not executable:
        print('❌ UV installation could not be verified\n',         file=sys.stderr)
        print('🔧 Troubleshooting:',                                file=sys.stderr)
        print('   1. Close and reopen your terminal',               file=sys.stderr)
        print('   2. Try running the installer again with --force', file=sys.stderr)
        print('   3. Check the official UV installation guide:',    file=sys.stderr)
        print(f'      {INSTALLATION_GUIDE_URL}',                    file=sys.stderr)
        return False

    # Tool found!
    print(f'✅ UV installed successfully: {version}')

    # Check if it's in PATH
    if executable == 'uv':
        print('✅ UV is in your PATH and ready to use')
        vprint(f'   Executable: {executable}')
        return True

    # Tool is installed but not in PATH
    else:
        print(f'📍 Found at: {executable}\n')
        print('⚠️  UV is installed but not in your PATH')

        install_dir = Path(executable).parent
        shell       = detect_shell()
        rc_file     = get_shell_rc_file()
        export_cmd  = get_path_export_command(install_dir)

        print('')
        print('💡 To make UV available globally, add it to your PATH:\n')
        if rc_file and export_cmd and shell:
            print(f'   For {shell}, add this line to {rc_file}:')
            print(f'   {export_cmd}\n')
            print('   Then run:')
            print(f'   source {rc_file}')
        else:
            print(f'   Add {install_dir} to your PATH environment variable')
            print("   Consult your shell's documentation for instructions")

        print('')
        print(f'   Or use the full path: {executable}')

        # Still consider this a success since the tool is installed
        return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Build parser and parse command-line arguments

    :param argv: argument list of parse, defaults to ``sys.argv[1:]``
    :return: :class:`argparse.Namespace` with parsed argument values
    """
    global VERBOSE

    # Build argument parser
    parser = argparse.ArgumentParser(
        description='Install UV package manager using official installer script',
        formatter_class=functools.partial(
            argparse.RawDescriptionHelpFormatter,
            max_help_position=50,
        ),
        epilog='\n'.join([
            'Examples:',
            '',
            '  %(prog)s                              # Normal installation',
            '  %(prog)s --force                      # Force reinstall even if present',
            '  %(prog)s --verbose                    # Show detailed progress',
            '  %(prog)s --force -v                   # Force reinstall with verbose output',
            '  %(prog)s --retries 5                  # Increase download retry attempts to 5',
            '  %(prog)s --retry-delay 3              # Set initial retry delay to 3 seconds',
            '  %(prog)s --retries 5 --retry-delay 3  # Custom retry configuration',
        ]),
        add_help=False,
    )

    execution_opts = parser.add_argument_group('Execution options')
    execution_opts.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='Force installation even if UV is already installed',
    )
    execution_opts.add_argument(
        '-e',
        '--ensure',
        action='store_true',
        help='Install UV if it does not exist, otherwise quietly exit with no console output',
    )

    download_opts = parser.add_argument_group('Download options')
    download_opts.add_argument(
        '-t',
        '--timeout',
        type=float,
        default=DOWNLOAD_TIMEOUT,
        metavar='SECONDS',
        help=f'Download timeout in seconds (default: {DOWNLOAD_TIMEOUT})',
    )
    download_opts.add_argument(
        '-r',
        '--retries',
        type=int,
        default=DOWNLOAD_RETRIES,
        metavar='N',
        help=f'Maximum number of download retry attempts (default: {DOWNLOAD_RETRIES})',
    )
    download_opts.add_argument(
        '--retry-delay',
        type=float,
        default=DOWNLOAD_RETRY_DELAY,
        metavar='SECONDS',
        help=f'Initial delay in seconds between retries, uses exponential backoff (default: {DOWNLOAD_RETRY_DELAY})',
    )

    logging_opts = parser.add_argument_group('Logging options')
    logging_opts.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Enable verbose output for debugging',
    )

    other_opts = parser.add_argument_group('Other options')
    other_opts.add_argument(
        '-h',
        '--help',
        action='help',
        default=argparse.SUPPRESS,
        help='Show this help message and exit',
    )

    # Parse arguments
    args = parser.parse_args(argv)

    # Set global config variables with parsed command-line option values
    VERBOSE = args.verbose

    # Validate download parameters
    if args.timeout < 0:
        print('❌ Error: --timeout cannot be negative',     file=sys.stderr)
        sys.exit(ExitCode.INVALID_PARAMETERS)
    if args.retries < 1:
        print('❌ Error: --retries must be at least 1',     file=sys.stderr)
        sys.exit(ExitCode.INVALID_PARAMETERS)
    if args.retry_delay < 0:
        print('❌ Error: --retry-delay cannot be negative', file=sys.stderr)
        sys.exit(ExitCode.INVALID_PARAMETERS)

    # Enforce mutual exclusivity of --force and --ensure
    # Using ``add_mutually_exclusive_group()`` prevents us from adding a help text title to the execution options group
    if args.force and args.ensure:
        print('❌ Error: --force and --ensure are mutually exclusive', file=sys.stderr)
        sys.exit(ExitCode.INVALID_PARAMETERS)

    return args


def main(argv: list[str] | None = None) -> None:
    """
    Programmatically install UV using the official installer script

    :param argv: argument list of parse, defaults to ``sys.argv[1:]``
    """

    # Parse command-line arguments
    args = parse_args(argv=argv)

    if args.verbose or not args.ensure:
        print('╔════════════════════════════╗')
        print('║   UV Installation Script   ║')
        print('╚════════════════════════════╝')
        print()
        vprint(f'Download retry configuration: {args.retries} attempts, {args.retry_delay}s initial delay\n')

    # Check Python version
    if not check_python_version():
        sys.exit(ExitCode.PYTHON_VERSION)

    # Check if already installed (unless --force is specified)
    if not args.force:
        if is_installed(quiet=args.ensure and not args.verbose):
            if not args.ensure:
                print('⏭️ Skipping installation\n')
                print('💡 Tip: Use --force to reinstall')
            sys.exit(ExitCode.ALREADY_INSTALLED)
    else:
        print('🔄 --force specified, proceeding with installation...\n')

    # Get installer URL
    try:
        url = get_installer_url()
        vprint(f'Installer URL: {url}')
    except OSError as e:
        print(f'❌ Error: {e}', file=sys.stderr)
        sys.exit(ExitCode.UNSUPPORTED_PLATFORM)

    # Determine installer file extension
    system         = platform.system().lower()
    extension      = '.ps1' if system == 'windows' else '.sh'
    installer_path = Path.home() / f'.uv_installer{extension}'
    vprint(f'Temporary installer path: {installer_path}')

    # Download installer
    if not download_installer(
        url,
        installer_path,
        timeout=args.timeout,
        retries=args.retries,
        retry_delay=args.retry_delay,
    ):
        sys.exit(ExitCode.DOWNLOAD_FAILED)

    # Run the installer
    print()
    if not run_installer(installer_path):
        installer_path.unlink(missing_ok=True)
        sys.exit(ExitCode.INSTALL_FAILED)

    # Clean up installer
    vprint(f'Cleaning up {installer_path}')
    installer_path.unlink(missing_ok=True)

    # Verify installation
    if not verify_installation():
        sys.exit(ExitCode.VERIFICATION_FAILED)

    print('')
    print('🎉 Installation complete!\n')
    print('📋 Next steps:')
    print('   1. Close and reopen your terminal (or run: source ~/.bashrc)')
    print('   2. Verify with: uv --version')
    print(f'   3. View documentation: {DOCS_URL}')
    sys.exit(ExitCode.SUCCESS)


if __name__ == '__main__':
    main()
