#!/usr/bin/env python3
"""
Programmatically install Hatch using the official installer script
"""
from __future__ import annotations

import argparse
import enum
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from typing import Union

# Configuration
MIN_PYTHON:          tuple[int, int] = (3, 8)
DOWNLOAD_RETRIES:    int             = 3
RETRY_DELAY_SECONDS: int             = 2

# Global verbose flag
VERBOSE: bool = False


PathLike = Union[Path, str]


class ExitCode(int, enum.Enum):
    """
    Script exit codes
    """
    SUCCESS              = 0
    ALREADY_INSTALLED    = 0
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
        print(*args, **kwargs)


def check_python_version() -> bool:
    """
    Check if Python version is 3.8+
    """
    if sys.version_info < MIN_PYTHON:
        print(
            f'❌ Error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, '
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
    shell = os.environ.get('SHELL', '')
    if shell:
        return Path(shell).name
    return None


def get_shell_rc_file() -> Path | None:
    """
    Get the appropriate shell RC file path

    :return: path to shell RC file for current shell
    """
    shell = detect_shell()
    if shell is None:
        return None

    home = Path.home()
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

    return shell_rc_map.get(shell)


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


def get_installer_url() -> str:
    """
    Get the appropriate Hatch installer URL based on the platform

    :raises OSError: if current platform/operating system is not supported
    :return: installer URL
    """
    system = platform.system().lower()
    if system in ('linux', 'darwin'):
        return 'https://github.com/pypa/hatch/releases/latest/download/hatch-universal-installer.py'
    else:
        raise OSError(f'Unsupported operating system: {system}')


def get_common_install_locations() -> list[Path]:
    """
    Get common installation locations for Hatch based on platform

    :return: list of filepaths
    """
    home   = Path.home()
    system = platform.system().lower()

    locations: list[Path] = []
    if system in ('linux', 'darwin'):
        locations = [
            home / '.local' / 'bin' / 'hatch',
            home / '.cargo' / 'bin' / 'hatch',
            Path('/usr/local/bin/hatch'),
            Path('/usr/bin/hatch'),
            home / '.hatch' / 'bin' / 'hatch',
        ]
    return locations


def find_executable() -> tuple[str | None, str | None]:
    """
    Try to find the Hatch executable in common locations

    :return: tuple (executable path, version)
    """

    # First check if it's in PATH
    try:
        result = subprocess.run(
            ['hatch', '--version'],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    else:
        return 'hatch', result.stdout.strip()

    # Check common installation locations
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


def is_installed() -> bool:
    """
    Check if Hatch is already installed

    :return: True if `hatch` already installed, False if not
    """
    executable, version = find_executable()
    if executable:
        print(f'✅ Hatch is already installed: {version}')
        if executable != 'hatch':
            print(f'  📍 Found at: {executable}')
            print('  💡 Note: Consider adding this location to your PATH')
        return True
    return False


def download_installer(url: str, dest: PathLike, *, timeout: int = 30) -> bool:
    """
    Download the installer script with retry logic

    :param url: installer URL
    :param dest: where to download installer to
    :param timeout: download timeout in seconds
    :return: True if successful, False if not
    """
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            if attempt > 1:
                delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 2))      # Exponential backoff
                print(f'⏱️  Retrying in {delay} seconds... (attempt {attempt}/{DOWNLOAD_RETRIES})')
                time.sleep(delay)

            print(f'⏬ Downloading installer from {url}...')
            vprint(f'  Attempt {attempt}/{DOWNLOAD_RETRIES}')

            with urllib.request.urlopen(url, timeout=timeout) as response:
                content = response.read()
            with Path(dest).open('wb') as f:
                f.write(content)

        except urllib.error.URLError as e:
            print(f'❌ Download failed: {e}', file=sys.stderr)
            if attempt == DOWNLOAD_RETRIES:
                print('\n🔧 Troubleshooting:', file=sys.stderr)
                print('  1. Check your internet connection',               file=sys.stderr)
                print('  2. Verify you can access https://github.com',     file=sys.stderr)
                print('  3. Check if a proxy is required in your network', file=sys.stderr)
                return False

        except Exception as e:
            print(f'❌ Unexpected error during download: {e}', file=sys.stderr)
            if attempt == DOWNLOAD_RETRIES:
                return False

        else:
            print(f'✅ Downloaded to {dest}')
            return True

    return False


