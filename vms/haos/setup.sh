#!/usr/bin/env bash
# Provision the Home Assistant OS VM on the NAS (libvirt/KVM, bridged onto the LAN).
#
# Usage: sudo vms/haos/setup.sh [--dry-run]
#
# Idempotent: every step checks current state first, and an existing VM disk is never overwritten. Requires the LAN
# bridge from bridge.sh. Steps:
#   1. install KVM / libvirt / OVMF packages and add the invoking user to the libvirt group
#   2. disable libvirt's NAT 'default' network (unused with a bridge; its dnsmasq holds :53, which blocks Pi-hole)
#   3. configure libvirt-guests to shut guests down cleanly when the host does
#   4. keep bridged traffic flowing if Docker's FORWARD-drop policy ever applies to it (br_netfilter)
#   5. download the pinned HAOS image (sha256-verified), decompress and grow it to HAOS_DISK_SIZE
#   6. define the VM with virt-install, mark it autostart, and start it
#
# Environment overrides:
#   HAOS_NAME       libvirt domain name (default: haos)
#   HAOS_MEMORY     MiB of RAM (default: 4096)
#   HAOS_VCPUS      vCPU count (default: 2)
#   HAOS_DISK_SIZE  virtual disk size for a fresh image (default: 64G)
#   HAOS_MAC        NIC MAC address; pin it so the router's DHCP reservation survives a rebuild
#   BRIDGE          host bridge to attach to (default: br0)
set -euo pipefail

# Initial install image only: HAOS updates itself in place afterwards (Settings -> System -> Updates). To bump, take
# the version and the asset's sha256 digest from https://github.com/home-assistant/operating-system/releases.
HAOS_VERSION='18.4'
HAOS_SHA256='756ec485b1b153099ca53e88a5eebd63a801d56b791afe5c6d63ef94a35dc02d' # pragma: allowlist secret
HAOS_URL="https://github.com/home-assistant/operating-system/releases/download/${HAOS_VERSION}/haos_ova-${HAOS_VERSION}.qcow2.xz"

HAOS_NAME="${HAOS_NAME:-haos}"
HAOS_MEMORY="${HAOS_MEMORY:-4096}"
HAOS_VCPUS="${HAOS_VCPUS:-2}"
HAOS_DISK_SIZE="${HAOS_DISK_SIZE:-64G}"
HAOS_MAC="${HAOS_MAC:-52:54:00:4b:e0:e5}"
BRIDGE="${BRIDGE:-br0}"

LIBVIRT_URI='qemu:///system'
IMAGES_DIR='/var/lib/libvirt/images'
DISK="${IMAGES_DIR}/${HAOS_NAME}.qcow2"
OVMF_CODE='/usr/share/OVMF/OVMF_CODE_4M.fd' # non-Secure-Boot firmware; HAOS images are not MS-signed
OVMF_VARS='/usr/share/OVMF/OVMF_VARS_4M.fd'
PACKAGES=(qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients virtinst ovmf xz-utils curl)
DRY_RUN=0

log() { printf '\033[1;34m[haos]\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m[haos]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die() {
    printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2
    exit 1
}

# run CMD... -> the single mutation chokepoint. Under --dry-run, print only.
run() {
    if [[ "$DRY_RUN" == 1 ]]; then
        printf '\033[2m[dry-run]\033[0m %s\n' "$*"
        return 0
    fi
    "$@"
}

# write_if_changed PATH CONTENT -> write PATH only when its content differs; succeeds if it wrote
write_if_changed() {
    local path="$1" content="$2"
    [[ -f "$path" && "$(cat "$path")" == "$content" ]] && return 1
    if [[ "$DRY_RUN" == 1 ]]; then
        printf '\033[2m[dry-run]\033[0m write %s:\n%s\n' "$path" "$content"
    else
        mkdir -p "$(dirname "$path")"
        printf '%s\n' "$content" >"$path"
    fi
}

# Read-only libvirt socket: works for root and (under --dry-run) unprivileged users alike
virsh_ro() { virsh -r -c "$LIBVIRT_URI" "$@"; }

for arg in "$@"; do
    case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h | --help)
        sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'
        exit 0
        ;;
    *) die "Unknown argument: $arg" ;;
    esac
done

