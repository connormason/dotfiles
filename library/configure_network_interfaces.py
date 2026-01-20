#!/usr/bin/python
"""
Module for configuring a macOS network interface
"""
from __future__ import annotations

import re
import traceback
from typing import Any
from typing import ClassVar
from typing import NamedTuple
from typing import Optional
from typing import Union

""" Module metadata """


ANSIBLE_METADATA: dict[str, Any] = {
    'metadata_version': '1.0',
    'status':           ['stableinterface'],
    'supported_by':     'community',
}

DOCUMENTATION = """
---
module: configure_network_interfaces

short_description: This module can configure macOS network interfaces

description: Allows configuration of macOS network interfaces by wrapping the `networksetup` command. One (and only one)
             of the options `dhcp`, `dhcp_with_manual_address`, and `manual` may be specified

options:
  interfaces:
    description: Network interface configurations. Each entry corresponds to a hardware network port and its
                 corresponding network service on the host machine
    type: list
    elements: dict
    required: true
    options:
      mac_address:
        description: MAC address of network interface hardware port (this is the unique identifier)
        type: str
        required: true
      name:
        description: Custom name to set for network service
        type: str
        required: false
      dhcp:
        description: Configure interface for DHCP
        type: bool
        required: false
      dhcp_with_manual_address:
        description: Configure interface for DHCP with a manual IP address
        type: dict
        required: false
        options:
          ip_address:
            description: IP address to set for interface
            type: str
            required: true
      manual:
        description: Configure interface manually
        type: dict
        required: false
        options:
          ip_address:
            description: IP address to set for interface
            type: str
            required: true
          subnet_mask:
            description: Subnet mask to set for interface
            type: str
            required: true
          router:
            description: Router address to set for interface
            type: str
            required: false
      ipv6:
        description: Configure IPv6
        type: dict
        required: false
        options:
          off:
            description: Turn IPv6 off for service
            type: bool
            required: false
          automatic:
            description: Set the service to get its IPv6 info automatically
            type: bool
            required: false
          link_local:
            description: Set the service to use its IPv6 only for link local
            aliases:
              - link_local_only
            type: bool
            required: false
          manual:
            description: Set the service to get its IPv6 info manually
            type: dict
            required: false
            options:
              address:
                description: IPv6 address to set for interface
                type: str
                required: true
              prefix_length:
                description: IPv6 prefix length to set for interface
                type: int
                required: true
              router:
                description: IPv6 router address to set for interface
                type: str
                required: false
                default: none
      dns_servers:
        description: DNS servers to set for interface. If None, existing DNS servers will be preserved. If empty list,
                     existing DNS servers will be cleared out
        type: list
        elements: str
        required: false
        default: none
      search_domains:
        description: Search domains to set for interface. If None, existing search domains will be preserved. If empty
                     list, existing DNS servers will be cleared out
        type: list
        elements: str
        required: false
        default: none
      hardware:
        description: Hardware configuration for port associated with network interface. If not provided, hardware
                     configuration will be automatically configured by macOS
        type: dict
        required: false
        options:
          speed:
            description: Configure speed of network port. Note that not all ports support all speeds
            type: int
            required: false
            choices:
              - 10
              - 100
              - 1000
          duplex:
            description: Configure duplex setting of network port. Note that not all ports support all settings, and
                         not all configurations support setting this at all
            type: str
            required: false
            choices:
              - full-duplex
              - half-duplex
          flow_control:
            description: Enable flow control for network port. Note that not all configurations support this
            type: bool
            required: false
          energy_efficient_ethernet:
            description: Enable energy efficient ethernet for network port. Note that not all configurations support
                         this
            type: bool
            required: false
          mtu:
            description: MTU setting of network port. If not provided, the default MTU setting will be used
            type: int
            required: false

author:
    - Connor Mason (@connor-mason)
"""

EXAMPLES = """
# Configure interface for DHCP
- hosts: myhost.mydomain.com
  tasks:
    - name: Configure Ethernet for DHCP
      configure_network_interfaces:
        - mac_address: d8:ec:5e:11:77:c5
          dhcp: true

# Configure interface for DHCP w/ manual IP address and set custom service name
- hosts: myhost.mydomain.com
  tasks:
    - name: Configure Ethernet static IP
      configure_network_interfaces:
        - name: Ethernet (Static IP)
          mac_address: d8:ec:5e:11:77:c5
          dhcp_with_manual_address:
            ip_address: 192.168.1.40

# Configure two interfaces, one for DHCP, one manually
- hosts: myhost.mydomain.com
  tasks:
    - name: Configure Ethernet static IP
      configure_network_interfaces:
        - name: Ethernet
          mac_address: d8:ec:5e:11:77:c5
          dhcp: true

        - name: Custom Thing
          mac_address: 38:f9:d3:16:de:d7
          manual:
            ip_address: 10.10.10.100
            subnet_mask: 255.255.255.0
          hardware:
            speed: 1000
            duplex: full-duplex
            flow_control: true
            energy_efficient_ethernet: false
            mtu: 9000

# Configure interface manually and only use IPv6 for link local
- hosts: myhost.mydomain.com
  tasks:
    - name: Configure Ethernet static IP
      configure_network_interfaces:
        - name: Ethernet
          mac_address: 38:f9:d3:16:de:d7
          manual:
            ip_address: 192.169.1.123
            subnet_mask: 255.255.255.0
          ipv6:
            link_local: true
"""