def run_installer(installer_path: PathLike) -> bool:
    """
    Execute the Hatch installer script

    :param installer_path: path to installer script
    :return: True on success, False on failure
    """
    print('💿 Running Hatch installer...')
    try:
        result = subprocess.run(
            [sys.executable, str(installer_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f'❌ Installation failed: {e}', file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        return False
    else:
        print(result.stdout)
        return True


def verify_installation() -> bool:
    """
    Verify that Hatch was installed successfully. Provides detailed guidance if tool is installed but not in PATH

    :return: True on success, False on failure
    """
    print('\n🔍 Verifying installation...')
    vprint('Checking all known installation locations...')

    # Use find_executable to check all locations
    executable, version = find_executable()
    if not executable:
        print('❌ Hatch installation could not be verified', file=sys.stderr)
        print('\n🔧 Troubleshooting:', file=sys.stderr)
        print('  1. Close and reopen your terminal', file=sys.stderr)
        print('  2. Try running the installer again with --force', file=sys.stderr)
        print('  3. Check the official Hatch installation guide:', file=sys.stderr)
        print('     https://hatch.pypa.io/latest/install/', file=sys.stderr)
        return False

    # Tool found!
    print(f'✅ Hatch installed successfully: {version}')

    # Check if it's in PATH
    if executable == 'hatch':
        print('✅ Hatch is in your PATH and ready to use')
        vprint(f'  Executable: {executable}')
        return True

    # Tool is installed but not in PATH
    else:
        print(f'📍 Found at: {executable}')
        print('\n⚠️  Hatch is installed but not in your PATH')

        install_dir = Path(executable).parent
        shell       = detect_shell()
        rc_file     = get_shell_rc_file()
        export_cmd  = get_path_export_command(install_dir)

        print('\n💡 To make Hatch available globally, add it to your PATH:')

        if rc_file and export_cmd and shell:
            print(f'\n  For {shell}, add this line to {rc_file}:')
            print(f'  {export_cmd}')
            print('\n  Then run:')
            print(f'  source {rc_file}')
        else:
            print(f'\n  Add {install_dir} to your PATH environment variable')
            print("  Consult your shell's documentation for instructions")

        print(f'\n  Or use the full path: {executable}')

        # Still consider this a success since the tool is installed
        return True


def main() -> None:
    """
    Programmatically install Hatch using the official installer script
    """
    global DOWNLOAD_RETRIES
    global RETRY_DELAY_SECONDS
    global VERBOSE

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Install Hatch build tool with maximum reliability',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='\n'.join([
            'Examples:',
            '  %(prog)s                        # Normal installation',
            '  %(prog)s --force                # Force reinstall even if present',
            '  %(prog)s --verbose              # Show detailed progress',
            '  %(prog)s --force -v             # Force reinstall with verbose output',
            '  %(prog)s --retries 5            # Increase download retry attempts to 5',
            '  %(prog)s --retry-delay 3        # Set initial retry delay to 3 seconds',
            '  %(prog)s --retries 5 --retry-delay 3  # Custom retry configuration',
        ]),
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force installation even if Hatch is already installed',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Enable verbose output for debugging',
    )
    parser.add_argument(
        '--retries',
        type=int,
        default=DOWNLOAD_RETRIES,
        metavar='N',
        help=f'Maximum number of download retry attempts (default: {DOWNLOAD_RETRIES})',
    )
    parser.add_argument(
        '--retry-delay',
        type=int,
        default=RETRY_DELAY_SECONDS,
        metavar='SECONDS',
        help=f'Initial delay in seconds between retries, uses exponential backoff (default: {RETRY_DELAY_SECONDS})',
    )
    args = parser.parse_args()

    # Set global config variables with parsed command-line option values
    DOWNLOAD_RETRIES    = args.retries
    RETRY_DELAY_SECONDS = args.retry_delay
    VERBOSE             = args.verbose

    # Validate retry parameters
    if DOWNLOAD_RETRIES < 1:
        print('❌ Error: --retries must be at least 1', file=sys.stderr)
        sys.exit(1)
    if RETRY_DELAY_SECONDS < 0:
        print('❌ Error: --retry-delay cannot be negative', file=sys.stderr)
        sys.exit(1)

    print('╔═══════════════════════════════╗')
    print('║   Hatch Installation Script   ║')
    print('╚═══════════════════════════════╝')
    print()

    vprint(f'Download retry configuration: {DOWNLOAD_RETRIES} attempts, {RETRY_DELAY_SECONDS}s initial delay\n')

    # Check Python version
    if not check_python_version():
        sys.exit(ExitCode.PYTHON_VERSION)

    # Check if already installed (unless --force is specified)
    if not args.force:
        if is_installed():
            print('⏭️ Skipping installation')
            print('\n💡 Tip: Use --force to reinstall')
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

    # Download installer to temp location
    installer_path = Path.home() / '.hatch_installer.py'
    vprint(f'Temporary installer path: {installer_path}')
    if not download_installer(url, installer_path):
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

    print('\n🎉 Installation complete!')
    print('\n📋 Next steps:')
    print('  1. Close and reopen your terminal (or run: source ~/.bashrc)')
    print('  2. Verify with: hatch --version')
    print('  3. View documentation: https://hatch.pypa.io/')
    sys.exit(ExitCode.SUCCESS)


if __name__ == '__main__':
    main()
