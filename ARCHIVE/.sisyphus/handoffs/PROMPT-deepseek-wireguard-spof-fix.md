# Task: Fix WireGuard SPOF — Watchdog + Nginx Graceful Degradation

**Date:** 2026-07-01
**Estimated effort:** 2–3 hours
**Priority:** Medium — zero users today, but once there are paying customers, tunnel downtime = total API outage.

---

## 0. ⚠️ INFRASTRUCTURE WARNING

This task touches **two machines** and the **Docker nginx container** on the VPS. You are NOT working in a Python backend repo. There are no tests to run — verification is done by **simulating failures** and observing recovery.

| Machine | Access | Working directory |
|---------|--------|-------------------|
| VPS | `ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142` | `/opt/flowmanner/` |
| Homelab | Local (you're on it) | `/` (system-level files) |

**CRITICAL:** Every SSH command to the VPS MUST use the key path above. Do NOT use `ssh root@74.208.115.142` without the key — it will hang waiting for a password.

**CRITICAL:** Every VPS command that touches the flowmanner project MUST `cd /opt/flowmanner` first. Running `docker compose` without this will fail with "no configuration file provided".

## 1. Context — current WireGuard architecture

### Topology

```
VPS (74.208.115.142)          Homelab (176.141.9.146)
  WireGuard IP: 10.99.0.1       WireGuard IP: 10.99.0.3
  ListenPort: 51820              ListenPort: 51820
  Endpoint: (none — passive)     Endpoint: 74.208.115.142:51820
  PersistentKeepalive: 5         PersistentKeepalive: 5
```

### Key facts (verified 2026-07-01)

1. **Homelab is behind NAT/CGNAT.** Its public IP `176.141.9.146` has port 51820 **not directly reachable** from the VPS (`nc -z` fails). WireGuard works because the **homelab initiates outbound** and NAT keeps the mapping alive via PersistentKeepalive=5.

2. **The VPS is passive** — it has `Endpoint = 176.141.9.146:51820` for the homelab peer, but this is a **learned endpoint** that updates from incoming packets. If the homelab's NAT mapping changes (ISP reconnect, CGNAT rebinding, router reboot), the VPS sends to a stale endpoint until the homelab re-initiates.

3. **`wg-quick@.service` is Type=oneshot, RemainAfterExit=yes, Restart=no.** If WireGuard crashes or the handshake goes stale, nothing restarts it automatically.

4. **Homelab has `WG_ENDPOINT_RESOLUTION_RETRIES=infinity`** in its systemd drop-in. This means `wg-quick up` will retry DNS resolution forever if the VPS IP is unreachable at boot — good.

5. **Nginx proxies `/api/*` to `10.99.0.3:8000`** and `/ws` to `10.99.0.3:8000/ws`. If the tunnel is down, Nginx returns raw **502 Bad Gateway** — no maintenance page, no retry, no user-friendly fallback.

6. **Zero monitoring exists.** No watchdog, no cron job, no systemd timer for WireGuard health. The only cron is `check-certs.sh` for TLS certificate expiry.

### Failure modes

| Scenario | What happens today | Recovery time |
|----------|-------------------|---------------|
| Homelab WireGuard process crashes | Service goes to `inactive`. No auto-restart. Tunnel dead until manual `systemctl restart wg-quick@wg0` on homelab. | ∞ (manual) |
| Homelab ISP reconnects / CGNAT rebinding | Homelab's public IP changes. VPS sends to stale endpoint. Homelab re-initiates from new IP → VPS learns new endpoint from incoming handshake. | 5–60s (automatic, but unmonitored) |
| Homelab reboots | WireGuard comes back up via `enabled` systemd. Re-initiates to VPS. | ~30s (automatic) |
| VPS WireGuard crashes | Homelab's packets go nowhere. VPS nginx returns 502. | ∞ (manual) |
| WireGuard handshake goes stale (no crash) | Interface is `UP` but no traffic flows. Both sides think it's fine. Nginx returns 502. | ∞ (undetected) |

### What this task fixes

| Layer | What | Effect |
|-------|------|--------|
| **Detection** | Watchdog scripts on both machines check tunnel health every 60s | Stale/dead tunnel detected within 1 min |
| **Recovery** | Auto-restart WireGuard on failure | Tunnel recovers in 10–30s |
| **User experience** | Nginx serves maintenance page on 502/504 | Users see "temporarily unavailable" instead of raw error |

## 2. Why this is safe

- **No Python code changes.** No backend, no frontend, no schema, no migrations.
- **No WireGuard config changes.** The `wg0.conf` files stay exactly as they are.
- **Additive only.** New scripts + new systemd timers + nginx config tweak. Nothing is deleted or modified in existing services.
- **Fail-safe.** If the watchdog scripts have bugs, the worst case is they don't restart WireGuard — same as today. They cannot make the tunnel worse.

## 3. Files to create/modify

| # | File | Machine | Action |
|---|------|---------|--------|
| 1 | `/opt/flowmanner/scripts/wg-watchdog.sh` | VPS | **Create** — bash watchdog script |
| 2 | `/etc/systemd/system/wg-watchdog.service` | VPS | **Create** — systemd service unit |
| 3 | `/etc/systemd/system/wg-watchdog.timer` | VPS | **Create** — systemd timer (every 60s) |
| 4 | `/opt/flowmanner/nginx/maintenance.html` | VPS | **Create** — static maintenance page |
| 5 | `/opt/flowmanner/nginx/default.conf` | VPS | **Modify** — add `error_page 502 504` + `proxy_intercept_errors` |
| 6 | `/usr/local/bin/wg-watchdog.sh` | Homelab | **Create** — bash watchdog script |
| 7 | `/etc/systemd/system/wg-watchdog.service` | Homelab | **Create** — systemd service unit |
| 8 | `/etc/systemd/system/wg-watchdog.timer` | Homelab | **Create** — systemd timer (every 60s) |

Total: 7 new files, 1 modified file.

## 4. Detailed requirements

### 4.1 VPS watchdog — `/opt/flowmanner/scripts/wg-watchdog.sh`

```bash
#!/usr/bin/env bash
# wg-watchdog.sh — WireGuard tunnel health monitor for VPS
# Checks handshake freshness with homelab peer. If stale, clears
# the endpoint so the next inbound packet from homelab re-establishes.
# Logs to /var/log/wg-watchdog.log

set -euo pipefail

LOG_FILE=/var/log/wg-watchdog.log
STALE_THRESHOLD=120  # seconds — 2 missed keepalives
HOMELAB_PUBKEY="AdZG7G7cwaYTIUB9CyF2FxxwQWUyQLab+VWIkM9rMEI="

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"; }

# Get latest handshake timestamp for homelab peer
handshake=$(wg show wg0 latest-handshakes | grep "$HOMELAB_PUBKEY" | awk '{print $2}')

if [ -z "$handshake" ]; then
    log "ERROR: Could not read handshake for homelab peer"
    exit 1
fi

now=$(date +%s)

# handshake=0 means never connected
if [ "$handshake" -eq 0 ]; then
    log "WARNING: No handshake ever recorded for homelab peer"
    exit 0
fi

age=$(( now - handshake ))

if [ "$age" -gt "$STALE_THRESHOLD" ]; then
    log "STALE: Handshake is ${age}s old (threshold: ${STALE_THRESHOLD}s). Clearing endpoint to accept re-handshake."
    # Clear the learned endpoint so VPS accepts the next packet from
    # any source IP (homelab may have a new NAT mapping).
    wg set wg0 peer "$HOMELAB_PUBKEY" endpoint 0.0.0.0:0
    log "RECOVERY: Endpoint cleared. Waiting for homelab to re-initiate."
else
    # Only log every 5th check to avoid log spam (i.e. every ~5 min)
    if (( age % 300 < 60 )); then
        log "OK: Handshake is ${age}s old"
    fi
fi
```

**Key design decisions:**

- **Does NOT restart `wg-quick@wg0`** — that would tear down the entire interface and disconnect all peers. Instead, `wg set peer ... endpoint 0.0.0.0:0` clears the stale learned endpoint so the VPS accepts the next handshake from any source IP.
- **120s threshold** = 2 missed keepalives (keepalive is every 5s, but we give a generous window for transient network blips).
- **Logs to `/var/log/wg-watchdog.log`** — matches the `check-certs.sh` pattern.
- **Does NOT attempt to reach the homelab** — the VPS can't initiate to the homelab (NAT). It can only wait for the homelab to reconnect.

### 4.2 VPS systemd units

**`/etc/systemd/system/wg-watchdog.service`:**

```ini
[Unit]
Description=WireGuard tunnel watchdog (VPS side)
After=wg-quick@wg0.service

[Service]
Type=oneshot
ExecStart=/opt/flowmanner/scripts/wg-watchdog.sh
StandardOutput=journal
StandardError=journal
```

**`/etc/systemd/system/wg-watchdog.timer`:**

```ini
[Unit]
Description=Run WireGuard watchdog every 60 seconds

[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5

[Install]
WantedBy=timers.target
```

### 4.3 Homelab watchdog — `/usr/local/bin/wg-watchdog.sh`

```bash
#!/usr/bin/env bash
# wg-watchdog.sh — WireGuard tunnel health monitor for Homelab
# Pings the VPS through the tunnel. If unreachable, restarts WireGuard.
# Logs to /var/log/wg-watchdog.log

set -euo pipefail

LOG_FILE=/var/log/wg-watchdog.log
VPS_WG_IP="10.99.0.1"
PING_TIMEOUT=5
FAIL_THRESHOLD=2  # consecutive failures before restart

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"; }

# Track consecutive failures in a state file
STATE_FILE=/var/run/wg-watchdog-failures

if ping -c 1 -W "$PING_TIMEOUT" "$VPS_WG_IP" > /dev/null 2>&1; then
    # Tunnel is healthy
    if [ -f "$STATE_FILE" ]; then
        count=$(cat "$STATE_FILE")
        if [ "$count" -ge "$FAIL_THRESHOLD" ]; then
            log "RECOVERED: Tunnel is back after ${count} consecutive failures"
        fi
        rm -f "$STATE_FILE"
    fi
    exit 0
fi

# Ping failed — increment failure count
if [ -f "$STATE_FILE" ]; then
    count=$(( $(cat "$STATE_FILE") + 1 ))
else
    count=1
fi
echo "$count" > "$STATE_FILE"

log "FAIL: Ping to ${VPS_WG_IP} failed (consecutive failures: ${count})"

if [ "$count" -ge "$FAIL_THRESHOLD" ]; then
    log "RESTART: ${count} consecutive failures. Restarting wg-quick@wg0"
    systemctl restart wg-quick@wg0
    log "RESTART: wg-quick@wg0 restarted. Waiting for reconnection."
    # Reset counter after restart attempt
    rm -f "$STATE_FILE"
fi
```

**Key design decisions:**

- **Pings through the tunnel** (`10.99.0.1`) — the most reliable check. If ping fails, the tunnel is genuinely dead.
- **2 consecutive failures before restart** — avoids restarting on a single transient blip. With 60s check interval, that's 2 minutes of confirmed downtime before action.
- **Tracks state in `/var/run/`** (tmpfs) — survives reboots as a fresh start, doesn't accumulate stale state.
- **Restarts `wg-quick@wg0`** — this is the clean way. `wg-quick down wg0 && wg-quick up wg0` tears down and re-creates the interface. The homelab re-initiates the handshake to the VPS, and the VPS learns the new endpoint.
- **Does NOT restart if the homelab itself has no network** — ping to `10.99.0.1` will fail, but so will the restart. The homelab will keep retrying on its own once network is back.

### 4.4 Homelab systemd units

**`/etc/systemd/system/wg-watchdog.service`:**

```ini
[Unit]
Description=WireGuard tunnel watchdog (Homelab side)
After=wg-quick@wg0.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/wg-watchdog.sh
StandardOutput=journal
StandardError=journal
```

**`/etc/systemd/system/wg-watchdog.timer`:**

```ini
[Unit]
Description=Run WireGuard watchdog every 60 seconds

[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5

[Install]
WantedBy=timers.target
```

### 4.5 Nginx maintenance page — `/opt/flowmanner/nginx/maintenance.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Flowmanner — Temporarily Unavailable</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0a0a0a; color: #e5e5e5;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; padding: 2rem;
        }
        .container { max-width: 480px; text-align: center; }
        h1 { font-size: 1.5rem; margin-bottom: 1rem; color: #fff; }
        p { color: #a3a3a3; line-height: 1.6; margin-bottom: 0.5rem; }
        .status { color: #f59e0b; font-weight: 600; margin: 1.5rem 0; }
        .retry { margin-top: 2rem; }
        .retry a {
            display: inline-block; padding: 0.75rem 2rem;
            background: #2563eb; color: #fff; text-decoration: none;
            border-radius: 0.5rem; font-weight: 500;
        }
        .retry a:hover { background: #1d4ed8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Temporarily Unavailable</h1>
        <p class="status">We're reconnecting to the backend.</p>
        <p>This usually resolves within a minute. If it persists, the backend may be undergoing maintenance.</p>
        <div class="retry"><a href="/">Try Again</a></div>
    </div>
</body>
</html>
```

### 4.6 Nginx config modification — `/opt/flowmanner/nginx/default.conf`

Add to the **main `server` block** (the `listen 443 ssl` one), inside the block, before the first `location`:

```nginx
    # ── Maintenance page when backend is unreachable ──────────────────
    proxy_intercept_errors on;
    error_page 502 504 /maintenance.html;

    location = /maintenance.html {
        root /etc/nginx;
        internal;
    }
```

**Also** add a volume mount to the nginx service in `docker-compose.yml`:

```yaml
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/maintenance.html:/etc/nginx/maintenance.html:ro
      - /var/www/certbot:/var/www/certbot:ro
      - ./certs:/etc/nginx/certs:ro
```

**Design notes:**

- `proxy_intercept_errors on` tells Nginx to handle 502/504 from upstream instead of passing them to the client.
- `error_page 502 504 /maintenance.html` serves the static page for both error codes.
- The `location = /maintenance.html { internal; }` block serves the file from `/etc/nginx/` inside the container, mounted from the host. `internal` prevents direct access to the URL.
- The maintenance page is intentionally dark-themed to match Flowmanner's UI.
- **This does NOT affect `/api/auth/`** routes that proxy to the frontend container — those are on a different upstream (`frontend:3000`) and won't produce 502/504 unless the frontend itself is down.

## 5. Constraints (HARD)

1. **Do NOT modify `/etc/wireguard/wg0.conf`** on either machine. The tunnel config is correct as-is.
2. **Do NOT restart WireGuard during implementation.** The tunnel is live and serving traffic. Only the watchdog timers should ever trigger a restart.
3. **Do NOT use `docker compose restart nginx`** without `cd /opt/flowmanner &&` first. This is a recurring mistake — see AGENTS.md.
4. **Do NOT change nginx proxy behavior for healthy backends.** The `proxy_intercept_errors on` only activates when upstream returns 502/504. Normal 200/401/404/500 responses pass through unchanged.
5. **Do NOT add the maintenance.html to the frontend container.** It goes in the nginx container as a static file.
6. **Test the watchdog scripts manually before enabling the timers.** Run each script directly and verify it produces expected log output.
7. **Homelab watchdog uses `sudo` for `systemctl restart`.** The script must be runnable by root (the systemd service runs as root).
8. **Do NOT log every 60s check on the VPS watchdog** — that would produce 1440 lines/day of "OK" noise. Log only on state transitions (stale, recovered, error).

## 6. Verification — MUST do, MUST paste output

### 6.1 VPS watchdog test

```bash
# Deploy the script
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "cat /opt/flowmanner/scripts/wg-watchdog.sh"

# Run it manually (should log OK or STALE based on current handshake)
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "bash /opt/flowmanner/scripts/wg-watchdog.sh && cat /var/log/wg-watchdog.log | tail -5"

# Enable the timer
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "systemctl daemon-reload && systemctl enable --now wg-watchdog.timer && systemctl status wg-watchdog.timer"
```

### 6.2 Homelab watchdog test

```bash
# Deploy the script
cat /usr/local/bin/wg-watchdog.sh

# Run it manually (should succeed — tunnel is currently healthy)
sudo bash /usr/local/bin/wg-watchdog.sh
sudo cat /var/log/wg-watchdog.log | tail -5

# Enable the timer
sudo systemctl daemon-reload
sudo systemctl enable --now wg-watchdog.timer
sudo systemctl status wg-watchdog.timer
```

### 6.3 Nginx maintenance page test

```bash
# Deploy updated nginx config + maintenance page
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "cd /opt/flowmanner && docker compose up -d --no-deps nginx"

# Test maintenance page is accessible (should return the HTML)
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "docker exec flowmanner-nginx cat /etc/nginx/maintenance.html | head -5"

# Test that normal traffic still works (should return 200)
curl -s -o /dev/null -w '%{http_code}' https://flowmanner.com/api/health

# Simulate backend-down by temporarily blocking the WireGuard IP on VPS
# (DO NOT do this unless you know how to undo it — see §7)
```

### 6.4 Timer persistence across reboot

```bash
# VPS
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "systemctl is-enabled wg-watchdog.timer"

# Homelab
systemctl is-enabled wg-watchdog.timer
```

Both must return `enabled`.

## 7. Failure simulation (OPTIONAL — do this only if you want to prove it works)

**⚠️ This temporarily breaks the tunnel. Only do it during a maintenance window.**

### Test homelab watchdog recovery:

```bash
# On homelab — kill WireGuard
sudo wg-quick down wg0

# Wait 2 minutes (2 consecutive failures × 60s interval)
# Check the log
sudo cat /var/log/wg-watchdog.log | tail -10

# The watchdog should have restarted WireGuard. Verify:
sudo wg show wg0
ping -c 3 10.99.0.1
```

### Test VPS watchdog endpoint clearing:

```bash
# On VPS — manually set a stale endpoint to force the watchdog to clear it
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "wg set wg0 peer AdZG7G7cwaYTIUB9CyF2FxxwQWUyQLab+VWIkM9rMEI= endpoint 192.0.2.1:51820"

# Wait 2+ minutes for the watchdog to detect stale handshake
# Check the log
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "cat /var/log/wg-watchdog.log | tail -5"

# The watchdog should have cleared the endpoint. Verify:
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "wg show wg0 | grep -A3 'peer: AdZG7'"

# Homelab should reconnect within seconds. Verify from homelab:
ping -c 3 10.99.0.1
```

### Test nginx maintenance page:

```bash
# On VPS — temporarily stop the WireGuard interface to simulate tunnel down
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "wg-quick down wg0"

# Hit the API from outside (should return maintenance page, not raw 502)
curl -s https://flowmanner.com/api/health | head -5

# Restore WireGuard
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "wg-quick up wg0"
```

## 8. Handoff format

Write to `.sisyphus/handoffs/exit-audit-2026-07-01-wireguard-spof-fix.md`:

1. **What changed** — file-by-file, which machine, what it does.
2. **Verification output** — paste the raw output from §6.1–6.4.
3. **Timer status** — both timers active and enabled, paste `systemctl status` output.
4. **Log samples** — paste 5 lines from each watchdog log.
5. **What is NOT done** — explicitly say "no WireGuard config changes, no backend/frontend code changes, no new dependencies."
6. **Follow-up items** (surfaced, not blocking):
   - Log rotation for `/var/log/wg-watchdog.log` (add logrotate config)
   - Telegram/email alerting when watchdog triggers (currently just logs)
   - The second VPS peer (`P6rLB47g3N3LF9ktTnwfZ7XsJShaHaoQHDVt67KyIkc=` at `10.99.0.4`) has never handshaked — is it still needed?

## 9. Stop-the-line rules

- **If `wg set peer ... endpoint 0.0.0.0:0` doesn't work** (some WireGuard versions reject it), fall back to `wg set wg0 peer <pubkey> endpoint [::]:0` (IPv6 wildcard). If that also fails, the VPS watchdog should log and skip the clear — the homelab watchdog is the primary recovery mechanism.
- **If `proxy_intercept_errors on` breaks existing error handling** (e.g., the frontend returns intentional 502s for some routes), test each route type and scope the interception if needed.
- **If the homelab doesn't have `sudo` access for `systemctl restart`**, the watchdog must run as root via the systemd service. Do NOT add a sudoers rule — systemd runs the service as root by default.
- **If `docker compose up -d --no-deps nginx` fails**, check `docker compose ps` first — the nginx container might be in a bad state. Do NOT `docker compose down` — that would take down the frontend too.

## 10. What "done" means

- Both watchdog timers are `active` and `enabled`.
- Both watchdog logs show at least one "OK" entry from a manual run.
- Nginx config is updated and the maintenance page is mounted in the container.
- `curl https://flowmanner.com/api/health` returns 200 (normal traffic unaffected).
- Handoff written to `.sisyphus/handoffs/exit-audit-2026-07-01-wireguard-spof-fix.md`.
- **You do NOT commit.** Per session ritual: Glenn reviews, Hermes commits. Stop at the handoff.
- **You do NOT restart WireGuard during implementation.** Only the watchdog timers should ever trigger a restart.
