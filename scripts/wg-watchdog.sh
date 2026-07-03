#!/usr/bin/env bash
# WireGuard Tunnel Watchdog — auto-restart stale WG tunnels
#
# Monitors the WireGuard tunnel to the homelab. If the last handshake is older
# than the threshold AND the peer is unreachable, restarts the tunnel.
#
# Runs on the VPS (74.208.115.142) via cron.
#
# Cron (every 2 min):
#   */2 * * * * /opt/flowmanner/scripts/wg-watchdog.sh >> /var/log/wg-watchdog.log 2>&1
#
# Symptoms of a stale tunnel:
#   - `wg show wg0` shows `latest handshake` > threshold (default 5 min)
#   - `endpoint: 0.0.0.0:0` (peer lost its endpoint mapping)
#   - ping to homelab WireGuard IP fails
#
# Root cause: NAT tables on the homelab's router expire the UDP port mapping.
# PersistentKeepalive=5 should prevent this, but network disruptions (ISP
# resets, router reboots, extended packet loss) can still break it.

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────
INTERFACE="${WG_INTERFACE:-wg0}"
PEER_IP="${WG_PEER_IP:-10.99.0.3}"       # Homelab WireGuard IP
HANDSHAKE_THRESHOLD="${WG_HANDSHAKE_THRESHOLD:-300}"  # 5 minutes in seconds
PING_COUNT=2
PING_TIMEOUT=3
LOG_PREFIX="[wg-watchdog]"

# ── Helpers ───────────────────────────────────────────────────────────────

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

log()  { echo "$(timestamp) $LOG_PREFIX $*"; }
warn() { echo "$(timestamp) $LOG_PREFIX WARNING: $*"; }
crit() { echo "$(timestamp) $LOG_PREFIX CRITICAL: $*"; }

# Get the last handshake epoch for the first peer.
# `wg show <iface> latest-handshakes` outputs "<pubkey>\t<epoch>" per peer.
# Requires WireGuard >= 1.0.20210219 (epoch output).
get_last_handshake() {
    local pub_key
    pub_key=$(wg show "$INTERFACE" peers | head -1)

    if [[ -z "$pub_key" ]]; then
        echo "0"
        return
    fi

    local epoch
    epoch=$(wg show "$INTERFACE" latest-handshakes | awk -v pk="$pub_key" '$1 == pk { print $2 }')
    echo "${epoch:-0}"
}

# Convert a "time ago" string to seconds (approximate)
handshake_age_seconds() {
    local last_epoch="$1"
    if [[ "$last_epoch" == "0" ]]; then
        echo "999999"
        return
    fi
    local now
    now=$(date +%s)
    echo $(( now - last_epoch ))
}

# ── Main ──────────────────────────────────────────────────────────────────

main() {
    # 1. Check if WireGuard interface exists
    if ! ip link show "$INTERFACE" &>/dev/null; then
        crit "Interface $INTERFACE does not exist — cannot monitor"
        exit 1
    fi

    # 2. Get last handshake epoch
    local last_handshake
    last_handshake=$(get_last_handshake)
    local age
    age=$(handshake_age_seconds "$last_handshake")

    # 3. If handshake is fresh, tunnel is healthy — exit silently
    if (( age < HANDSHAKE_THRESHOLD )); then
        # Only log in verbose mode (when run manually)
        if [[ "${WG_VERBOSE:-0}" == "1" ]]; then
            log "Tunnel healthy (last handshake ${age}s ago, threshold ${HANDSHAKE_THRESHOLD}s)"
        fi
        exit 0
    fi

    # 4. Handshake is stale — verify with a ping before restarting
    warn "Stale handshake detected (${age}s ago, threshold ${HANDSHAKE_THRESHOLD}s)"

    if ping -c "$PING_COUNT" -W "$PING_TIMEOUT" "$PEER_IP" &>/dev/null; then
        log "Ping to $PEER_IP succeeded despite stale handshake — tunnel is working, no restart needed"
        exit 0
    fi

    # 5. Tunnel is confirmed broken — restart WireGuard
    crit "Ping to $PEER_IP failed — restarting WireGuard interface $INTERFACE"

    if systemctl restart "wg-quick@${INTERFACE}"; then
        log "WireGuard interface $INTERFACE restarted successfully"

        # 6. Verify the restart fixed the tunnel
        sleep 3
        if ping -c "$PING_COUNT" -W "$PING_TIMEOUT" "$PEER_IP" &>/dev/null; then
            log "Post-restart ping to $PEER_IP succeeded — tunnel restored"
        else
            crit "Post-restart ping to $PEER_IP still failing — manual intervention needed"
            exit 1
        fi
    else
        crit "Failed to restart WireGuard interface $INTERFACE — manual intervention needed"
        exit 1
    fi
}

main "$@"
