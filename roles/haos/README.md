[Project Root](../../README.md) > [Roles](../README.md) > **haos**

# haos

Runs [`vms/haos/setup.sh`](../../vms/haos/README.md) from the NAS clone to converge the Home Assistant OS VM (KVM
packages, libvirt settings, the Docker bridge exemption, the VM itself). The script stays the implementation; the role
only checks preconditions and maps Ansible's modes onto it.

| Behaviour  | Detail                                                                                                             |
| ---------- | ------------------------------------------------------------------------------------------------------------------ |
| LAN bridge | Fails with instructions when `haos_bridge` has no IPv4 address. It never runs `bridge.sh`, which blips the network |
| Changed    | From the script's `haos: changes=N` line                                                                           |
| Check mode | Runs `setup.sh --dry-run` (read-only)                                                                              |
| Long runs  | The script runs async (1 h limit, polled every 15 s), since a fresh host downloads the HAOS image                  |
| Depends on | The [`dotfiles`](../dotfiles/README.md) role, for the clone at `dotfiles_repo_dir`                                 |

## Variables

| Variable            | Default                                 | Purpose                   |
| ------------------- | --------------------------------------- | ------------------------- |
| `haos_bridge`       | `br0`                                   | Bridge the VM attaches to |
| `haos_setup_script` | `<dotfiles_repo_dir>/vms/haos/setup.sh` | Script to run             |
