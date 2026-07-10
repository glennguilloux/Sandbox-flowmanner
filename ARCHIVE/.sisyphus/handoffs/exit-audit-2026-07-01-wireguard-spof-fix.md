# EXIT AUDIT — WireGuard SPOF Fix

**Date:** 2026-07-01
**Session:** WireGuard SPOF mitigation — watchdog, nginx, logrotate, alerting, peer cleanup, failure simulation

---

## WHAT CHANGED (one bullet per file, what + why)

### VPS (74.208.115.142)
- `/opt/flowmanner/scripts/wg-watchdog.sh` **Created** — watchdog script that checks handshake freshness with homelab peer (120s threshold), clears stale endpoint, sends Telegram alerts on STALE/ERROR events
- `/etc/systemd/system/wg-watchdog.service` **Created** — systemd oneshot service unit for VPS watchdog
- `/etc/systemd/system/wg-watchdog.timer` **Created** — systemd timer running every 60s, persists across reboot
- `/opt/flowmanner/nginx/maintenance.html` **Created** — dark-themed maintenance page for 502/504 errors
- `/opt/flowmanner/nginx/default.conf` **Modified** — added `proxy_intercept_errors on` + `error_page 502 504 /maintenance.html` in HTTPS server block
- `/opt/flowmanner/docker-compose.yml` **Modified** — added volume mount `./nginx/maintenance.html:/etc/nginx/maintenance.html:ro` to nginx service
- `/etc/logrotate.d/wg-watchdog` **Created** — weekly rotation, 4 compressed copies
- `/etc/wg-watchdog.env` **Created** — Telegram bot credentials (chmod 600, root:root)
- `/etc/wireguard/wg0.conf` **Modified** — removed dead peer `10.99.0.4` (P6rLB47g3N3LF9ktTnwfZ7XsJShaHaoQHDVt67KyIkc=, zero handshakes, zero traffic)

### Homelab (10.99.0.3)
- `/usr/local/bin/wg-watchdog.sh` **Created** — watchdog script that pings VPS through tunnel, restarts WireGuard after 2 consecutive failures, sends Telegram alerts on FAIL/RESTART/RECOVERED events
- `/etc/systemd/system/wg-watchdog.service` **Created** — systemd oneshot service unit for homelab watchdog
- `/etc/systemd/system/wg-watchdog.timer` **Created** — systemd timer running every 60s, persists across reboot
- `/etc/logrotate.d/wg-watchdog` **Created** — weekly rotation, 4 compressed copies
- `/etc/wg-watchdog.env` **Created** — Telegram bot credentials (chmod 600, root:root)

### Documentation
- `.sisyphus/handoffs/exit-audit-2026-07-01-wireguard-spof-fix.md` **Updated** — this file

---

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- None — all changes are live on the respective machines

---

## TESTS RUN + RESULT

No code tests (this is infrastructure, not application code). Verification was done via:

1. **Manual watchdog runs** — both scripts ran successfully with exit 0
2. **Failure simulation** — killed WireGuard on homelab, watchdog detected 2 consecutive failures, restarted WireGuard, tunnel recovered automatically in ~2 minutes
3. **API health check** — `curl https://flowmanner.com/api/health` returned 200 through recovered tunnel
4. **Nginx syntax test** — `nginx -t` passed
5. **Telegram alert test** — test messages delivered successfully from both machines
6. **Logrotate dry run** — `logrotate -d` on both machines, no errors

---

## STATUS (raw output)

### VPS Watchdog Timer
```
$ systemctl is-active wg-watchdog.timer
active

$ systemctl is-enabled wg-watchdog.timer
enabled
```

### VPS Watchdog Log
```
$ tail -5 /var/log/wg-watchdog.log
2026-07-01 08:16:11 OK: Handshake is 8s old
```

### VPS Nginx
```
$ docker exec flowmanner-nginx nginx -t
nginx: the configuration file /etc/nginx/conf.d/default.conf syntax is ok
nginx: configuration file /etc/nginx/conf.d/default.conf test is successful
```

### API Health
```
$ curl -s -o /dev/null -w '%{http_code}' https://flowmanner.com/api/health
200
```

### VPS WireGuard
```
$ wg show wg0
interface: wg0
  public key: 95l+hEgqR5z1ax20JnI0I4N/O7VsL8zi1mSg0XU7/nQ=
  listening port: 51820

peer: AdZG7G7cwaYTIUB9CyF2FxxwQWUyQLab+VWIkM9rMEI=
  endpoint: 176.141.9.146:51820
  allowed ips: 10.99.0.3/32
  latest handshake: 38 seconds ago
  transfer: 104.45 MiB received, 162.82 MiB sent
  persistent keepalive: every 5 seconds
```

### Homelab Watchdog Timer
```
$ systemctl is-active wg-watchdog.timer
active

$ systemctl is-enabled wg-watchdog.timer
enabled
```

### Homelab Watchdog Log (from failure simulation)
```
$ sudo tail -5 /var/log/wg-watchdog.log
2026-07-01 09:57:10 FAIL: Ping to 10.99.0.1 failed (consecutive failures: 1)
2026-07-01 09:58:11 FAIL: Ping to 10.99.0.1 failed (consecutive failures: 2)
2026-07-01 09:58:11 RESTART: 2 consecutive failures. Restarting wg-quick@wg0
2026-07-01 09:58:11 RESTART: wg-quick@wg0 restarted. Waiting for reconnection.
```

