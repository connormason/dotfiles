[Project Root](../README.md) > **VMs**

# VMs

Virtual machines that run on the NAS under libvirt/KVM, alongside (not inside) the Docker stack in
[`services/`](../services/README.md). Each subdirectory holds the scripts that provision one VM plus its runbook.
Provisioning is script-driven and run by hand on the NAS (`sudo vms/<name>/setup.sh`), not part of the Ansible
bootstrap.

| Directory        | VM                                                           |
| ---------------- | ------------------------------------------------------------ |
| [`haos/`](haos/) | Home Assistant OS, bridged onto the LAN with its own address |
