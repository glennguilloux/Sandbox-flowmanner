# WireGuard Tunnel Watchdog — Homelab

**Status (2026-07-02): Disabled by user request.** Timer and service stopped and
disabled. `wg-quick@wg0.service` (the actual tunnel) is untouched and still up.

**Why this doc exists:** the previous handoff
([`HANDOFF-2026-07-01-wireguard-and-v2.md`](./HANDOFF-2026-07-01-wireguard-and-v2.md))
flagged **W10 — WireGuard SPOF** and recommended a watchdog, but described one
on the **VPS** pinging the homelab peer (10.99.0.3). A real watchdog was
already running on the **homelab** pinging the VPS peer (10.99.0.1) — and a
second, different watchdog was running on the **VPS** checking handshake
freshness. This doc covers both — read it before re-implementing W10 or
interpreting WireGuard-related Telegram alerts. See the
[Lesson: search both endpoints](#lesson-search-both-endpoints) section below for
why both exist as a single canonical reference.

---

## What it did

Every 60 seconds a systemd timer fired a oneshot service that:

1. Pinged the VPS through the WireGuard tunnel (`ping -c 1 -W 5 10.99.0.1`).
2. Tracked consecutive failures in `/var/run/wg-watchdog-failures`.
3. After **2 consecutive failures**, restarted `wg-quick@wg0` and sent a
   Telegram "warn" message.
4. After recovery, sent a Telegram "ok" message.

The watchdog could not bring the tunnel back up by itself in most failure modes
(restarting `wg-quick@wg0` rarely fixes a peer-side outage) — it was primarily a
**notifier**, not a healer.

## Components

| Path | Purpose |
|------|---------|
| `/etc/systemd/system/wg-watchdog.timer` | Fires the service every 60 s |
| `/etc/systemd/system/wg-watchdog.service` | Oneshot wrapper around the script |
| `/usr/local/bin/wg-watchdog.sh` | The script itself — ping, counter, restart, Telegram |
| `/etc/wg-watchdog.env` | **Disabled.** Holds `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`. Still on disk, untouched. |
| `/var/log/wg-watchdog.log` | Append-only log of ping failures, restarts, recoveries |
| `/var/run/wg-watchdog-failures` | State file with consecutive-failure counter |

### The Telegram path (why the alerts happened)

`wg-watchdog.sh:15-44` defines `send_alert()`. It:

1. Sources `/etc/wg-watchdog.env` for `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
2. POSTs to `https://api.telegram.org/bot${TOKEN}/sendMessage` with an emoji
   prefix (`⚠️` for warn, `✅` for ok) and the message text.
3. Early-returns silently if the env file is missing or the vars are unset —
   this is what made "stop the alert" safely reversible.

The script sends alerts on two events only:

- `send_alert "warn" ...` at `wg-watchdog.sh:74` — when `count >= FAIL_THRESHOLD` (2).
- `send_alert "ok" ...` at `wg-watchdog.sh:55` — when a previously-failing tunnel recovers.

No spam on healthy ticks — the happy path just `exit 0`s at line 59.

## Current state (verified 2026-07-02)

```
$ systemctl is-active wg-watchdog.timer
inactive
$ systemctl is-enabled wg-watchdog.timer
disabled
$ systemctl is-active wg-watchdog.service
inactive
$ systemctl list-timers --all | grep -i 'wg\|wireguard'
(no output — no wg/wireguard timers loaded)
$ systemctl list-units --type=service --all | grep 'wg-quick@wg0'
wg-quick@wg0.service  loaded  active  exited  WireGuard via wg-quick(8) for wg0
```

The `wg-quick@wg0.service` is the actual tunnel interface and was **not**
touched — only the watchdog timer/service that monitors it.

## How to re-enable (if you change your mind)

Full re-enable, with alerting restored:

```bash
sudo systemctl enable --now wg-watchdog.timer
# Verify
systemctl list-timers wg-watchdog.timer
sudo systemctl start wg-watchdog.service   # optional: force one run
journalctl -u wg-watchdog.service -n 20 --no-pager
```

The env file (`/etc/wg-watchdog.env`) is still on disk with the bot token and
chat id intact, so Telegram alerts will resume automatically on the next
2-consecutive-failure event. The unit files are also still in
`/etc/systemd/system/` — `enable --now` is sufficient, no reinstall needed.

To permanently delete:

```bash
sudo systemctl disable --now wg-watchdog.timer
sudo rm /etc/systemd/system/wg-watchdog.timer \
        /etc/systemd/system/wg-watchdog.service \
        /usr/local/bin/wg-watchdog.sh \
        /etc/wg-watchdog.env
sudo rmdir /etc/systemd/system 2>/dev/null || true   # only if empty
```

## VPS-side watchdog (disabled 2026-07-02 — second one)

The **VPS (74.208.115.142)** runs a separate watchdog — same timer/service
names, different script. This one was the actual source of the most recent
alert ("`⚠️ WireGuard Alert (VPS)` … `STALE: Handshake is 14930s old`").

### Components (VPS)

| Path | Purpose |
|------|---------|
| `/etc/systemd/system/wg-watchdog.timer` | Same template as homelab, fires every 60 s |
| `/etc/systemd/system/wg-watchdog.service` | Same template, runs the VPS script |
| `/opt/flowmanner/scripts/wg-watchdog.sh` | **In the deploy tree.** Handshake-age based. |
| `/etc/wg-watchdog.env` | **Disabled.** Bot token + chat id, still on disk. |
| `/var/log/wg-watchdog.log` | Stale-handshake events + endpoint-clear events |

Note: the VPS script lives in `/opt/flowmanner/scripts/` (the deploy target),
not `/usr/local/bin/`. A future `deploy-all.sh` or `deploy-backend.sh` could
overwrite or remove it. If you re-enable, also pin the script — see the
[Re-enable checklist](#re-enable-checklist) below.

### What it does (different from homelab)

Unlike the homelab script (ping-based, restart the interface), the VPS script:

1. Reads the latest handshake timestamp for the homelab peer from
   `wg show wg0 latest-handshakes`.
2. If the handshake is older than `STALE_THRESHOLD=120` s (≈ 2 missed
   keepalives), sends the Telegram alert you saw and **clears the endpoint**
   (`wg set wg0 peer <pubkey> endpoint 0.0.0.0:0`) so the next inbound packet
   from the homelab re-establishes the tunnel.

The recovery action here is real — endpoint-clearing actually fixes a class of
NAT rebind / route-flap failures that a restart would not. This is why I asked
before disabling, and why this one is mentioned separately from the homelab.

### Current state on VPS (verified 2026-07-02)

```
$ systemctl is-active wg-watchdog.timer
inactive
$ systemctl is-enabled wg-watchdog.timer
disabled
$ systemctl is-active wg-watchdog.service
inactive
$ systemctl list-timers --all | grep -i 'wg\|wireguard'
(no output)
$ systemctl is-active wg-quick@wg0.service
active
```

### Re-enable on VPS

```bash
ssh root@74.208.115.142
sudo systemctl enable --now wg-watchdog.timer
sudo systemctl start wg-watchdog.service   # optional: force one run
journalctl -u wg-watchdog.service -n 20 --no-pager
```

The env file is still at `/etc/wg-watchdog.env`, so Telegram alerts resume on
the next stale handshake.

---

## Lesson: search both endpoints

When the user reports a WireGuard alert, **grep both machines** before
disabling anything. In this session, the homelab grep returned
`wg-watchdog.{timer,service}` on `archglenn`, and I assumed that was the
source. The actual paging alert (`(VPS)` prefix) came from the VPS, where a
near-identical watchdog with a different detection strategy (handshake age vs.
ping) was running independently. The two scripts diverge at lines 49-79
(homelab: ping + restart; VPS: `wg show` + endpoint-clear), and would have
been caught by a 5-second SSH check of the VPS.

**Rule for future agents:** when disabling a watchdog, alert, cron, or any
tunnel-monitoring code, confirm the alert prefix in the user's message and
find every code path that produces that exact prefix across **both** the
origin and destination machines. "Disabled the alert" means "I stopped the
specific alert the user just received," not "I stopped an alert that looked
similar."

If you turn it back on, be aware:

- **Spam risk on VPS outages.** A VPS-side WireGuard peer crash triggers a
  Telegram ping every ~120 s (2 consecutive failures + restart cycle). The
  bot has no rate limit on this script.
- **Restart doesn't usually help.** `systemctl restart wg-quick@wg0` fixes
  nothing if the peer is unreachable. The watchdog confuses "alert" with
  "fix."
- **Counter resets on reboot.** `/var/run/wg-watchdog-failures` lives in tmpfs,
  so a homelab reboot starts the count fresh — a single failed ping right
  after boot doesn't alert (correct), but a persistent failure won't alert
  until ~2 minutes after boot either.
- **Logs to `/var/log/wg-watchdog.log` forever.** Not logrotated by default;
  add a logrotate entry if you re-enable.

## Relation to W10 (WireGuard SPOF) from the 2026-07-01 handoff

The old handoff recommended a **VPS-side** watchdog that pings the homelab peer
(10.99.0.3) — a different machine, different peer, different vantage point.
That recommendation still stands and was never implemented; the homelab
watchdog was a separate, pre-existing artifact.

The homelab watchdog can't fix the SPOF on its own because the most common
failure modes are VPS-side (peer key rotation, VPS reboot, ISP routing
change). To actually mitigate W10 you need either:

1. **VPS-side watchdog** (per the handoff) pinging 10.99.0.3 every 60 s and
   restarting `wg-quick@wg0` on the VPS.
2. **Nginx 502/503 graceful degradation** (per the handoff, Layer 2) so
   `/api/*` returns a clean JSON error instead of hanging when the tunnel is
   down.
3. **Cloudflare Tunnel fallback** (Layer 3, deferred).

Both watchdogs running simultaneously is fine — they're on different machines
and monitor different directions of the same tunnel.