[[ "$DRY_RUN" == 1 || "$EUID" -eq 0 ]] || die 'Run as root (sudo), or pass --dry-run'
[[ -e /dev/kvm ]] || die '/dev/kvm missing: enable SVM/VT-x in firmware and load kvm_amd/kvm_intel'
[[ -n "$(ip -4 -o addr show dev "$BRIDGE" 2>/dev/null)" ]] ||
    die "Bridge ${BRIDGE} has no IPv4 address; run vms/haos/bridge.sh first"

# ---------------------------------------------------------------------------
# 1. Packages and group membership
# ---------------------------------------------------------------------------
missing=()
for pkg in "${PACKAGES[@]}"; do
    [[ "$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null)" == 'install ok installed' ]] || missing+=("$pkg")
done
if ((${#missing[@]})); then
    log "Installing: ${missing[*]}"
    run apt-get update
    run env DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
else
    ok 'Virtualization packages already installed'
fi
run systemctl enable --now libvirtd.service libvirt-guests.service

user="${SUDO_USER:-}"
if [[ -n "$user" && "$user" != root ]]; then
    if [[ " $(id -nG "$user") " == *' libvirt '* ]]; then
        ok "${user} already in the libvirt group"
    else
        run usermod -aG libvirt "$user"
        warn "Added ${user} to the libvirt group; log out and back in to use virsh without sudo"
    fi
fi

# ---------------------------------------------------------------------------
# 2. libvirt 'default' NAT network
# ---------------------------------------------------------------------------
if net_info="$(virsh_ro net-info default 2>/dev/null)"; then
    if grep -qE '^Active:\s+yes' <<<"$net_info"; then
        run virsh -c "$LIBVIRT_URI" net-destroy default
    fi
    if grep -qE '^Autostart:\s+yes' <<<"$net_info"; then
        run virsh -c "$LIBVIRT_URI" net-autostart default --disable
    fi
    ok "libvirt 'default' network stopped and not autostarting"
fi

# ---------------------------------------------------------------------------
# 3. Clean guest shutdown with the host
# ---------------------------------------------------------------------------
# ON_BOOT=ignore: the domain's own autostart flag starts it; libvirt-guests only handles shutdown.
if write_if_changed /etc/default/libvirt-guests "# Managed by dotfiles vms/haos/setup.sh
ON_BOOT=ignore
ON_SHUTDOWN=shutdown
SHUTDOWN_TIMEOUT=300"; then
    log 'Wrote /etc/default/libvirt-guests'
else
    ok '/etc/default/libvirt-guests up to date'
fi

# ---------------------------------------------------------------------------
# 4. Docker vs. bridged traffic
# ---------------------------------------------------------------------------
# Docker sets the FORWARD policy to DROP. If br_netfilter is ever loaded, frames crossing the bridge traverse that
# chain and the VM silently loses the LAN. DOCKER-USER is Docker's supported hook for exempting traffic; the leading
# '-' keeps a failure here from failing docker.service.
if systemctl list-unit-files docker.service >/dev/null 2>&1; then
    rule="DOCKER-USER -i ${BRIDGE} -o ${BRIDGE} -j ACCEPT"
    if write_if_changed /etc/systemd/system/docker.service.d/10-bridge-forward.conf "# Managed by dotfiles vms/haos/setup.sh
[Service]
ExecStartPost=-/bin/sh -c 'iptables -w -C ${rule} 2>/dev/null || iptables -w -I ${rule}'"; then
        run systemctl daemon-reload
        log 'Installed docker.service drop-in for bridged forwarding'
    else
        ok 'docker.service bridge-forward drop-in up to date'
    fi
    # Apply now too, without restarting Docker (and every container with it)
    if [[ "$DRY_RUN" == 0 ]] && iptables -w -nL DOCKER-USER >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        iptables -w -C $rule 2>/dev/null || iptables -w -I $rule
    fi
fi

# ---------------------------------------------------------------------------
# 5. Disk image
# ---------------------------------------------------------------------------
if [[ -f "$DISK" ]]; then
    ok "Disk ${DISK} exists; leaving it untouched"
else
    avail_gb="$(df --output=avail -BG "$IMAGES_DIR" | tail -1 | tr -dc '0-9')"
    ((avail_gb >= 40)) || warn "Only ${avail_gb}G free under ${IMAGES_DIR}; the disk grows towards ${HAOS_DISK_SIZE}"

    xz_path="${IMAGES_DIR}/haos_ova-${HAOS_VERSION}.qcow2.xz"
    if [[ ! -f "$xz_path" ]]; then
        log "Downloading HAOS ${HAOS_VERSION}"
        run curl -fL --retry 3 --progress-bar -o "${xz_path}.part" "$HAOS_URL"
        run mv "${xz_path}.part" "$xz_path"
    fi
    if [[ "$DRY_RUN" == 0 ]]; then
        actual="$(sha256sum "$xz_path" | awk '{print $1}')"
        if [[ "$actual" != "$HAOS_SHA256" ]]; then
            rm -f "$xz_path"
            die "Checksum mismatch for ${xz_path} (got ${actual}); deleted it"
        fi
        ok 'Image checksum verified'
        log 'Decompressing...'
        xz -dc "$xz_path" >"${DISK}.part"
    fi
    run qemu-img resize "${DISK}.part" "$HAOS_DISK_SIZE"
    run mv "${DISK}.part" "$DISK"
    run rm -f "$xz_path"
fi

# ---------------------------------------------------------------------------
# 6. VM definition
# ---------------------------------------------------------------------------
if virsh_ro dominfo "$HAOS_NAME" >/dev/null 2>&1; then
    current_disk="$(virsh_ro domblklist "$HAOS_NAME" --details | awk '$2 == "disk" {print $4; exit}')"
    [[ "$current_disk" == "$DISK" ]] ||
        die "A '${HAOS_NAME}' VM already exists using ${current_disk}; remove it first (see vms/haos/README.md)"
    ok "VM '${HAOS_NAME}' already defined"
    if ! grep -qE '^Autostart:\s+enable' <<<"$(virsh_ro dominfo "$HAOS_NAME")"; then
        run virsh -c "$LIBVIRT_URI" autostart "$HAOS_NAME"
    fi
    if [[ "$(virsh_ro domstate "$HAOS_NAME")" != running ]]; then
        run virsh -c "$LIBVIRT_URI" start "$HAOS_NAME"
    fi
else
    log "Defining VM '${HAOS_NAME}' (${HAOS_VCPUS} vCPU, ${HAOS_MEMORY} MiB, ${BRIDGE}, MAC ${HAOS_MAC})"
    run virt-install --connect "$LIBVIRT_URI" \
        --name "$HAOS_NAME" --description 'Home Assistant OS' \
        --osinfo generic --machine q35 \
        --memory "$HAOS_MEMORY" --vcpus "$HAOS_VCPUS" --cpu host-passthrough \
        --boot "loader=${OVMF_CODE},loader.readonly=yes,loader.type=pflash,nvram.template=${OVMF_VARS}" \
        --controller type=scsi,model=virtio-scsi \
        --disk "path=${DISK},format=qcow2,bus=scsi,discard=unmap" \
        --network "bridge=${BRIDGE},model=virtio,mac=${HAOS_MAC}" \
        --channel unix,target.type=virtio,target.name=org.qemu.guest_agent.0 \
        --graphics none --console pty,target.type=serial \
        --import --autostart --noautoconsole
fi

[[ "$DRY_RUN" == 0 ]] || exit 0

# ---------------------------------------------------------------------------
# Report the VM's address (guest agent first, then the host's ARP table)
# ---------------------------------------------------------------------------
log 'Waiting for the VM to report an address (first boot takes a minute or two)...'
vm_ip=''
for _ in $(seq 1 60); do
    for source in agent arp; do
        vm_ip="$(virsh_ro domifaddr "$HAOS_NAME" --source "$source" 2>/dev/null |
            awk '$3 == "ipv4" && $4 !~ /^127\./ {split($4, a, "/"); print a[1]; exit}')"
        [[ -n "$vm_ip" ]] && break 2
    done
    sleep 3
done

if [[ -n "$vm_ip" ]]; then
    ok "Home Assistant OS is booting at http://${vm_ip}:8123 (also http://homeassistant.local:8123)"
else
    warn 'No address yet; check the router for MAC '"${HAOS_MAC}"', or watch boot with: sudo virsh console '"${HAOS_NAME}"
fi
log 'First boot downloads the latest Home Assistant Core; the onboarding page appears when it finishes.'