### Homelab WireGuard
```
$ sudo wg show wg0
interface: wg0
  public key: AdZG7G7cwaYTIUB9CyF2FxxwQWUyQLab+VWIkM9rMEI=
  listening port: 51820

peer: 95l+hEgqR5z1ax20JnI0I4N/O7VsL8zi1mSg0XU7/nQ=
  endpoint: 74.208.115.142:51820
  allowed ips: 10.99.0.1/32
  latest handshake: 37 seconds ago
  transfer: 63.66 KiB received, 35.78 KiB sent
  persistent keepalive: every 5 seconds
```

### Tunnel Health
```
$ ping -c 2 -W 3 10.99.0.1
PING 10.99.0.1 (10.99.0.1) 56(84) bytes of data.
64 bytes from 10.99.0.1: icmp_seq=1 ttl=64 time=114 ms
64 bytes from 10.99.0.1: icmp_seq=2 ttl=64 time=114 ms

--- 10.99.0.1 ping statistics ---
2 packets transmitted, 2 received, 0% packet loss
```

### Env Files
```
# Homelab
$ ls -la /etc/wg-watchdog.env
-rw------- 1 root root 94 Jul  1 10:13 /etc/wg-watchdog.env

# VPS
$ ls -la /etc/wg-watchdog.env
-rw------- 1 root root 94 Jul  1 08:12 /etc/wg-watchdog.env
```

### Logrotate
```
$ logrotate -d /etc/logrotate.d/wg-watchdog 2>&1 | head -3
reading config file /etc/logrotate.d/wg-watchdog
Allocating hash table for state file, size 15360 B
Handling 1 log
```

### Git Status
```
$ git status --short
 M docs/BRAINSTORM-PROMPT-NEXT-PLAN.md
```

---

## NEXT SESSION HANDOFF

This session completed the WireGuard SPOF mitigation task from the task spec at `docs/EXIT-AUDIT-2026-07-01-session-complete.md`. All three layers are live: detection (watchdog timers on both machines, every 60s), recovery (auto-restart on homelab, endpoint-clear on VPS), and user experience (nginx maintenance page on 502/504). Telegram alerting is wired up via `@glennrockbot` (chat ID `8361144666`), and the failure simulation proved the full recovery cycle works — tunnel dies, watchdog detects in ~2 min, restarts, tunnel recovers, API returns 200. The dead VPS peer `10.99.0.4` was removed (zero handshakes ever, zero traffic).

**Gotchas for next agent:**
- The Telegram bot token is in `/etc/wg-watchdog.env` on both machines (chmod 600). If you need to rotate credentials, update both files.
- The homelab watchdog log only gets written when failures occur — if the tunnel is healthy, the file may not exist. This is by design.
- The VPS watchdog logs every ~5 min on healthy handshakes (not every 60s) to avoid log spam. Logrotate is configured for weekly rotation.
- The `wg0.conf` on the VPS was modified (dead peer removed) but NOT restarted — the live interface already had the peer removed via `wg set`. The config change takes effect on next `wg-quick down/up`.
- No application code was changed. No deploy needed. These are system-level infrastructure changes on both machines.

---

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- `docs/BRAINSTORM-PROMPT-NEXT-PLAN.md` — modified by a previous session (not this one)
- Untracked files: `.sisyphus/handoffs/` is gitignored by design (line 72 of `.gitignore`)
- Deleted files: none

---

## FUTURE WORK (not blocking)

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | **Audit ops machine peer** (`10.99.0.2`) | Low | 15 min | Shows 0 handshakes on homelab side. Is the ops machine still using WireGuard? If not, remove the peer from both homelab and VPS configs. |
| 2 | **VPS WireGuard SPOF** | Medium | 30 min | The VPS side watchdog only clears the endpoint — it doesn't restart WireGuard. If `wg-quick@wg0` crashes on the VPS (not just stale handshake), the tunnel dies. Consider adding a ping-based watchdog on the VPS too, or a systemd restart policy (`Restart=on-failure` in a drop-in for `wg-quick@wg0`). |
| 3 | **Nginx maintenance page for frontend down** | Low | 15 min | Current config intercepts 502/504 from the backend upstream only. If the frontend container itself is down, the `/api/auth/` routes (proxied to `frontend:3000`) will also 502. Consider adding `proxy_intercept_errors` to the frontend upstream blocks too. |
| 4 | **Failure simulation for VPS watchdog** | Low | 10 min | We tested the homelab watchdog recovery (kill WireGuard → auto-restart). The VPS watchdog endpoint-clear was not tested end-to-end (it requires the homelab's NAT mapping to change, which is hard to simulate). Consider a scheduled test during a maintenance window. |
| 5 | **Telegram alerting for other services** | Low | 30 min | The `send_alert()` pattern could be reused for backend health checks, PostgreSQL connection failures, disk space warnings, etc. |
| 6 | **Replace `curl` with `wget` in watchdog scripts** | Cosmetic | 5 min | Both machines have `curl`, but `wget` is more universally available on minimal installs. No action needed unless migrating to a different base OS. |
| 7 | **Dead VPS peer `10.99.0.4` removal verification** | Done | — | Removed from live interface and `wg0.conf`. Next `wg-quick down/up` on VPS will confirm the config change is persistent. |

---

## END
