# VPS Containerized Hermes "Open Computer" — Deep-Dive Plan

**Status:** PLAN ONLY. No code. Authored on homelab, deployed to VPS `74.208.115.142`
(see §11 trust boundary).
**Date:** 2026-07-08 (rev 3 — folded in second-model review: egress allowlist now
required, MCP deferred to v1.1, LP=P, prebuilt frontend, resource floors, corrected
threat model).
**Grounding:** Both upstream READMEs + Hermes web-dashboard docs fetched directly this
session (not guessed). Review inputs in §12.

---

## 0. Corrections to the original draft you were handed

The original draft claimed *"my tools can only access GitLab resources, so I cannot fetch
those GitHub READMEs"* and flagged every detail with ⚠️. That premise was false — all READMEs
+ dashboard docs were fetched directly. Verified facts below replace those guesses.

| Original-draft claim | Verified reality |
|---|---|
| "Can't access GitHub" — all details guessed | Fetched directly. No guessing. |
| Open Computer = a containerizable Linux desktop | **False.** QEMU ARM64 VM (Debian+XFCE+Chromium), Mac/hypervisor-oriented. |
| Hermes integration is an open question | **False.** Docker backend + container-isolation + MCP + linked `computer-use-linux`. |
| "Verify Hermes license" | **MIT** confirmed. |
| Browser surface needs custom UI / ttyd | **False.** `hermes dashboard` Chat tab embeds the full TUI over WebSocket/PTY. |

---

## 1. Repo / docs facts confirmed before planning

- **AnythingLLM / open-computer** (`Mintplex-Labs/anything-llm`): QEMU ARM64 VM per agent
  (`:9800`), CLI `create|up|destroy`, browser via CDP, tools as `pi` extensions.
  `LICENSE` present (verify MIT before reusing code). **Takeaway:** copy the *experience*,
  not the QEMU stack.
- **Hermes Agent** (`NousResearch/hermes-agent`, **MIT**): uv+Py3.11+Node+Git. Six terminal
  backends incl. **Docker**. `hermes dashboard` = web UI (Status / **Chat** / Config / Skills
  / MCP / Models / Sessions); Chat tab embeds the real TUI over `/api/ws` + `/api/pty`
  (xterm.js + WebGL). Needs `hermes-agent[web,pty]`. Basic-auth via
  `HERMES_DASHBOARD_BASIC_AUTH_*`. CORS auto-allows the custom port origin. Live chat WS is
  gated by a request guard that can close **4403** (Host/peer mismatch) or **4401** (ticket
  unauth). Linked MCP bridge: **`computer-use-linux`** (`agent-sh/computer-use-linux`, Rust +
  npm `@agent-sh/computer-use-linux`, **MIT**) — drives a real Linux desktop (AT-SPI tree,
  X11/Wayland input, screenshots) from any MCP host.
