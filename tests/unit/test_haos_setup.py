"""
Unit tests for vms/haos/setup.sh --dry-run: change counting and the `haos: changes=N` line (stubbed host tools)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP     = REPO_ROOT / 'vms' / 'haos' / 'setup.sh'
BASH      = shutil.which('bash')

pytestmark = pytest.mark.skipif(BASH is None, reason='bash not installed')

# The two files setup.sh manages under /etc, exactly as it writes them (write_if_changed compares the content)
LIBVIRT_GUESTS = (
    '# Managed by dotfiles vms/haos/setup.sh\n'
    'ON_BOOT=ignore\n'
    'ON_SHUTDOWN=shutdown\n'
    'SHUTDOWN_TIMEOUT=300\n'
)
DOCKER_DROP_IN = (
    '# Managed by dotfiles vms/haos/setup.sh\n'
    '[Service]\n'
    "ExecStartPost=-/bin/sh -c 'iptables -w -C DOCKER-USER -i br0 -o br0 -j ACCEPT 2>/dev/null || "
    "iptables -w -I DOCKER-USER -i br0 -o br0 -j ACCEPT'\n"
)
# The udev rule for the default HAOS_USB (ConBee II, 1cf1:0030)
USB_RULES = (
    '# Managed by dotfiles vms/haos/setup.sh: hand USB radios to the HAOS VM\n'
    'SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="1cf1", ATTR{idProduct}=="0030", '
    'GROUP="libvirt-qemu", MODE="0660", ENV{ID_MM_DEVICE_IGNORE}="1"\n'
    'SUBSYSTEM=="tty", ATTRS{idVendor}=="1cf1", ATTRS{idProduct}=="0030", ENV{ID_MM_DEVICE_IGNORE}="1"\n'
)

# Stubs read flag files in $HAOS_TEST_STATE: each flag's presence makes the matching host fact true
STUBS: dict[str, str] = {
    'ip': (
        '[ -f "$HAOS_TEST_STATE/bridge" ] && echo "5: br0    inet 192.168.68.79/22 brd 192.168.71.255"\n'
        'exit 0\n'
    ),
    'lsusb':       '[ -f "$HAOS_TEST_STATE/usb-plugged" ]; exit $?\n',
    'dpkg-query':  '[ -f "$HAOS_TEST_STATE/pkgs" ] && printf "install ok installed"\nexit 0\n',
    'id':          'if [ -f "$HAOS_TEST_STATE/group" ]; then echo "tester sudo libvirt"; else echo "tester sudo"; fi\n',
    'df': (
        'for last; do :; done\n'
        '[ -e "$last" ] || exit 1\n'
        'printf "Avail\\n100G\\n"\n'
    ),
    'systemctl': (
        'case "$1" in\n'
        'is-enabled) [ -f "$HAOS_TEST_STATE/enabled-$3" ]; exit $? ;;\n'
        'is-active) [ -f "$HAOS_TEST_STATE/active-$3" ]; exit $? ;;\n'
        'list-unit-files) [ -f "$HAOS_TEST_STATE/docker" ]; exit $? ;;\n'
        'esac\n'
        'exit 0\n'
    ),
    'virsh': (
        'while [ "$1" = -r ] || [ "$1" = -c ]; do\n'
        '    if [ "$1" = -c ]; then shift; fi\n'
        '    shift\n'
        'done\n'
        'case "$1" in\n'
        'net-info)\n'
        '    [ -f "$HAOS_TEST_STATE/net-default" ] || exit 1\n'
        '    printf "Active:         yes\\nAutostart:      yes\\n" ;;\n'
        'dominfo)\n'
        '    [ -f "$HAOS_TEST_STATE/vm" ] || exit 1\n'
        '    if [ -f "$HAOS_TEST_STATE/vm-autostart" ]; then\n'
        '        echo "Autostart:      enable"\n'
        '    else\n'
        '        echo "Autostart:      disable"\n'
        '    fi ;;\n'
        'domblklist)\n'
        '    printf "Type   Device   Target   Source\\nfile   disk     sda      %s\\n" '
        '"$HAOS_IMAGES_DIR/haos.qcow2" ;;\n'
        'dumpxml)\n'
        '    [ -f "$HAOS_TEST_STATE/vm" ] || exit 1\n'
        '    if [ -f "$HAOS_TEST_STATE/usb" ]; then\n'
        '        echo "<hostdev><source><vendor id=\'0x1cf1\'/><product id=\'0x0030\'/></source></hostdev>"\n'
        '    fi ;;\n'
        'domstate) if [ -f "$HAOS_TEST_STATE/vm-running" ]; then echo running; else echo "shut off"; fi ;;\n'
        'esac\n'
        'exit 0\n'
    ),
}

# A host where setup.sh has already converged
CONVERGED = (
    'bridge',
    'pkgs',
    'group',
    'docker',
    'enabled-libvirtd.service',
    'enabled-libvirt-guests.service',
    'active-libvirt-guests.service',
    'vm',
    'vm-autostart',
    'vm-running',
    'usb',
)


@pytest.fixture
def host(tmp_path: Path) -> dict[str, str]:
    """
    Stubbed host tools first on PATH, relocated /etc, images dir and KVM device; returns the environment
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name, body in STUBS.items():
        (bin_dir / name).write_text(f'#!/bin/sh\n{body}', encoding='utf-8')
        (bin_dir / name).chmod(0o755)

    for sub in ('state', 'etc', 'images'):
        (tmp_path / sub).mkdir()
    kvm = tmp_path / 'kvm'
    kvm.touch()

    return {
        **{key: value for key, value in os.environ.items() if not key.startswith(('HAOS_', 'BRIDGE'))},
        'PATH':            f'{bin_dir}:{os.environ["PATH"]}',
        'SUDO_USER':       'tester',
        'HAOS_TEST_STATE': str(tmp_path / 'state'),
        'HAOS_ETC_DIR':    str(tmp_path / 'etc'),
        'HAOS_IMAGES_DIR': str(tmp_path / 'images'),
        'HAOS_KVM_DEVICE': str(kvm),
    }


