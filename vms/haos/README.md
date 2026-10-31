[Project Root](../../README.md) > [VMs](../README.md) > **Home Assistant OS**

# Home Assistant OS VM

Runbook and scripts for running [Home Assistant OS](https://www.home-assistant.io/installation/linux) (HAOS) as a
libvirt/KVM virtual machine on the NAS. HAOS (unlike the plain `homeassistant/home-assistant` container) includes the
Supervisor, which provides apps (add-ons), managed backups, and in-place OS/Core updates.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Layout](#layout)
- [Fresh install](#fresh-install)
- [Re-bootstrapping a wiped NAS](#re-bootstrapping-a-wiped-nas)
- [Day-to-day operations](#day-to-day-operations)
- [Migrating from the Home Assistant container](#migrating-from-the-home-assistant-container)
- [Troubleshooting](#troubleshooting)
- [Remote access (not yet configured)](#remote-access-not-yet-configured)

<!-- mdformat-toc end -->

## Layout<a name="layout"></a>

| Piece            | Where                                               | Managed by                                               |
| ---------------- | --------------------------------------------------- | -------------------------------------------------------- |
| LAN bridge       | NetworkManager connections `br0` + `br0-port-<nic>` | [`bridge.sh`](bridge.sh)                                 |
| VM definition    | libvirt domain `haos` (`qemu:///system`)            | [`setup.sh`](setup.sh)                                   |
| VM disk          | `/var/lib/libvirt/images/haos.qcow2` (64 GB)        | [`setup.sh`](setup.sh) (created once, never overwritten) |
| Host shutdown    | `/etc/default/libvirt-guests`                       | [`setup.sh`](setup.sh)                                   |
| Docker exemption | `docker.service.d/10-bridge-forward.conf`           | [`setup.sh`](setup.sh)                                   |
| USB passthrough  | `/etc/udev/rules.d/90-haos-usb.rules` + `<hostdev>` | [`setup.sh`](setup.sh)                                   |
| Home Assistant   | inside the VM                                       | Home Assistant UI + its own backups                      |

The VM's NIC is bridged onto the LAN, so it gets its own DHCP address from the router and sees mDNS/SSDP broadcasts
exactly like a physical device (needed for discovery and for reaching the Lutron Caseta bridge). The host keeps its
address because `br0` inherits the physical NIC's MAC. libvirt's NAT `default` network (`virbr0`) is disabled since
nothing uses it.

Defaults: 2 vCPU, 4 GiB RAM, UEFI without Secure Boot, virtio-scsi disk, virtio NIC with pinned MAC `52:54:00:4b:e0:e5`,
QEMU guest-agent channel, autostart on. Override via the environment variables documented at the top of each script.

## Fresh install<a name="fresh-install"></a>

Both scripts are idempotent and accept `--dry-run`, which prints every mutating command without running it (and works
without sudo).

1. **Bridge the uplink.** Run from the local console or inside `tmux`, since the network blips for a few seconds:

   ```bash
   sudo vms/haos/bridge.sh
   ```

   A transient `br0-rollback` timer restores the original connection after 180 s unless `br0` comes up with the **same**
   IPv4 address and reaches the gateway, in which case the script disarms it. If the address changes, the script leaves
   the rollback armed and exits non-zero.

2. **Create and boot the VM:**

   ```bash
   sudo vms/haos/setup.sh
   ```

   It installs packages, downloads the pinned HAOS image (sha256-verified), grows it to 64 GB, defines the VM and starts
   it, then prints the address once the guest reports one. Log out and back in afterwards so the `libvirt` group
   membership applies.

3. **Reserve the VM's address** on the router for MAC `52:54:00:4b:e0:e5`, so its URL stays stable.

4. **Onboard** at `http://homeassistant.local:8123` (or the printed IP). First boot downloads the current Home Assistant
   Core, so the page takes a few minutes to appear. Pick *Create my smart home* to start fresh, or *Upload backup* to
   restore one.

5. **Set up backups.** Backups go to three places: the VM itself, the NAS, and Google Drive.

   - On the NAS, create the target folder once. It lives on its own dataset, so it can be snapshotted or capped
     separately:

     ```bash
     sudo zfs create storage/backups
     sudo mkdir -p /storage/backups/homeassistant && sudo chown -R "$USER:$USER" /storage/backups
     ```

   - In *Settings → System → Storage → Add network storage*, add `nas_backups` with usage **Backup**, server = the NAS's
     LAN IP, protocol Samba/Windows (CIFS), remote share `media/backups/homeassistant`, and user `connormason`. The
     password is the Samba password, set from the vault's `admin_password`.

   - Add the Google Drive integration. It shows up as a backup location.

   - In *Settings → System → Backups → Configure automatic backups*, schedule daily backups. Select *This system*,
     `nas_backups` and Google Drive as locations.

   - **Save the encryption key** (*Download emergency kit*) in the password manager. Backups cannot be restored without
     it.

   Keep the off-site copy: the `storage` pool stripes across two disks with no redundancy, so a single disk failure
   loses the NAS copy too.

## Re-bootstrapping a wiped NAS<a name="re-bootstrapping-a-wiped-nas"></a>

1. `./nas_bootstrap.sh` (Docker stack, Samba, ZFS import, Tailscale; see the [root README](../../README.md)).
2. `sudo vms/haos/bridge.sh`, then `sudo vms/haos/setup.sh`.
3. Re-create the router reservation if the router was also reset.
4. During onboarding choose *Upload backup*. Pick the newest `.tar` from `/storage/backups/homeassistant`, or from
   Google Drive if the pool was lost, and enter the encryption key from the emergency kit.

## Day-to-day operations<a name="day-to-day-operations"></a>

Commands below assume your user is in the `libvirt` group; otherwise prefix with `sudo`.

| Task                    | Command                                                     |
| ----------------------- | ----------------------------------------------------------- |
| Status                  | `virsh -c qemu:///system list --all`                        |
| VM address              | `virsh -c qemu:///system domifaddr haos --source agent`     |
| Serial console (HA CLI) | `virsh -c qemu:///system console haos` (exit with `Ctrl+]`) |
| Clean shutdown / start  | `virsh -c qemu:///system shutdown haos` / `... start haos`  |
| Autostart on / off      | `virsh -c qemu:///system autostart [--disable] haos`        |
| Resize RAM / vCPUs      | `virsh -c qemu:///system edit haos` while shut down         |

Setting `export LIBVIRT_DEFAULT_URI=qemu:///system` in your shell lets you drop the `-c` flag.

HAOS and Home Assistant Core update themselves from *Settings → System → Updates*. The `HAOS_VERSION` pinned in
[`setup.sh`](setup.sh) only decides which image a **fresh** install starts from. Bump it (with the release asset's
sha256 digest) when a rebuild would otherwise start several major versions behind.

USB radios (Zigbee, Z-Wave, Thread) need USB passthrough. [`setup.sh`](setup.sh) passes through every `vendor:product`
ID in `HAOS_USB` (find IDs with `lsusb`). The default is the ConBee II Zigbee stick (`1cf1:0030`). Devices are matched
by ID, not port, and marked optional, so the VM still boots without them. Re-run `sudo vms/haos/setup.sh` after adding
an ID. Inside Home Assistant the ConBee then appears as `/dev/serial/by-id/usb-dresden_elektronik_..._ConBee_II_...`. A
udev rule gives QEMU (user `libvirt-qemu`) write access to the device and tells ModemManager to ignore it. Without that
rule QEMU opens the device read-only: the guest sees it but cannot use it, and the host keeps `/dev/ttyACM0`. Once
passthrough works, that host node disappears.

## Migrating from the Home Assistant container<a name="migrating-from-the-home-assistant-container"></a>

This is a one-time step from the 2026-10 cutover. The container in [`services/homeassistant`](../../services/README.md)
is disabled in the repo (`compose.yml.disabled`), but neither the CI deploy nor `deploy.sh` stops or renames anything on
the NAS, so:

```bash
sudo docker rm -f home-assistant
mv ~/docker/homeassistant/compose.yml ~/docker/homeassistant/compose.yml.disabled
```

Stop the container **before** onboarding the VM so the two instances don't fight over discovered devices.

An earlier (July 2026) attempt left two `haos` domains behind. `setup.sh` refuses to run while they exist, so remove
them first:

```bash
sudo virsh -c qemu:///system undefine haos --nvram --remove-all-storage   # system VM + haos_ova-18.1.qcow2
virsh -c qemu:///session undefine haos --nvram                             # broken user-session copy
```

## Troubleshooting<a name="troubleshooting"></a>

- **VM boots but has no network.** Check `cat /proc/sys/net/bridge/bridge-nf-call-iptables`. If it exists and reads `1`,
  bridged frames are passing through Docker's `FORWARD` chain. Confirm the exemption rule is present with
  `sudo iptables -nL DOCKER-USER`. `setup.sh` installs it via a `docker.service` drop-in, so
  `sudo systemctl restart docker` re-applies it.
- **`bridge.sh` rolled back.** Inspect `journalctl -u br0-rollback` and `nmcli connection show`. The usual cause is the
  router handing `br0` a different address. Add a DHCP reservation for the host's MAC and re-run.
- **Stuck at the UEFI shell.** The VM must use the non-Secure-Boot `OVMF_CODE_4M.fd`. Check the `<loader>` element in
  `virsh dumpxml haos`.
- **Watching first boot.** `sudo virsh -c qemu:///system console haos` shows the HAOS boot log and, once up, the `ha`
  CLI prompt.

## Remote access (not yet configured)<a name="remote-access-not-yet-configured"></a>

Today the VM is reachable only on the LAN. The planned approach reuses the existing Tailscale + Caddy setup:

- Give the Caddy template a per-service `upstream` override, so a `tailscale_services` entry can point at the VM's LAN
  address instead of a container name. Expose Home Assistant on a dedicated port (e.g. `:8443`), since it cannot be
  served under a sub-path.
- In Home Assistant's `configuration.yaml` (via the File editor or Terminal app), set `http.use_x_forwarded_for: true`
  and add the `nas-network` subnet (`172.19.0.0/16`) to `http.trusted_proxies`.

The alternative is the official Tailscale app inside HAOS, which makes Home Assistant its own tailnet node with no host
changes. The trade-off is that its configuration then lives in HA backups rather than in this repo.