- **User-supplied constraints (rev 2):** Model = **set by you in the dashboard** (you mentioned
  DeepSeek V4 Flash as default; provider is your choice — OmniRoute, which already powers
  glennguilloux.com, or direct DeepSeek/OpenRouter). **No provider hardcoded in this plan.**
  Key stored in `HERMES_HOME` volume. Tunnel = **SSH local-forward**
  (`ssh -i ~/.ssh/vps_flowmanner_new -L <LP>:localhost:<P> root@74.208.115.142`; canonical key
  is `vps_flowmanner_new` — two n's). **Always-on** single instance.

---

## 2. Goal & success criteria

**Goal:** A Docker-Compose app on the VPS giving a *second, isolated* Hermes instance its own
Linux desktop + browser; you (a) **chat in the browser** via the dashboard Chat tab and
(b) **watch its desktop live** via noVNC — both through one SSH-tunneled port, always-on.

**Success criteria:**
1. `PUBLIC_PORT=<P> docker compose up -d` brings up the stack; `restart: unless-stopped`.
2. Hermes runs only in its container with dedicated `HERMES_HOME` (`/home/agent/.hermes`) +
   `/workspace` volume; model/API-key config survives restart.
3. Via tunnel: dashboard Chat at `/`, desktop at `/vnc/` — one port, one `-L` (with `LP=P`).
4. Agent edits/runs confined to its container; browsing visible on the desktop it drives.
5. Both surfaces auth-protected; services published **loopback only**; **egress allowlisted**.

---

## 3. Architecture (rev 3 — MCP deferred to v1.1)

```
        VPS 74.208.115.142  (docker network: agent-net, internal)
   ┌──────────────────────────────────────────────────────────────────────┐
   │  ┌──────────────┐   ┌───────────────────────┐   ┌────────────────────┐ │
   │  │  gateway     │   │  computer              │   │  hermes-agent      │ │
   │  │  Caddy       │──▶│  Xvfb + Openbox        │◀──│  Hermes runtime    │ │
   │  │  (1 port =P) │   │  + x11vnc + noVNC :6080│   │  + dashboard Chat  │ │
   │  │  /      →    │   │  + Chromium CDP :9222  │   │  + CDP browser tool│ │
   │  │    dashboard │   │    (internal only)     │   │  VOL: agent-ws     │ │
   │  │  /vnc/  →    │   │  VOL: shared /workspace│   │  (HERMES_HOME +     │ │
   │  │    noVNC     │   │                        │   │   /workspace)      │ │
   │  │  basic-auth  │   │                        │   │                    │ │
   │  │  on /vnc/    │   │                        │   │  (v1.1: + MCP via  │ │
   │  └──────┬───────┘   └───────────┬───────────┘   │   shared X11/D-Bus) │ │
   │  (optional) egress│             │ CDP (TCP)      └───────────┬────────┘ │
   │  allowlist proxy  │             └────────────────────────────┘          │
   └─────────┼─────────┴────────────────────────────────────────────────────┘
             │ ports published to VPS 127.0.0.1 only
             ▼  ssh -L <P>:localhost:<P> root@vps   (LP = P)
        Your browser → http://localhost:<P>/  (chat)  and  /vnc/  (desktop)
```

| Container | Role | Key tech |
|---|---|---|
| `gateway` | **Single published port = P.** `/`→dashboard, `/vnc/`→noVNC; WS upgrade; basic-auth on `/vnc/` | Caddy |
| `computer` | The "screen" the agent watches/controls | Debian slim + Xvfb + Openbox + x11vnc + noVNC + Chromium (CDP `:9222` internal) |
| `hermes-agent` | Second Hermes instance; serves dashboard (Chat = browser console); drives browser via **CDP** (`computer:9222`, pure TCP) | Hermes `[all]` extra, prebuilt dashboard frontend, CDP browser tool (Playwright/Puppeteer) |
| *(recommended)* `egress` | Outbound allowlist for the agent | tinyproxy/squid allowlist (Phase 4; target = whatever provider you configured in dashboard, §5/§9) |

**v1 vs v1.1:** v1 ships shell tools + noVNC watching + CDP-only browser automation (no
`computer-use-linux`). v1.1 adds full desktop control via `computer-use-linux` MCP, which
requires sharing the X11 + D-Bus session-bus sockets between the two containers (same UID)
or a networked-MCP fallback (see §7). **Deferring the MCP removes the only hard Phase-0
transport gate from the critical path.**

---

## 4. Why NOT copy Open Computer's QEMU approach

QEMU ARM64 + KVM assumes aarch64/hypervisor and is heavy (GBs qcow2, provisioning). Your VPS
is x86-64, headless, container-targeted. A container desktop (Xvfb/noVNC) delivers the same
UX at a fraction of the footprint, starts in seconds, restarts cleanly. Keep Open Computer's
good ideas (one desktop per agent, browser via CDP, watch live, per-agent port) — as compose
services.

---

## 5. Workspace isolation & containment (core requirement — corrected threat model)

- **Dedicated identity:** `HERMES_HOME=/home/agent/.hermes` (separate from any existing
  instance) on volume `agent-ws`; `/workspace` also on `agent-ws`, shared into `computer`.
- **Non-root:** UID 1000 (same in both containers — required for X11/D-Bus auth later).
- **Read-only rootfs:** `read_only: true`; writable mounts only `/workspace`, `/tmp` (tmpfs),
  and `HERMES_HOME`. **Prebuild the dashboard frontend in the image** (§8) so no first-launch
  `npm` build writes to a read-only layer.
- **Resource floors (§9):** `pids_limit: 2048` (computer) / `512` (agent); `shm_size: 1g`
  (computer — Chromium /dev/shm classic crash); mem `3g`/`1.5g`; **no hard CPU quota** on a
  2-vCPU box (CFS throttling janks Chromium). Size the VPS to **~8 GB RAM** (4 GB is too low
  under load).
- **Network:** both on internal `agent-net`. **Egress allowlist proxy is REQUIRED (not
  - **Egress allowlist proxy (recommended hardening, Phase 4):** allow only the LLM endpoint
    you configured in the dashboard + explicitly needed domains. This is the single control
    that bounds the #1 blast radius (§9). **Not a blocker** for the agent to run — populate the
    target at deploy time from whatever provider you chose in the dashboard.
- **No Docker socket** mounted into either container.
- **Hardening:** `security_opt:[no-new-privileges:true]`, default seccomp, drop unneeded caps.
- **Secrets:** DeepSeek/OmniRoute key set by you in the dashboard → `HERMES_HOME` volume. Never
  bake keys into the image; never expose to `computer`/`gateway`.
- **Reset must cover `HERMES_HOME`, not just `/workspace`** (§9) — a prompt-injected agent can
  plant persistent instructions there that re-compromise every future session.

---

## 6. Browser access & tunneling (SSH local-forward, LP = P)

- Services publish to VPS **loopback only**: `ports: ["127.0.0.1:${P}:${P}"]` (Caddy) — not
  public, reachable solely via your SSH tunnel.
- **Pin `LP = P`** (local port = published port = dashboard port). This makes `Host:
  localhost:<P>` true end-to-end and satisfies the dashboard's auto-allowed CORS origin
  (`http://localhost:<P>`). *Never* use a different laptop-side port "because it's free" —
  it silently breaks the allowed origin.
- Tunnel: `ssh -i ~/.ssh/vps_flowmanner_new -L <P>:localhost:<P> root@74.208.115.142`, then
  open `http://localhost:<P>/` (chat) and `/vnc/` (desktop).
- **Caddy must rewrite `Host` for the dashboard upstream** so the 4403 Host guard passes:
  ```
  :{$PUBLIC_PORT} {
    handle_path /vnc/* { basic_auth { glenn <hash> } reverse_proxy computer:6080 }
    handle {
      reverse_proxy hermes-agent:{$PUBLIC_PORT} { header_up Host {upstream_hostport} }
    }
  }
  ```
  Caddy 2 handles the WS upgrade automatically. (4401 ticket = same-origin, should hold.)
  Mirror the existing `VPS-Files` Caddyfile precedent: `flush_interval -1` + generous
  read/write timeouts so the dashboard's streaming WS / agent output doesn't buffer.
- **Residual risk + fallback:** if the dashboard's 4403 guard also validates the *peer* as
  loopback, the connection now arrives from Caddy's container IP → WS rejected. **Test in
  Phase 3 first.** Escape hatch: drop Caddy for the dashboard, use **two `-L` forwards**
  (dashboard direct on loopback satisfies a strict peer check; Caddy only fronts noVNC). Keep
  in pocket.

---

## 7. Agent ↔ computer wiring (v1 = CDP-only; v1.1 = full MCP)

**v1 (this plan's critical path):** Hermes `shell`/file tools run in its container's
`/workspace` = the volume the desktop shows (so you watch edits live via noVNC). Browser
automation uses a **CDP-only tool** (Playwright/Puppeteer connecting to `computer:9222`,
pure TCP — zero transport problems), and the agent's browsing is visible on the desktop you
watch. No `computer-use-linux` needed.

**v1.1 (bounded spike, defer):** add `computer-use-linux` for arbitrary GUI clicking. Its
transport breaks down as:
- CDP (`:9222`) → TCP, trivially remote.
- Screenshots + X11 input → X11 protocol, via a **shared `/tmp/.X11-unix` socket**.
- AT-SPI accessibility tree → **D-Bus session bus**, machine-local by design → needs a
  **shared D-Bus socket** (or co-location).

Clean split survives via **shared X11 + D-Bus session-bus sockets** (same UID 1000 in both
containers), `computer` runs `dbus-daemon --session` writing to the shared path:
```
volumes: x11-socket (→ /tmp/.X11-unix both), dbus-socket (→ shared session-bus dir)
hermes-agent env: DISPLAY=":99"  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/dbus-session/bus"
```
**Verify without full build (Phase 0 of v1.1):** `npm pack @agent-sh/computer-use-linux`, grep
for `DBUS_SESSION_BUS_ADDRESS`/`DISPLAY`/`atspi`/zbus/x11rb. If it reads env vars →
socket-sharing works. If it shells out to desktop-local helpers → **fallback: run the MCP
binary inside `computer` and expose it as a networked MCP (SSE/HTTP) to Hermes** — preserves
the split.

---

## 8. Phased delivery plan

**Phase 0 — Research & validation (1–2 d)**
- Pick port `<P>`. Confirm OmniRoute API endpoint domain (feeds egress allowlist).
- (v1.1 only later) inspect `computer-use-linux` transport per §7.
- Acceptance: port + endpoint locked; no code.

**Phase 1 — `computer` container (2–3 d)**
- Debian slim + Xvfb + Openbox + x11vnc + noVNC + Chromium(CDP). Healthcheck: X up + VNC.
  `pids_limit:2048`, `shm_size:1g`, `mem_limit:3g`.
- Acceptance: `http://localhost:<P>/vnc/` (via tunnel) shows a live, controllable desktop.

**Phase 2 — `hermes-agent` container (3–5 d)**
- Multi-stage Dockerfile: build dashboard frontend (Node) → copy static into
  `hermes-agent[all]` Python image; non-root UID 1000; `HERMES_HOME` + `/workspace` on
  `agent-ws`; `read_only:true` (writable `/workspace`,`/tmp`,`HERMES_HOME`); `restart:
  unless-stopped`; `pids_limit:512`, `mem_limit:1.5g`.
- `hermes dashboard --host 0.0.0.0 --port <P> --no-open`. Register CDP browser tool →
  `computer:9222`. You set DeepSeek/OmniRoute in dashboard; verify persistence across restart.
- Smoke test: "create a file in /workspace, open it in the desktop's editor; browse a site
  via CDP and watch it on noVNC."
- Acceptance: agent edits/runs/browses confined to its container; state persists.

**Phase 3 — `gateway` + tunnel (1–2 d)**
- Caddy per §6 (`LP=P`, `header_up Host`, basic-auth on `/vnc/`). Publish `127.0.0.1:<P>` only.
- **Test the dashboard WS early** (4403/4401). If peer-check fails → two-`-L` fallback.
- Verify loopback-only (off-VPS nmap = closed). Acceptance: one tunneled port → chat+desktop;
  anon blocked.

**Phase 4 — Hardening & ops (2–4 d) — egress recommended**
- **Egress allowlist proxy** (tinyproxy/squid) allowing only the LLM endpoint you configured in
  the dashboard + needed domains. This bounds API-key exfil + egress abuse. Recommended
  (enable before the agent has network access with the key); not a blocker to run.
- Read-only rootfs, cap drops, resource floors (already set), optional egress sidecar.
- `agent-ws` backup job (also = compromise-recovery); **reset playbook covering `HERMES_HOME`
  AND `computer`** (not just `/workspace`).
- Threat-model pass per §9.

**Phase 5 — Quality of life (ongoing)**
- Per-project workspaces (one volume per project); "reset desktop" + "reset HERMES_HOME"
  buttons; session history via dashboard Sessions tab; **v1.1 MCP spike** (§7).

---

## 9. Key risks & tradeoffs (rev 3 — corrected)

- 🔴 **Threat model — your earlier "only ruins its own workspace" is FALSE.** Real blast
  radius if prompt-injected: (1) **LLM API key** in `HERMES_HOME` → exfil/billing abuse; (2)
  **persistent `HERMES_HOME`** → planted instructions re-compromise every session; (3) **open
  egress** → your VPS IP becomes spam/scan/exfil platform; (4) **Chromium sessions** via CDP →
  any account logged into the desktop browser is compromised (rule: nothing personal there).
  **Mitigation: egress allowlist (recommended; fill target at deploy from your chosen provider) +
  reset covering `HERMES_HOME` + treat `computer` as disposable.** Container escape itself is
  well-bounded by existing hardening.
- 🟠 **WS guard behind Caddy (4403):** pin `LP=P` + `header_up Host`; keep two-`-L` fallback.
- 🟠 **MCP transport (v1.1):** AT-SPI/D-Bus is the wrinkle; defer to v1.1, socket-share or
  networked-MCP fallback.
- 🟡 **VPS sizing:** ~8 GB RAM (4 GB too low under load). No hard CPU quota.
- 🟡 **noVNC latency over SSH tunnel:** usable, not snappy; KasmVNC/Selkies (WebRTC) if it bites.
- 🟡 **Licensing:** Hermes MIT ✅; `computer-use-linux` MIT ✅; `open-computer` verify.

---

## 10. Decisions locked (rev 3) & remaining unknowns

**Locked:**
- Model: **DeepSeek V4 Flash via OmniRoute**, set by you in dashboard (key in volume).
- Tunnel: **SSH `-L`**, services loopback-only, **`LP = P`**.
- Instance: **single, always-on** (`restart: unless-stopped`).
- Browser surface: **dashboard Chat tab** (TUI over WebSocket).
- v1 scope: **shell + noVNC + CDP-only browser tool**; full MCP deferred to v1.1.
- Egress allowlist: **required** (Phase 4, ideally enabled at deploy).

**Remaining unknowns (none blocking — all deployment-time decisions):**
1. **Which LLM provider/endpoint you'll configure in the dashboard** (DeepSeek direct,
   OmniRoute, or other). Only feeds the *optional* Phase-4 egress allowlist target — not a
   blocker. Set it when you set up the agent.
2. WS peer-check behavior in Phase 3 (decides Caddy vs two-`-L`).
3. Whether to run the egress proxy as a 4th container or host-level.

**Locked this rev:**
- **Port `<P>` = `20123`** (your chosen port, distinct from the `20128` example and from the
  clickandbuilds `VPS-Files` app which publishes `9443` → `ai-proxy:8081`; no collision).
- **This is a SEPARATE project from `VPS-Files`.** Mirror its *structure* (Caddy
  `reverse_proxy` + `flush_interval -1` for streaming) but: own compose dir
  (e.g. `/home/glenn/agent-computer/`), own docker network (NOT `ai-net`), **loopback-only
  publish** (no public domain/TLS — the SSH tunnel already encrypts), and basic-auth on
  `/vnc/`. Do not share the `VPS-Files` Caddyfile/certs/`.env`.

---

## 11. Trust boundary (per AGENTS.md)

- Author on the **homelab**, not the VPS. Own project dir (e.g. `/home/glenn/agent-computer/`
  or a new repo), separate from Flowmanner's image pipeline.
- Deploy via **rsync of bundle + `docker compose up`** — do **not** `docker build` on the VPS.
  VPS is runtime-only. NOT through `deploy-backend.sh`/`deploy-frontend.sh`.
- **If promoted to a GitLab epic:** mark confidential; strip VPS IP + key paths to
  `<VPS_IP>`/`<KEY>` (your memory already flags the agent-computer threat model — don't let
  an agent read live creds from the plan).

---

## 12. Reviewer inputs incorporated (rev 3)

Second-model review (Opus/Fable, reasoning from the §1 facts, no repo access) — graded and
adopted:
- #5 threat model (false assumption) → egress allowlist (recommended; target from chosen
  provider) + `HERMES_HOME` reset. **Adopted (softened from "required" so it isn't a blocker).**
- #2 WS guard (4403 Host/peer) → `LP=P` + `header_up Host` + two-`-L` fallback. **Adopted.**
- #1 MCP transport decomposition → socket-share design for v1.1. **Adopted (deferred).**
- #4 MCP not needed for v1 → CDP-only browser tool. **Adopted (scope cut).**
- #3 prebuild frontend multi-stage → read-only rootfs intact. **Adopted.**
- #6 resource caps (`pids_limit`/`shm_size`/no hard CPU/8 GB) → **Adopted.**
- #7 OmniRoute = provider, not tunnel → consistent with memory; need endpoint domain.

Not adopted / not applicable: the earlier "trailing backend section" critique — that content
is **not in this document** (it lives in a separate plan); no split required.

---

## 13. What I can do next

- Draft the concrete `docker-compose.yml` + `Dockerfile`s (`computer` / `hermes` multi-stage /
  `gateway` Caddy) with `<P>` parameterized and the egress proxy included.
- Turn this into a confidential epic in `glennguilloux-group` with Phases 0–5 as child issues,
  the two amendments (egress required, MCP deferred) baked into acceptance criteria.
- Inspect `computer-use-linux` source now to pre-close the v1.1 transport question.