def _converge(host: dict[str, str], *, skip: tuple[str, ...] = ()) -> None:
    """
    Make the stubbed host converged, except for the flags in skip
    """
    state = Path(host['HAOS_TEST_STATE'])
    for flag in CONVERGED:
        if flag not in skip:
            (state / flag).touch()

    etc = Path(host['HAOS_ETC_DIR'])
    (etc / 'default').mkdir()
    (etc / 'default' / 'libvirt-guests').write_text(LIBVIRT_GUESTS, encoding='utf-8')
    drop_in = etc / 'systemd' / 'system' / 'docker.service.d'
    drop_in.mkdir(parents=True)
    (drop_in / '10-bridge-forward.conf').write_text(DOCKER_DROP_IN, encoding='utf-8')
    (Path(host['HAOS_IMAGES_DIR']) / 'haos.qcow2').touch()
    udev_dir = etc / 'udev' / 'rules.d'
    udev_dir.mkdir(parents=True)
    (udev_dir / '90-haos-usb.rules').write_text(USB_RULES, encoding='utf-8')


def _dry_run(host: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """
    Run setup.sh --dry-run against the stubbed host
    """
    assert BASH is not None
    return subprocess.run([BASH, str(SETUP), '--dry-run'], capture_output=True, text=True, check=False, env=host)


class TestHaosChangeCount:
    """
    Tests for setup.sh's change counting
    """
    def test_converged_host_reports_zero(self, host: dict[str, str]) -> None:
        """
        Test that a converged host reports changes=0
        """
        _converge(host)

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr
        assert 'haos: changes=0' in result.stdout.splitlines()

    @pytest.mark.parametrize(
        'missing',
        [
            'group',
            'active-libvirt-guests.service',
            'enabled-libvirtd.service',
            'vm-running',
            'vm-autostart',
            'usb',
        ],
    )
    def test_single_drift_reports_one(self, host: dict[str, str], missing: str) -> None:
        """
        Test that one unconverged fact is counted as exactly one change
        """
        _converge(host, skip=(missing,))

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr
        assert 'haos: changes=1' in result.stdout.splitlines()

    def test_stale_usb_rules_are_counted_and_not_written(self, host: dict[str, str]) -> None:
        """
        Test that drifted udev rules count as changes (write, reload, trigger, settle) and the dry run leaves them alone
        """
        _converge(host)
        rules = Path(host['HAOS_ETC_DIR']) / 'udev' / 'rules.d' / '90-haos-usb.rules'
        rules.write_text('# stale\n', encoding='utf-8')

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr
        assert 'haos: changes=4' in result.stdout.splitlines()
        assert rules.read_text(encoding='utf-8') == '# stale\n'

    def test_plugged_usb_is_reattached_after_a_rules_change(self, host: dict[str, str]) -> None:
        """
        Test that a rules change on a running VM with the stick plugged in counts the detach and attach as well
        """
        _converge(host)
        (Path(host['HAOS_TEST_STATE']) / 'usb-plugged').touch()
        rules = Path(host['HAOS_ETC_DIR']) / 'udev' / 'rules.d' / '90-haos-usb.rules'
        rules.unlink()

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr
        assert 'haos: changes=6' in result.stdout.splitlines()

    def test_empty_haos_usb_skips_passthrough(self, host: dict[str, str]) -> None:
        """
        Test that HAOS_USB='' makes the USB step a no-op even when the rules and hostdev are absent
        """
        _converge(host, skip=('usb',))
        (Path(host['HAOS_ETC_DIR']) / 'udev' / 'rules.d' / '90-haos-usb.rules').unlink()

        result = _dry_run({**host, 'HAOS_USB': ''})
        assert result.returncode == 0, result.stderr
        assert 'haos: changes=0' in result.stdout.splitlines()

    def test_fresh_host_counts_without_writing(self, host: dict[str, str]) -> None:
        """
        Test that a fresh host reports changes and the dry run writes nothing
        """
        (Path(host['HAOS_TEST_STATE']) / 'bridge').touch()
        (Path(host['HAOS_TEST_STATE']) / 'docker').touch()

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr

        counts = [line for line in result.stdout.splitlines() if line.startswith('haos: changes=')]
        assert len(counts) == 1
        assert int(counts[0].split('=', 1)[1]) > 0
        assert not any(Path(host['HAOS_ETC_DIR']).iterdir())

    def test_missing_images_dir_does_not_abort_dry_run(self, host: dict[str, str]) -> None:
        """
        Test that a dry run before libvirt is installed (no images dir yet) still reports a single change count
        """
        (Path(host['HAOS_TEST_STATE']) / 'bridge').touch()
        Path(host['HAOS_IMAGES_DIR']).rmdir()

        result = _dry_run(host)
        assert result.returncode == 0, result.stderr

        counts = [line for line in result.stdout.splitlines() if line.startswith('haos: changes=')]
        assert len(counts) == 1
        assert int(counts[0].split('=', 1)[1]) > 0
        assert not Path(host['HAOS_IMAGES_DIR']).exists()

    def test_missing_bridge_fails_with_instructions(self, host: dict[str, str]) -> None:
        """
        Test that a missing bridge fails before any change, naming bridge.sh
        """
        result = _dry_run(host)
        assert result.returncode != 0
        assert 'run vms/haos/bridge.sh first' in result.stderr
