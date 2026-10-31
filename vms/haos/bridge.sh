#!/usr/bin/env bash
# Move the NAS's wired uplink onto a NetworkManager bridge so VMs can sit directly on the LAN.
#
# Usage: sudo vms/haos/bridge.sh [--dry-run]
#
# Idempotent: exits early when the bridge already carries the default route. Safe to run over SSH: before touching
# the uplink it arms a transient systemd timer that restores the original wired connection after ROLLBACK_SECS. The
# timer is cancelled automatically only when the bridge comes up with the *same* IPv4 address and can reach the
# gateway, so an SSH session survives (or, on failure, the old connection comes back on its own).
#
# Environment overrides:
#   BRIDGE         bridge interface / connection name (default: br0)
#   NIC            physical uplink (default: the current default-route interface)
#   ROLLBACK_SECS  seconds before the safety rollback fires (default: 180)
set -euo pipefail

BRIDGE="${BRIDGE:-br0}"
ROLLBACK_SECS="${ROLLBACK_SECS:-180}"
ROLLBACK_UNIT="${BRIDGE}-rollback"
ROLLBACK_SCRIPT="/run/${ROLLBACK_UNIT}.sh"
DRY_RUN=0

log() { printf '\033[1;34m[bridge]\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m[bridge]\033[0m %s\n' "$*"; }
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

# ipv4_of IFACE -> first IPv4 address (no prefix) on IFACE, or empty
ipv4_of() { ip -4 -o addr show dev "$1" 2>/dev/null | awk '{split($4, a, "/"); print a[1]; exit}'; }

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
command -v nmcli >/dev/null || die 'nmcli not found (NetworkManager is required)'

# ---------------------------------------------------------------------------
# Discover current state
# ---------------------------------------------------------------------------
default_dev="$(ip -4 route show default | awk '{print $5; exit}')"
if [[ "$default_dev" == "$BRIDGE" && -n "$(ipv4_of "$BRIDGE")" ]]; then
    ok "${BRIDGE} already carries the default route ($(ipv4_of "$BRIDGE")) — nothing to do"
    exit 0
fi

NIC="${NIC:-$default_dev}"
[[ -n "$NIC" && -e "/sys/class/net/${NIC}" ]] || die "Could not determine the uplink NIC (got '${NIC}'); set NIC=..."
mac="$(cat "/sys/class/net/${NIC}/address")"
old_ip="$(ipv4_of "$NIC")"
gateway="$(ip -4 route show default dev "$NIC" | awk '{print $3; exit}')"
old_con="$(nmcli -g GENERAL.CONNECTION device show "$NIC")"
[[ -n "$old_con" ]] || die "No active NetworkManager connection on ${NIC}"
port_con="${BRIDGE}-port-${NIC}"

log "Uplink:  ${NIC} (${mac}) via connection '${old_con}', IPv4 ${old_ip:-none}, gateway ${gateway:-none}"
log "Bridge:  ${BRIDGE} (will inherit ${NIC}'s MAC so DHCP hands back the same address)"

# ---------------------------------------------------------------------------
# Replace any stale bridge definition (e.g. a port bound to a renamed NIC)
# ---------------------------------------------------------------------------
bridge_uuid="$(nmcli -g UUID,NAME connection show | awk -F: -v n="$BRIDGE" '$2 == n {print $1}')"
while IFS=: read -r uuid _; do
    [[ -n "$uuid" ]] || continue
    master="$(nmcli -g connection.master connection show "$uuid")"
    if [[ -n "$master" && ("$master" == "$BRIDGE" || " ${bridge_uuid} " == *" ${master} "*) ]]; then
        log "Removing stale port connection $(nmcli -g connection.id connection show "$uuid")"
        run nmcli connection delete "$uuid"
    fi
done < <(nmcli -g UUID,NAME connection show)
for uuid in $bridge_uuid; do
    log "Removing stale bridge connection ${BRIDGE} (${uuid})"
    run nmcli connection delete "$uuid"
done

# ---------------------------------------------------------------------------
# Create bridge + port
# ---------------------------------------------------------------------------
client_id="$(nmcli -g ipv4.dhcp-client-id connection show "$old_con")"
run nmcli connection add type bridge con-name "$BRIDGE" ifname "$BRIDGE" \
    bridge.stp no bridge.mac-address "$mac" \
    ipv4.method auto ipv6.method auto \
    ${client_id:+ipv4.dhcp-client-id "$client_id"} \
    connection.autoconnect yes
run nmcli connection add type ethernet con-name "$port_con" ifname "$NIC" \
    master "$BRIDGE" slave-type bridge \
    connection.autoconnect yes connection.autoconnect-priority 10

# ---------------------------------------------------------------------------
# Arm rollback, then switch over
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == 0 ]]; then
    cat >"$ROLLBACK_SCRIPT" <<EOF
#!/bin/sh
# Restore '${old_con}' on ${NIC}; armed by $(realpath "$0")
nmcli connection modify $(printf %q "$BRIDGE") connection.autoconnect no
nmcli connection modify $(printf %q "$port_con") connection.autoconnect no
nmcli connection modify $(printf %q "$old_con") connection.autoconnect yes
nmcli connection up $(printf %q "$old_con")
nmcli connection down $(printf %q "$BRIDGE")
EOF
    chmod 0700 "$ROLLBACK_SCRIPT"
fi
[[ "$DRY_RUN" == 1 ]] || systemctl stop "${ROLLBACK_UNIT}.timer" 2>/dev/null || true
run systemd-run --unit="$ROLLBACK_UNIT" --on-active="$ROLLBACK_SECS" --timer-property=AccuracySec=1s \
    /bin/sh "$ROLLBACK_SCRIPT"
warn "Safety rollback armed: '${old_con}' is restored in ${ROLLBACK_SECS}s unless ${BRIDGE} comes up cleanly"

log 'Switching uplink onto the bridge (SSH may stall for a few seconds)...'
run nmcli connection modify "$old_con" connection.autoconnect no
# Activating the port takes the NIC from the old connection and brings the bridge up with it
run nmcli connection up "$port_con"

[[ "$DRY_RUN" == 0 ]] || exit 0

# ---------------------------------------------------------------------------
# Verify, then disarm
# ---------------------------------------------------------------------------
new_ip=''
for _ in $(seq 1 60); do
    new_ip="$(ipv4_of "$BRIDGE")"
    [[ -n "$new_ip" ]] && ping -c1 -W1 -I "$BRIDGE" "$gateway" >/dev/null 2>&1 && break
    new_ip=''
    sleep 1
done

if [[ -z "$new_ip" ]]; then
    die "${BRIDGE} did not get an address / reach ${gateway}; rollback fires in under ${ROLLBACK_SECS}s"
elif [[ -n "$old_ip" && "$new_ip" != "$old_ip" ]]; then
    die "${BRIDGE} came up as ${new_ip} (was ${old_ip}); leaving the rollback armed. Check the router's DHCP reservation, or run: systemctl stop ${ROLLBACK_UNIT}.timer to keep the new address"
fi

systemctl stop "${ROLLBACK_UNIT}.timer"
rm -f "$ROLLBACK_SCRIPT"
ok "${BRIDGE} is up as ${new_ip} via ${NIC}; rollback disarmed"