RETURN = """
changed:
  description: Whether any changes were made
  type: bool
  returned: always
changelog:
  description: List of changes made to network configuration
  type: list
  returned: always
commands_run:
  description: networksetup commands run to configure network settings
  type: list
  returned: always
cmd:
  description: networksetup command that did not complete successfully
  type: str
  returned: When error encountered while running networksetup tool
stdout:
  description: Standard out of networksetup command that did not complete successfully
  type: str
  returned: When error encountered while running networksetup tool
stderr:
  description: Standard err of networksetup command that did not complete successfully
  type: str
  returned: When error encountered while running networksetup tool
available_hardware_ports:
  description: List of available hardware ports on host
  type: list
  elements: dict
  sample:
    - name: Ethernet
      device: en0
      address: d8:ec:5e:11:77:c4
  returned: always
available_network_services:
  description: List of available network services on host
  type: list
  elements: dict
  sample:
    - name: Belkin USB-C LAN
      configuration: dhcp
    - name: Ethernet
      configuration: dhcp_with_manual_address
      ip_address: 192.168.1.20
    - name: Ethernet 2
      configuration: manual
      ip_address: 192.168.1.21
      subnet_mask: 255.255.255.0
valid_mtu_range_by_port:
  description: Valid range of MTU values per hardware port
  type: dict
  elements: tuple
  sample: (1280, 9000)
  returned: When MTU setting is configured for a port
valid_media_by_port:
  description: Valid media configurations per hardware port
  type: dict
  elements: list
  sample:
    - speed: 1000
      duplex: full-duplex
      flow_control: false
      energy_efficient_ethernet: false
  returned: When media configuration set for a port
"""


from ansible.module_utils.basic import AnsibleModule  # noqa: E402

""" Exceptions """


class ConfigurationError(Exception):
    """
    Error raised when there is an issue configuring network interfaces
    """
    pass


""" Regex definitions """


HARDWARE_PORTS_REGEX = re.compile(
    r'Hardware Port: (?P<name>.+)\nDevice: (?P<device>\w+)\nEthernet Address: (?P<address>[\w:]+)'
)
MTU_REGEX          = re.compile(r'Active MTU: (?P<active>\d+) \(Current Setting: (?P<current>\d+)\)')
MTU_RANGE_REGEX    = re.compile(r'Valid MTU Range: (?P<min>\d+)-(?P<max>\d+)')
MEDIA_CONFIG_REGEX = re.compile(r'(?P<speed>\d+baseT[\/\w]*) <(?P<media>.+)>')

INTERFACE_INFO_REGEXES: dict[str, re.Pattern[str]] = {
    'configuration':        re.compile(r'(?P<configuration>.+) Configuration\n'),
    'ip_address':           re.compile(r'IP address: (?P<ip_address>[\d\.]+)\n'),
    'subnet_mask':          re.compile(r'Subnet mask: (?P<subnet_mask>[\d\.]+)\n'),
    'router':               re.compile(r'Router: (?P<router>[\d\.]+)\n'),
    'address':              re.compile(r'(Ethernet Address|Wi-Fi ID): (?P<address>[\w:]+)\n'),
    'ipv6_configuration':   re.compile(r'IPv6: (?P<ipv6_configuration>Off|Automatic|Manual)\n'),
    'ipv6_address':         re.compile(r'IPv6 IP address: (?P<address>[\w\:]+)'),
    'ipv6_router':          re.compile(r'IPv6 Router: (?P<ipv6_router>[\w\:]+)'),
    'ipv6_prefix_length':   re.compile(r'IPv6 Prefix Length: (?P<ipv6_prefix_length>\d+)'),
}


""" Lookups """


INTERFACE_CONFIGURATION_MAP: dict[str, str] = {
    'DHCP':                       'dhcp',
    'Manually Using DHCP Router': 'dhcp_with_manual_address',
    'Manual':                     'manual',
}
INTERFACE_IPV6_CONFIGURATION_MAP: dict[Union[str, None], str] = {
    'Off':       'off',
    'Automatic': 'automatic',
    'Manual':    'manual',
    None:        'link_local',   # "IPv6" entry not shown in `networksetup -getinfo` if in link local mode
}

SPEED_MAPPING: dict[int, str] = {
    10:   '10baseT/UTP',
    100:  '100baseTX',
    1000: '1000baseT'
}
SPEED_REVERSE_MAPPING: dict[str, int] = {v: k for k, v in SPEED_MAPPING.items()}


""" Parsed types """


class HardwarePortEntry(NamedTuple):
    """
    Representation of an entry in ``networksetup -listallhardwareports``
    """
    name:    str
    device:  str
    address: str


