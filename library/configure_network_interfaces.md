# configure_network_interfaces

This module allows for configuration of macOS network interfaces by wrapping the `networksetup` command.

## Parameters

- `interfaces` (list): list of dictionaries describing desired port/service configuration (see
                       [Interface Configuration](#interface-configuration)). Each entry corresponds to a hardware port
                       and its associated network service on the host machine

### Interface Configuration

Sub-options for each entry in `interfaces` parameter

- `mac_address` (str, required): MAC address of network interface hardware port (this is the unique identifier)
- `name` (str, optional): Custom name to set for network interface
- `dhcp` (bool, optional): Configure interface for DHCP if present/True
- `dhcp_with_manual_address` (dict, optional): Configure interface for DHCP with a manual IP address
  - `ip_address` (str, required): IP address to set for interface
- `manual` (dict, optional): Configure interface manually
  - `ip_address` (str, required): IP address to set for interface
  - `subnet_mask` (str, required): Subnet mask to set for interface
  - `router` (str, optional): Router address to set for interface
- `ipv6` (dict, optional): Configure IPv6
  - `off` (bool, optional): Turn IPv6 off for service
  - `automatic` (bool, optional): Set the service to get its IPv6 info automatically
  - `link_local` (bool, optional): Set the service to use its IPv6 only for link local
  - `manual` (dict, optional): Set the service to get its IPv6 info manually
    - `address` (str, required): IPv6 address to set for interface
    - `prefix_length` (str, required): IPv6 prefix length to set for interface
    - `router` (str, optional): IPv6 router address to set for interface
- `dns_servers` (list, optional): DNS servers to set for interface. If None, existing DNS servers will be preserved.
                                  If empty list, existing DNS servers will be cleared out
- `search_domains` (list, optional): DNS servers to set for interface. If None, existing DNS servers will be
                                     preserved. If empty list, existing DNS servers will be cleared out
- `hardware` (dict, optional): Hardware configuration for port associated with network interface. If not provided,
                               hardware configuration will be automatically configured by macOS
  - `speed` (int, optional): Configure speed of network port. Note that not all ports support all speeds.
                             Choices: 10, 100, 1000
  - `duplex` (str, optional): Configure duplex setting of network port. Note that not all ports support all settings,
                              and not all configurations support setting this at all. Choices: half-duplex, full-duplex
  - `flow_control` (bool, optional): Enable flow control for network port. Note that not all configurations support
                                     this. Required if `duplex` value is provided
  - `energy_efficient_ethernet` (bool, optional): Enable energy efficient ethernet for network port. Note that not all
                                                  configurations support this. Required if `duplex` value is provided
  - `mtu` (int, optional): MTU setting of network port. If not provided, default MTU setting will be used

Note that the following parameters are mutually exclusive:
- `dhcp`
- `dhcp_with_manual_address`
- `manual`

For `ipv6` option, the following parameters are mutually exclusive:
- `off`
- `automatic`
- `link_local`
- `manual`

## Returns

### Always Returned
- `changed` (bool): whether any changes were made to the network configurations
- `changelog` (list): list of changes made to the network configurations
- `commands_run` (list): list of `networksetup` commands run during configuration
- `available_hardware_ports` (list): list of information dictionaries describing hardware ports available on host
- `available_network_services` (list): list of information dictionaries describing network services available on host

### Returned on Failure
- `cmd` (str): `networksetup` command that was unable to run successfully
- `stdout` (str): Standard out of `networksetup` command that was unable to run successfully
- `stderr` (str): Standard err of `networksetup` command that was unable to run successfully

### Returned Conditionally Based on Configuration
- `valid_mtu_range_by_port` (dict): mapping from hardware port MAC address -> supported range of MTU values (min, max)
- `valid_media_by_port` (dict): mapping from hardware port MAC address -> list of dictionaries describing available
                                media configurations for the port (speed, duplex, flow control, energy efficient
                                ethernet)

## Examples

### Configure an interface for DHCP
```
- hosts: myhost.mydomain.com
  tasks:
    - name: Configure Ethernet for DHCP
      configure_network_interfaces:
        - mac_address: d8:ec:5e:11:77:c5
          dhcp: true
```

### Configure an interface for DHCP w/ manual IP address and set custom service name
```
- hosts: myhost.mydomain.com
  tasks:
    - name: Configure Ethernet static IP
      configure_network_interfaces:
        - name: Ethernet (Static IP)
          mac_address: d8:ec:5e:11:77:c5
          dhcp_with_manual_address:
            ip_address: 192.168.1.40
```

### Configure two interfaces, one for DHCP, one manually
```
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
```
