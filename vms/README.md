[Project Root](../README.md) > **VMs**

# VMs

Virtual machines that run on the NAS under libvirt/KVM, alongside (not inside) the Docker stack in
[`services/`](../services/README.md). Each subdirectory holds the scripts that provision one VM plus its runbook. The
NAS playbook's [`haos`](../roles/haos/README.md) role runs `vms/haos/setup.sh`, so the Home Assistant OS VM is part of
the Ansible bootstrap. Only `vms/haos/bridge.sh`, which blips the network for a few seconds, is run by hand on the NAS;
`sudo vms/haos/setup.sh` also works by hand.

| Directory        | VM                                                           |
| ---------------- | ------------------------------------------------------------ |
| [`haos/`](haos/) | Home Assistant OS, bridged onto the LAN with its own address |