class HardwarePortMediaConfig(NamedTuple):
    """
    Representation of a media configuration supported by a hardware port
    """
    speed:                     int     # 10, 100, 1000
    duplex:                    str     # "half-duplex" or "full-duplex"
    flow_control:              bool
    energy_efficient_ethernet: bool


class CurrentHardwarePortMediaConfig(NamedTuple):
    """
    Representation of currently configured/active media configuration for a hardware port
    """
    current: Union[HardwarePortMediaConfig, str]    # Union[HardwarePortMediaConfig, Literal['autoselect']]
    active:  HardwarePortMediaConfig


class CurrentMTUConfig(NamedTuple):
    """
    Representation of currently configured/active MTU value for a hardware port
    """
    current: int
    active:  int


class NetworkServiceInfo(NamedTuple):
    """
    Representation of network service info, as returned by ``networksetup -getinfo <service>``

    Does not include IPv6 data present in the command output
    """
    name:               str
    configuration:      str             # "dhcp", "dhcp_with_manual_address", "manual"
    ip_address:         Optional[str]   # None if interface is not active
    subnet_mask:        Optional[str]   # None if interface is not active
    router:             Optional[str]   # None if interface is not active or (null)
    ipv6_configuration: str             # "off", "automatic", "link_local", "manual", "unknown" (if cannot parse)
    ipv6_address:       Optional[str]   # None if not active
    ipv6_router:        Optional[str]   # None if not active or router not set
    ipv6_prefix_length: Optional[int]   # None if not set manually
    address:            Optional[str]   # MAC address. Can be (null). "Ethernet Address"


""" Parsing helpers """


def parse_listhardwarereports(stdout: str) -> dict[str, HardwarePortEntry]:
    """
    Parse output of ``networksetup -listallhardwareports``

    :param stdout: stdout of command
    :return: mapping from MAC address -> HardwarePortEntry dict
    """
    ports: dict[str, HardwarePortEntry] = {}
    for m in HARDWARE_PORTS_REGEX.finditer(stdout):
        ports[m.group('address')] = HardwarePortEntry(
            name=m.group('name'),
            device=m.group('device'),
            address=m.group('address'),
        )
    return ports


def parse_getmtu(stdout: str) -> Optional[CurrentMTUConfig]:
    """
    Parse output of ``networksetup -getMTU <hardware port>``

    :param stdout: stdout of command
    :return: CurrentMTUConfig dict
    """
    if m := MTU_REGEX.match(stdout):
        return CurrentMTUConfig(current=int(m.group('current')), active=int(m.group('active')))
    else:
        return None


def parse_listvalidmturange(stdout: str) -> Optional[tuple[int, int]]:
    """
    Parse output of ``networksetup -listvalidMTUrange <hardware port>``

    :param stdout: stdout of command
    :return: (min, max) or None if unable to parse
    """
    if m := MTU_RANGE_REGEX.match(stdout):
        return int(m.group('min')), int(m.group('max'))
    else:
        return None


def parse_media(media_str: str) -> Optional[HardwarePortMediaConfig]:
    """
    Parse str representation of media configuration, as outputted by:

        - ``networksetup -listvalidmedia <hardware port>``
        - ``networksetup -getmedia <hardware port>``

    :param media_str: str representation of media configuration
    :return: HardwarePortMediaConfig dict
    """
    if m := MEDIA_CONFIG_REGEX.match(media_str):
        speed_int = SPEED_REVERSE_MAPPING[m.group('speed')]
        media = [item.strip() for item in m.group('media').split(',')]
        duplex = 'half-duplex' if 'half-duplex' in media else 'full-duplex'
        return HardwarePortMediaConfig(
            speed=speed_int,
            duplex=duplex,
            flow_control='flow-control' in media,
            energy_efficient_ethernet='energy-efficient-ethernet' in media,
        )
    else:
        return None


def parse_listvalidmedia(stdout: str) -> list[HardwarePortMediaConfig]:
    """
    Parse output of ``networksetup -listvalidmedia <hardware port>``

    :param stdout: stdout of command
    :return: list of HardwarePortMediaConfig dicts. If only "autoselect" is supported, this will be an empty list
    """
    configs: list[HardwarePortMediaConfig] = []
    for line in stdout.splitlines():
        media_config = parse_media(line)
        if media_config:
            configs.append(media_config)
    return configs


def parse_getinfo(name: str, stdout: str) -> Optional[NetworkServiceInfo]:
    """
    Parse output of ``networksetup -getinfo <service>``

    :param name: name of service
    :param stdout: stdout of command
    :return: NetworkServiceInfo dict or None if unable to parse
    """
    info: dict[str, Optional[str]] = {}
    for key, regex in INTERFACE_INFO_REGEXES.items():
        if m := regex.search(stdout):
            info[key] = m.group(key) if m.group(key).lower() != 'none' else None
        else:
            info[key] = None

    if (info['configuration'] is None) or (info['configuration'] not in INTERFACE_CONFIGURATION_MAP):
        return None
    else:
        info['configuration'] = INTERFACE_CONFIGURATION_MAP[info['configuration']]

    ipv6_prefix_length: int | None = None
    if ipv6_prefix_length_str := info.get('ipv6_prefix_length'):
        ipv6_prefix_length = int(ipv6_prefix_length_str)

    return NetworkServiceInfo(
        name=name,
        configuration=info['configuration'],
        ip_address=info['ip_address'],
        subnet_mask=info['subnet_mask'],
        router=info['router'],
        address=info['address'],
        ipv6_configuration=INTERFACE_IPV6_CONFIGURATION_MAP.get(info['ipv6_configuration'], 'unknown'),
        ipv6_address=info['ipv6_address'],
        ipv6_router=info['ipv6_router'],
        ipv6_prefix_length=ipv6_prefix_length,
    )


""" Core module logic """


def build_module() -> AnsibleModule:
    """
    Build AnsibleModule with argument spec

    :return: :class:`AnsibleModule` obj
    """
    return AnsibleModule(
        argument_spec=dict(
            interfaces=dict(
                type='list',
                elements='dict',
                required=True,
                options=dict(

                    # Required args
                    mac_address=dict(
                        type='str', required=True,
                    ),

                    # Interface customization args
                    name=dict(
                        type='str', required=False, default=None,
                    ),

                    # DHCP args
                    dhcp=dict(
                        type='bool', required=False,
                    ),

                    # DHCP w/ manual address args
                    dhcp_with_manual_address=dict(
                        type='dict',
                        required=False,
                        options=dict(
                            ip_address=dict(
                                type='str', required=True,
                            ),
                        ),
                    ),

                    # Manual args
                    manual=dict(
                        type='dict',
                        required=False,
                        options=dict(
                            ip_address=dict(
                                type='str', required=True,
                            ),
                            subnet_mask=dict(
                                type='str', required=True,
                            ),
                            router=dict(
                                type='str', required=False, default=None,
                            ),
                        ),
                    ),

                    # IPv6 args
                    ipv6=dict(
                        type='dict',
                        required=False,
                        options=dict(
                            off=dict(
                                type='bool', required=False,
                            ),
                            automatic=dict(
                                type='bool', required=False,
                            ),
                            link_local=dict(
                                type='bool', required=False, aliases=['link_local_only'],
                            ),
                            manual=dict(
                                type='dict', required=False,
                                options=dict(
                                    address=dict(
                                        type='str', required=True,
                                    ),
                                    prefix_length=dict(
                                        type='int', required=True,
                                    ),
                                    router=dict(
                                        type='str', required=False, default=None,
                                    ),
                                ),
                            ),
                        ),

                        # Require exactly one of: off, automatic, link_local, manual
                        mutually_exclusive=[
                            ('off', 'automatic', 'link_local', 'manual'),
                        ],
                        required_one_of=[
                            ('off', 'automatic', 'link_local', 'manual'),
                        ],
                    ),

                    # DNS server/search domain args
                    # Set to empty list to clear out configured values
                    dns_servers=dict(
                        type='list', elements='str', required=False, default=None,
                    ),
                    search_domains=dict(
                        type='list', elements='str', required=False, default=None,
                    ),

                    # Hardware configuration args
                    hardware=dict(
                        type='dict',
                        required=False,
                        default=None,
                        options=dict(
                            speed=dict(
                                type='int', required=False, default=None,
                                choices=[10, 100, 1000],
                            ),
                            duplex=dict(
                                type='str',  required=False, default=None,
                                choices=['full', 'full-duplex', 'half', 'half-duplex'],
                            ),
                            flow_control=dict(
                                type='bool', required=False, default=None,
                            ),
                            energy_efficient_ethernet=dict(
                                type='bool', required=False, default=None,
                            ),
                            mtu=dict(
                                type='int',  required=False, default=None,
                            ),
                        ),
                        required_together=['speed', 'duplex', 'flow_control', 'energy_efficient_ethernet'],
                    ),
                ),

                # Require exactly one of: dhcp, dhcp_with_manual_address, manual
                mutually_exclusive=[
                    ('dhcp', 'dhcp_with_manual_address', 'manual'),
                ],
                required_one_of=[
                    ('dhcp', 'dhcp_with_manual_address', 'manual'),
                ],
            ),
        ),
        supports_check_mode=True,
    )


class ConfigureNetworkInterfaces:
    """
    Class to manage network interface configuration

    :param module: :class:`AnsibleModule` obj
    """

    #: Network services with any of these prefixes will be ignored by :meth:`get_network_services_by_mac_address`
    IGNORED_NETWORK_SERVICE_PREFIXES: ClassVar[list[str]] = [
        '*',
        'Chimp',
        'Kanzi',
        'Koba',
        'Thunderbolt Bridge',
    ]

    def __init__(self, module: AnsibleModule) -> None:
        self.module:     AnsibleModule  = module
        self.params:     dict[str, Any] = module.params
        self.interfaces: list[dict]     = module.params['interfaces']
        self.bin:        str            = module.get_bin_path('networksetup', opt_dirs=['/usr/sbin'], required=True)

        self._hardware_ports_by_mac_address:   Optional[dict[str, HardwarePortEntry]]  = None
        self._network_services_by_mac_address: Optional[dict[str, NetworkServiceInfo]] = None

        self.result: dict[str, Any] = dict(
            changed=False,
            changelog=[],
            commands_run=[],
        )

    def _update_result(
        self,
        *,
        cmd: Optional[str] = None,
        returncode: Optional[int] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Update result with provided kwargs
        """
        if cmd:
            self.result['cmd'] = cmd
        if returncode:
            self.result['returncode'] = returncode
        if stdout:
            self.result['stdout'] = stdout
        if stderr:
            self.result['stderr'] = stderr
        self.result.update(**kwargs)

        if self.result['changelog']:
            self.result['changed'] = True

    def networksetup_cmd(self, cmd: str, *, check_rc: bool = True, **kwargs: Any) -> tuple[int, str, str]:
        """
        Run ``networksetup`` command

        :param cmd: command
        :param check_rc: raise exception if command return code != 0
        :param kwargs: kwargs to pass into ``AnsibleModule.run_command()``
        :return: (return code, stdout, stderr)
        """
        if cmd.startswith('networksetup'):
            cmd = cmd.lstrip('networksetup').lstrip()

        full_cmd = f'sudo {self.bin} {cmd}'
        self.result['commands_run'].append(full_cmd)

        rc, stdout, stderr = self.module.run_command(full_cmd, check_rc=False, **kwargs)
        if (rc != 0) and check_rc:
            self._update_result(cmd=full_cmd, returncode=rc, stdout=stdout, stderr=stderr)
            raise ConfigurationError(f'Command `networksetup {cmd}` failed: {stderr}')
        else:
            return rc, stdout, stderr

    """ ``networksetup`` command execution/parsing helpers """

    def get_hardware_ports_by_mac_address(self) -> dict[str, HardwarePortEntry]:
        """
        Get hardware network ports. Result is cached, so the command is only run once

        :raises ConfigurationError: if no hardware ports found
        :return: mapping from MAC address -> HardwarePortEntry dict
        """
        if self._hardware_ports_by_mac_address is None:
            cmd = 'networksetup -listallhardwareports'
            rc, stdout, stderr = self.networksetup_cmd(cmd)

            ports: dict[str, HardwarePortEntry] = parse_listhardwarereports(stdout)
            if len(ports) == 0:
                self._update_result(cmd=cmd, returncode=rc, stdout=stdout, stderr=stderr)
                raise ConfigurationError('No hardware ports found')

            self.result['available_hardware_ports'] = list(ports.values())
            self._hardware_ports_by_mac_address = ports

        return self._hardware_ports_by_mac_address

    def get_valid_mtu_range(self, hardware_port: str) -> tuple[int, int]:
        """
        Get valid MTU range for a hardware port

        :param hardware_port: hardware port or device name
        :raises ConfigurationError: if unable to parse MTU range from command output
        :return: (min, max)
        """
        cmd = f'networksetup -listvalidMTUrange "{hardware_port}"'
        rc, stdout, stderr = self.networksetup_cmd(cmd)
        result = parse_listvalidmturange(stdout)
        if result is not None:
            self.result.setdefault('valid_mtu_range_by_port', {})[hardware_port] = (result[0], result[1])
            return result[0], result[1]
        else:
            self._update_result(cmd=cmd, returncode=rc, stdout=stdout, stderr=stderr)
            raise ConfigurationError(f'Unable to parse valid MTU range for hardware port "{hardware_port}"')

    def get_port_mtu(self, hardware_port: str) -> CurrentMTUConfig:
        """
        Get current configured/active MTU value of a hardware port

        :param hardware_port: hardware port or device name
        :raises ConfigurationError: if unable to parse MTU values from command output
        :return: CurrentMTUConfig dict
        """
        cmd = f'networksetup -getMTU "{hardware_port}"'
        rc, stdout, stderr = self.networksetup_cmd(cmd)
        result = parse_getmtu(stdout)
        if result is not None:
            return result
        else:
            self._update_result(cmd=cmd, returncode=rc, stdout=stdout, stderr=stderr)
            raise ConfigurationError(f'Unable to parse current/active MTU values for hardware port "{hardware_port}"')

    def get_port_media_configuration(self, hardware_port: str) -> CurrentHardwarePortMediaConfig:
        """
        Get currently configured/active media configuration of a hardware port

        :param hardware_port: hardware port or device name
        :raises ConfigurationError: if unable to parse configuration from command output
        :return: CurrentHardwarePortMediaConfig dict
        """
        cmd = f'networksetup -getmedia "{hardware_port}"'
        rc, stdout, stderr = self.networksetup_cmd(cmd)

        lines = stdout.splitlines()
        if not (lines[0].startswith('Current: ') and lines[1].startswith('Active: ')):
            self._update_result(cmd=cmd, returncode=rc, stdout=stdout, stderr=stderr)
            raise ConfigurationError(f'Unable to parse media configuration lines for port "{hardware_port}"')

        current_str = lines[0].replace('Current: ', '').strip()
        current: Union[HardwarePortMediaConfig, str]
        if current_str == 'autoselect':
            current = 'autoselect'
        else:
            if media_config := parse_media(current_str):
                current = media_config
            else:
                raise ConfigurationError(f'Unable to parse current media configuration for port "{hardware_port}"')

        active_str = lines[1].replace('Active: ', '').strip()
        active = parse_media(active_str)
        if active is None:
            raise ConfigurationError(f'Unable to parse active media configuration for port "{hardware_port}"')

        return CurrentHardwarePortMediaConfig(current=current, active=active)

    def get_valid_port_media_configurations(self, hardware_port: str) -> list[HardwarePortMediaConfig]:
        """
        Get media configurations supported by a hardware port

        :param hardware_port: hardware port or device name
        :return: list of HardwarePortMediaConfig dicts. If only "autoselect" is supported, this will be an empty list
        """
        _, stdout, _ = self.networksetup_cmd(f'networksetup -listvalidmedia "{hardware_port}"')
        valid_media = parse_listvalidmedia(stdout)
        self.result.setdefault('valid_media_by_port', {})[hardware_port] = valid_media
        return valid_media

    def get_network_service_info(self, service: str, *, update_result_on_error: bool = True) -> NetworkServiceInfo:
        """
        Get network service info by service name

        :param service: network service name
        :param update_result_on_error: if True, module result will be updated with command info on error
        :raises ConfigurationError: if unable to parse network configuration from command output
        :return: NetworkServiceInfo dict
        """
        cmd = f'networksetup -getinfo "{service}"'
        rc, stdout, stderr = self.networksetup_cmd(cmd)

        info = parse_getinfo(service, stdout)
        if info is None:
            if update_result_on_error:
                self._update_result(cmd=cmd, returncode=rc, stdout=stdout, stderr=stderr)
            raise ConfigurationError(f'Unable to parse network configuration for service "{service}"')
        else:
            return info

    def get_network_services_by_mac_address(self) -> dict[str, NetworkServiceInfo]:
        """
        Get network service info for all active interfaces. Result is cached, so the command is only run once

        :return: mapping from MAC address -> NetworkServiceInfo dict
        """
        if self._network_services_by_mac_address is None:
            _, stdout, _ = self.networksetup_cmd('networksetup -listallnetworkservices')

            all_service_info: dict[str, NetworkServiceInfo] = {}
            for service in stdout.splitlines()[1:]:
                service = service.strip()
                if any(service.startswith(ignored_prefix) for ignored_prefix in self.IGNORED_NETWORK_SERVICE_PREFIXES):
                    continue

                try:
                    service_info = self.get_network_service_info(service, update_result_on_error=False)
                except ConfigurationError:
                    pass
                else:
                    if service_info.address is not None:
                        all_service_info[service_info.address] = service_info

            self.result['available_network_services'] = all_service_info
            self._network_services_by_mac_address = all_service_info

        return self._network_services_by_mac_address

    def get_network_service_dns_servers(self, service: str) -> list[str]:
        """
        Get DNS servers configured for the provided network service. Empty list if none configured

        :param service: network service name
        :return: list of configured DNS servers
        """
        _, stdout, _ = self.networksetup_cmd(f'networksetup -getdnsservers "{service}"')
        if "There aren't any" in stdout:
            return []
        else:
            return [line.strip() for line in stdout.splitlines()]

    def get_network_service_search_domains(self, service: str) -> list[str]:
        """
        Get search domains configured for the provided network service. Empty list if none configured

        :param service: network service name
        :return: list of configured search domains
        """
        _, stdout, _ = self.networksetup_cmd(f'networksetup -getsearchdomains "{service}"')
        if "There aren't any" in stdout:
            return []
        else:
            return [line.strip() for line in stdout.splitlines()]

    """ Main configuration command methods """

    def validate_config(self) -> None:
        """
        Ensure the provided network interface configurations are supported by the hardware

        :raises ConfigurationError: if validation fails
        """

        # Ensure all provided MAC addresses exist
        ports = self.get_hardware_ports_by_mac_address()
        for interface in self.interfaces:
            if interface['mac_address'] not in ports:
                raise ConfigurationError(
                    f'No network interface with MAC address "{interface["mac_address"]}" found. '
                    f'Available MAC addresses: {", ".join(ports.keys())}'
                )

        # Validate hardware configuration settings
        for i, interface in enumerate(self.interfaces):
            hardware = interface.get('hardware')
            if not hardware:
                continue

            port_info = ports[interface['mac_address']]

            # Validate MTU setting
            mtu = hardware.get('mtu')
            if mtu:
                min, max = self.get_valid_mtu_range(port_info.name)
                if mtu < min:
                    raise ConfigurationError(
                        f'MTU setting ({mtu}) for interface {i} ({port_info.address}) below minimum supported value '
                        f'for hardware port (supported range: {min}-{max})'
                    )
                elif mtu > max:
                    raise ConfigurationError(
                        f'MTU setting ({mtu}) for interface {i} ({port_info.address}) above maximum supported value '
                        f'for hardware port (supported range: {min}-{max})'
                    )

            # Validate hardware settings (all other than MTU are gated on speed being present)
            speed = hardware.get('speed')
            if speed:
                supported_media = self.get_valid_port_media_configurations(port_info.name)
                media_config = HardwarePortMediaConfig(
                    speed=speed,
                    duplex='half-duplex' if hardware['duplex'] in ['half', 'half-duplex'] else 'full-duplex',
                    flow_control=hardware['flow_control'],
                    energy_efficient_ethernet=hardware['energy_efficient_ethernet'],
                )
                if media_config not in supported_media:
                    raise ConfigurationError(
                        f'Provided hardware configuration not supported by interface {i} ({port_info.address}). '
                        f'See `valid_media_by_port` in result for supported configurations'
                    )

    def configure_interface(self, config: dict[str, Any]) -> None:
        """
        Configure a single network interface

        :param config: interface configuration
        """
        mac_address = config['mac_address']

        # Get hardware port info
        ports = self.get_hardware_ports_by_mac_address()
        port  = ports[mac_address]

        # Lookup corresponding network service info
        services = self.get_network_services_by_mac_address()
        service  = services[mac_address]

        # Set interface to DHCP
        if config['dhcp']:
            self.networksetup_cmd(f'networksetup -setdhcp "{service.name}"')
            if service.configuration != 'dhcp':
                self.result['changelog'].append(f'Set service "{service.name}" to DHCP')

        # Set interface to DHCP with manual address
        elif config['dhcp_with_manual_address']:
            new_ip_address = config['dhcp_with_manual_address']['ip_address']
            self.networksetup_cmd(f'networksetup -setmanualwithdhcprouter "{service.name}" "{new_ip_address}"')
            if service.configuration != 'dhcp_with_manual_address':
                self.result['changelog'].append(
                    f'Set service "{service.name}" to DHCP w/ manual address "{new_ip_address}"'
                )
            elif service.ip_address != new_ip_address:
                self.result['changelog'].append(
                    f'Set service "{service.name}" to DHCP w/ manual address "{new_ip_address}"'
                )

        # Set interface to manual
        elif config['manual']:
            new_ip_address  = config['manual']['ip_address']
            new_subnet_mask = config['manual']['subnet_mask']
            new_router      = config['manual']['router']

            cmd = f'networksetup -setmanual "{service.name}" "{new_ip_address}" "{new_subnet_mask}"'
            if new_router:
                cmd += f' {new_router}'

            self.networksetup_cmd(cmd)
            if service.configuration != 'manual':
                self.result['changelog'].append(f'Set service "{service.name}" to manual')
            if service.ip_address != new_ip_address:
                self.result['changelog'].append(f'Set service "{service.name}" IP address to "{new_ip_address}"')
            if service.subnet_mask != new_subnet_mask:
                self.result['changelog'].append(f'Set service "{service.name}" subnet mask to "{new_subnet_mask}"')
            if service.router != new_router:
                self.result['changelog'].append(f'Set service "{service.name}" router to "{new_router}"')

        # Configure IPv6
        if config['ipv6']:
            if config['ipv6']['off']:
                self.networksetup_cmd(f'networksetup -setv6off "{service.name}"')
                if service.ipv6_configuration != 'off':
                    self.result['changelog'].append(f'Turn IPv6 off for service "{service.name}"')

            elif config['ipv6']['automatic']:
                self.networksetup_cmd(f'networksetup -setv6automatic "{service.name}"')
                if service.ipv6_configuration != 'automatic':
                    self.result['changelog'].append(f'Set service "{service.name}" to get its IPv6 info automatically')

            elif config['ipv6']['link_local']:
                self.networksetup_cmd(f'networksetup -setv6LinkLocal "{service.name}"')
                if service.ipv6_configuration != 'link_local':
                    self.result['changelog'].append(f'Set service "{service.name}" to use its IPv6 only for link local')

            elif config['ipv6']['manual']:
                new_address = config['ipv6']['manual']['address']
                new_prefix_length = config['ipv6']['manual']['prefix_length']
                new_router = config['ipv6']['manual']['router']
                self.networksetup_cmd(
                    f'networksetup -setv6manual "{service.name}" "{new_address}" "{new_prefix_length}" "{new_router}"'
                )

                if service.ipv6_address != new_address:
                    self.result['changelog'].append(f'Set service "{service.name}" IPv6 address to "{new_address}"')
                if service.ipv6_router != new_router:
                    self.result['changelog'].append(f'Set service "{service.name}" IPv6 router to "{new_router}"')
                if service.ipv6_prefix_length != new_prefix_length:
                    self.result['changelog'].append(
                        f'Set service "{service.name}" IPv6 prefix length to "{new_prefix_length}"'
                    )

        # Clear DNS servers if empty list provided
        if (config['dns_servers'] is not None) and (not config['dns_servers']):
            existing_dns_servers = self.get_network_service_dns_servers(service.name)
            self.networksetup_cmd(f'networksetup -setdnsservers "{service.name}" "Empty"')
            if existing_dns_servers:
                self.result['changelog'].append(f'Clear DNS servers from service "{service.name}"')

        # Set DNS servers
        elif config['dns_servers']:
            existing_dns_servers = self.get_network_service_dns_servers(service.name)
            servers_str = ' '.join(f'"{server}"' for server in config['dns_servers'])
            self.networksetup_cmd(f'networksetup -setdnsservers "{service.name}" {servers_str}')
            if set(existing_dns_servers) - set(config['dns_servers']):
                self.result['changelog'].append(f'Set service "{service.name}" DNS servers to: {servers_str}')

        # Clear search domains if empty list provided
        if (config['search_domains'] is not None) and (not config['search_domains']):
            existing_search_domains = self.get_network_service_search_domains(service.name)
            self.networksetup_cmd(f'networksetup -setsearchdomains "{service.name}" "Empty"')
            if existing_search_domains:
                self.result['changelog'].append(f'Clear search domains from service "{service.name}"')

        # Set search domains
        elif config['search_domains']:
            existing_search_domains = self.get_network_service_search_domains(service.name)
            search_domains_str = ' '.join(f'"{domain}"' for domain in config['search_domains'])
            self.networksetup_cmd(f'networksetup -setsearchdomains "{service.name}" {search_domains_str}')
            if set(existing_search_domains) - set(config['search_domains']):
                self.result['changelog'].append(
                    f'Set service "{service.name}" search domains to: {search_domains_str}'
                )

        # If hardware configuration not provided, set to "autoselect"
        media = self.get_port_media_configuration(port.name)
        if not config.get('hardware'):
            self.networksetup_cmd(f'networksetup -setMTUAndMediaAutomatically "{port.name}"')
            if media.current != 'autoselect':
                self.result['changelog'].append(f'Set port "{port.name}" media/MTU configuration to "autoselect"')

        # If hardware configuration provided, configure
        else:

            # If speed not provided, set to "autoselect"
            speed = config['hardware'].get('speed')
            if not speed:
                self.networksetup_cmd(f'networksetup -setmedia "{port.name}" autoselect')
                if (media.current == 'autoselect') or (media.current.speed != speed):     # type: ignore[union-attr]
                    self.result['changelog'].append(f'Set port "{port.name}" media configuration to "autoselect"')

            # If speed provided, configure all hardware media values
            else:
                media_config = HardwarePortMediaConfig(
                    speed=speed,
                    duplex='half-duplex' if config['hardware']['duplex'] in ('half', 'half-duplex') else 'full-duplex',
                    flow_control=config['hardware']['flow_control'],
                    energy_efficient_ethernet=config['hardware']['energy_efficient_ethernet'],
                )

                cmd = f'networksetup -setmedia "{port.name}" {SPEED_MAPPING[speed]} {media_config.duplex}'
                if media_config.flow_control:
                    cmd += ' flow-control'
                if media_config.energy_efficient_ethernet:
                    cmd += ' energy-efficient-ethernet'

                self.networksetup_cmd(cmd)
                if (media.current == 'autoselect') or (media.current != media_config):
                    self.result['changelog'].append(f'Set port "{port.name}" media configuration to: {media_config}')

            # If MTU value not provided, set to default (standard/1500)
            existing_mtu = self.get_port_mtu(port.name)
            mtu = config['hardware'].get('mtu')
            if not mtu:
                self.networksetup_cmd(f'networksetup -setMTU "{port.name}" 1500')
                # Bug fix: Compare existing_mtu.current (int) to 1500 (int), not existing_mtu (NamedTuple) to None
                if existing_mtu.current != 1500:
                    self.result['changelog'].append(f'Set port "{port.name}" MTU to 1500')

            # Set MTU value
            else:
                self.networksetup_cmd(f'networksetup -setMTU "{port.name}" {mtu}')
                # Bug fix: Compare existing_mtu.current (int) to mtu (int), not existing_mtu (NamedTuple) to mtu (int)
                if existing_mtu.current != mtu:
                    self.result['changelog'].append(f'Set port "{port.name}" MTU to {mtu}')

        # Set interface name
        # This runs at the end of everything so our network service name doesn't change while modifying other settings
        if config['name']:
            self.networksetup_cmd(f'networksetup -renamenetworkservice "{service.name}" "{config["name"]}"')
            if service.name != config['name']:
                self.result['changelog'].append(f'Set service "{service.name}" name to "{config["name"]}"')

    def run(self) -> None:
        """
        Run module logic
        """

        # Ensure the provided network interface configurations are supported
        self.validate_config()

        # Configure interfaces
        for i, interface in enumerate(self.interfaces):
            self.configure_interface(interface)


def run_module() -> None:
    """
    Run "configure_network_interface" ansible module
    """

    # Build argument spec, AnsibleModule, and module runner obj
    module = build_module()
    config = ConfigureNetworkInterfaces(module)

    # Return current state if running in check mode
    if module.check_mode:
        module.exit_json(**config.result)

    # Run module
    try:
        config.run()
    except Exception as e:
        if config.result['changelog']:
            config.result['changed'] = True
        module.fail_json(msg=str(e), exc_traceback=traceback.format_exc(), **config.result)
    else:
        module.exit_json(**config.result)


def main() -> None:
    run_module()


if __name__ == '__main__':
    main()
