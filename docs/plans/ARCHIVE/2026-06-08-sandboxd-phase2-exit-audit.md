# sandboxd Integration — Phase 2 Exit Audit

**Date:** June 8, 2026
**Status:** Phase 2 COMPLETE ✅. Preview URLs, TLS, forward auth, and monitoring all operational.

---

## Phase 2 Execution Summary

### Objective
Enable live sandbox preview URLs accessible from the user's browser, gated behind FlowManner session authentication, with TLS, monitoring, and production-ready infrastructure.

### Result
**All deliverables complete. 61 unit tests pass. Forward auth working. Wildcard TLS cert issued. VPS nginx routing operational. Cert expiry monitoring in place.**

---

## Deliverables Completed

### 1. Environment Variables (Homelab + sandboxd)

**FlowManner `.env`** (`/opt/flowmanner/.env`) — Added 5 `SANDBOXD_*` entries:

| Variable | Value |
|----------|-------|
| `SANDBOXD_API_URL` | `host.docker.internal:9090` |
| `SANDBOXD_AUTH_TOKEN` | `37fb6669...` (generated) |
| `SANDBOXD_PREVIEW_DOMAIN` | `preview.flowmanner.com` |
| `SANDBOXD_ENABLED` | `true` |
| `SANDBOXD_DEFAULT_TEMPLATE` | `react-standard` |

**sandboxd `.env`** (`/mnt/apps/Softwares2/sandboxd/.env`) — Updated 6 entries:

| Variable | Old | New |
|----------|-----|-----|
| `PREVIEW_DOMAIN` | `localhost` | `preview.flowmanner.com` |
| `PREVIEW_ENTRYPOINT` | `web` | `websecure` |
| `PREVIEW_TLS` | `false` | `true` |
| `SANDBOXD_API_AUTH_DISABLED` | `true` | `false` |
| `SANDBOXD_API_TOKENS` | *(empty)* | `flowmanner=37fb6669...` |
| `SANDBOXD_SET_MEMORY_HIGH` | `false` | `true` |

### 2. Wildcard DNS

- IONOS: `*.preview.flowmanner.com` → `74.208.115.142` A record added by user
- Verified: `dig +short s-test-3000.preview.flowmanner.com @8.8.8.8` → `74.208.115.142` ✅

### 3. Wildcard TLS Certificate

- Certbot DNS-01 challenge on VPS (manual TXT record in IONOS)
- Cert: `CN=*.preview.flowmanner.com`, SAN includes `preview.flowmanner.com`
- Issuer: Let's Encrypt (YE1)
- Valid: Jun 8, 2026 → Sep 6, 2026 (90 days)
- Cert files copied to `/opt/flowmanner/certs/preview-{fullchain,privkey,chain}.pem`

### 4. Forward Auth Endpoint (Backend)

**File:** `backend/app/api/v1/sandbox_preview.py` — Added `GET /sandbox/forward-auth`

- Validates FlowManner session via both `Authorization: Bearer` header AND `fm_refresh_token` httpOnly cookie (matches existing `deps.py` pattern at line 236)
- Uses `decode_access_token` + `get_user_by_id` with `get_db_session`
- Returns 200 + `X-Forwarded-User` header if authenticated, 401 if not
- Request parameter typed as `starlette.requests.Request`
- Exception handling narrowed to `(ValueError, TypeError, KeyError)` with warning-level logging

### 5. Traefik Forward-Auth Middleware (sandboxd)

**`sandboxd/traefik/dynamic/auth.yml`** — Updated middleware address:
```yaml
# Was: http://sandboxd:9000/forward-auth
# Now: http://host.docker.internal:8000/api/sandbox/forward-auth
```

**`sandboxd/traefik/dynamic/wake.yml`** — Added `sandbox-preview-auth` middleware to catch-all wake router:
```yaml
http:
  routers:
    sandbox-wake:
      rule: "HostRegexp(`^s-[0-9A-Za-z]+-[0-9]+\\.preview\\\\..+$`)"
      entryPoints: [web]
      middlewares:
        - sandbox-preview-auth
      service: sandbox-wake
      priority: 1
```

**`sandboxd/docker-compose.yml`** — Added `extra_hosts` to Traefik:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### 6. Sandbox Visibility Default

**File:** `backend/app/integrations/sandboxd_client.py`

Changed `SandboxdClient.create()` default visibility from `"public"` → `"private"`. This ensures sandboxd auto-applies the forward-auth middleware to active sandbox routes (not just the catch-all).

### 7. VPS Nginx Preview Routing

**File:** `/opt/flowmanner/nginx/default.conf` (on VPS, inside `flowmanner-nginx` Docker container)

Added two server blocks:

**HTTPS (443):**
- `server_name ~^(?<subdomain>.+)\.preview\.flowmanner\.com$ preview.flowmanner.com`
- Wildcard TLS cert at `/etc/nginx/certs/preview-{fullchain,privkey,chain}.pem`
- `proxy_pass http://10.99.0.3:80` (homelab sandboxd Traefik via WireGuard)
- WebSocket upgrade support for HMR
- `http2 on;` (separate directive, not deprecated `listen ... http2`)

**HTTP (80):**
- Redirects all `*.preview.flowmanner.com` to HTTPS

### 8. Cert Expiry Monitoring (VPS)

**`/opt/flowmanner/scripts/check-certs.sh`** — Daily cert expiry monitor:
- Checks all Let's Encrypt certs
- Warns at 30 days, critical at 14 days
- Prints step-by-step manual renewal instructions for the wildcard cert
- Logs to `/var/log/cert-expiry.log`
- Uses `shopt -s nullglob` for empty directory safety
- Runs daily at 9am UTC via cron

**`/opt/flowmanner/scripts/renew-preview-certs.sh`** — Post-renewal helper:
- Validates source cert exists (fails clearly if certbot hasn't been run)
- Copies certs to `/opt/flowmanner/certs/` with `preview-` prefix
- Verifies cert validity via `openssl -checkend 0` before restart
- Restarts `flowmanner-nginx` container

### 9. sandboxd API Token Format Fix

**Root cause:** sandboxd's `parseNamedPairs()` function expects `name=token` (equals separator), but the `.env` had `flowmanner:token` (colon). The parser found no `=` and skipped the entry → zero tokens → all requests 401.

**Fix:** Changed `SANDBOXD_API_TOKENS=flowmanner:37fb...` → `SANDBOXD_API_TOKENS=flowmanner=37fb...` in `sandboxd/.env`. Required `docker compose up -d --force-recreate` (not just `restart`) since `restart` doesn't re-read `.env` variable interpolation.

**⚠️ Gotcha documented:** `SANDBOXD_API_TOKENS` format is `name=token` (equals), NOT `name:token` (colon).

---

## Files Changed Summary

### Backend (Homelab)

| File | Change |
|------|--------|
| `backend/app/api/v1/sandbox_preview.py` | Added `GET /sandbox/forward-auth` endpoint |
| `backend/app/integrations/sandboxd_client.py` | Changed default visibility `public` → `private` |
| `backend/app/config.py` | *(no changes — SANDBOXD_* settings existed from Phase 1)* |

### sandboxd (Homelab)

| File | Change |
|------|--------|
| `/mnt/apps/Softwares2/sandboxd/.env` | Updated 6 env vars (preview domain, TLS, auth, tokens) |
| `/mnt/apps/Softwares2/sandboxd/docker-compose.yml` | Added `extra_hosts: host.docker.internal:host-gateway` to Traefik |
| `/mnt/apps/Softwares2/sandboxd/traefik/dynamic/auth.yml` | Updated forward-auth address to FlowManner backend |
| `/mnt/apps/Softwares2/sandboxd/traefik/dynamic/wake.yml` | Added `sandbox-preview-auth` middleware to catch-all |

### VPS

| File | Change |
|------|--------|
| `/opt/flowmanner/nginx/default.conf` | Added preview server blocks (HTTPS + HTTP redirect) |
| `/opt/flowmanner/certs/preview-*.pem` | Wildcard TLS cert files (3 files) |
| `/opt/flowmanner/scripts/check-certs.sh` | Daily cert expiry monitor |
| `/opt/flowmanner/scripts/renew-preview-certs.sh` | Post-renewal cert copy + nginx restart |

### Infrastructure

| Item | Action |
|------|--------|
| IONOS DNS | `*.preview.flowmanner.com` → `74.208.115.142` A record |
| Let's Encrypt | Wildcard cert via manual DNS-01 challenge |
| Crontab (VPS) | `0 9 * * * /opt/flowmanner/scripts/check-certs.sh` |

---

## Architecture

```
Browser → https://s-abc-3000.preview.flowmanner.com
  → VPS Nginx (TLS termination, wildcard cert)
  → WireGuard tunnel (10.99.0.3:80)
  → Homelab sandboxd Traefik (port 80)
  → forward-auth middleware → FlowManner backend
    → Validates: Bearer token OR fm_refresh_token cookie
    → 200: proxy to sandbox container
    → 401: deny access
  → Docker container (e.g., port 3000 for React dev server)
```

---

## Verification Results

| Check | Result |
|-------|--------|
| `*.preview.flowmanner.com` DNS resolution | ✅ Resolves to `74.208.115.142` |
| TLS certificate validity | ✅ `CN=*.preview.flowmanner.com`, expires Sep 6 2026 |
| SSL verification (`curl`) | ✅ Passed (verify=0) |
| Traefik forward-auth blocks unauthenticated | ✅ 401 Unauthorized |
| Traefik forward-auth blocks invalid cookie | ✅ 401 Unauthorized |
| sandboxd API without token | ✅ 401 Unauthorized |
| sandboxd API with Bearer token | ✅ Auth passes (405 = method not allowed, not auth failure) |
| sandboxd health endpoint | ✅ `ok` |
| WireGuard tunnel (VPS ↔ Homelab) | ✅ `10.99.0.3/24` up, 0% packet loss |
| Nginx config test (`nginx -t`) | ✅ `syntax is ok`, no warnings |
| Nginx container running | ✅ `flowmanner-nginx` up |
| All 61 sandbox tests | ✅ Pass |
| Cert expiry monitor script | ✅ All 3 certs reported healthy |
| Cron job configured | ✅ Daily at 9am UTC |

---

## Code Review Findings (All Addressed)

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | Forward-auth endpoint returns 404 (wrong URL path) | Critical | ✅ Fixed — path corrected from `/api/v1/sandbox/forward-auth` to `/api/sandbox/forward-auth` |
| 2 | `get_current_user` only checks Bearer header, not cookies | Critical | ✅ Fixed — custom `_authenticate_preview_request` checks both Bearer + `fm_refresh_token` cookie |
| 3 | `decode_access_token` vs `decode_refresh_token` for cookie | Concern | ✅ Confirmed correct — `deps.py` line 236 uses `decode_access_token` on `fm_refresh_token` cookie |
| 4 | Untyped `request` parameter | Code quality | ✅ Fixed — typed as `request: Request` (starlette) |
| 5 | Broad `except Exception` masking real errors | Code quality | ✅ Fixed — narrowed to `except (ValueError, TypeError, KeyError)` |
| 6 | Debug-level logging in forward-auth | Code quality | ✅ Fixed — changed to `warning` level |
| 7 | `http2` deprecated in `listen` directive | Deprecation | ✅ Fixed — separated `http2 on;` as standalone directive |
| 8 | IPv6 `listen [::]:443` missing `http2 on;` | Concern | ✅ Verified — `http2 on;` is server-block-level, applies to all listen directives |
| 9 | `renew-preview-certs.sh` missing source file check | Robustness | ✅ Fixed — added `test -f` guard + `openssl -checkend` validation |
| 10 | `check-certs.sh` fails on empty cert directory | Edge case | ✅ Fixed — added `shopt -s nullglob` |
| 11 | Corrupted em-dash in SCP'd script | Deployment | ✅ Fixed — replaced `M-bM-^@M-^T` with `--` |

---

## Lessons Learned

1. **sandboxd `SANDBOXD_API_TOKENS` uses `=` separator, not `:`.** The `parseNamedPairs()` function splits on `=`. Using `name:token` silently produces zero tokens. This was invisible in logs — sandboxd just said "SANDBOXD_API_TOKENS is empty."

2. **`docker compose restart` doesn't re-read `.env` interpolation.** Environment variables set via `${VAR:-default}` in docker-compose require `docker compose up -d --force-recreate` to pick up `.env` changes.

3. **Traefik forward-auth can point to external services.** The middleware just needs `address: "http://host:port/path"` — it doesn't need to be the same service. Using `extra_hosts: host.docker.internal:host-gateway` lets Traefik reach the FlowManner backend.

4. **certbot DNS-01 is inherently interactive.** Without IONOS API credentials, wildcard cert renewal requires manual TXT record addition. The monitoring script + cron job mitigate the risk of forgetting.

5. **`http2 on;` is a server-block-level directive in nginx ≥1.25.1.** One `http2 on;` applies to all listen directives in the block (IPv4 + IPv6). The old `listen 443 ssl http2` syntax is deprecated.

6. **Heredoc over SSH double-escapes special characters.** Em-dashes and other Unicode get corrupted when heredocs pass through SSH + bash quoting. SCP'ing a file is more reliable.

---

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Wildcard cert requires manual DNS-01 renewal | Cert expires Sep 6, 2026 | Daily cron monitor warns at 30 days + renewal helper script |
| No IONOS API credentials for auto-renewal | Manual process | Consider getting IONOS API creds for `certbot-dns-ionos` plugin |
| Forward-auth reimplements auth logic from `deps.py` | Code duplication | Could refactor to use `get_current_session` from deps, but current impl is correct |
| `visibility=private` is global default | All new sandboxes require auth | Callers can pass `visibility="public"` explicitly if needed |
| No security headers on preview nginx block | Minor gap | Traefik handles access control; could add HSTS/X-Frame-Options later |

---

## Verification Checklist

- [x] FlowManner `.env` has all `SANDBOXD_*` entries
- [x] sandboxd `.env` updated (preview domain, TLS, auth, tokens with `=` separator)
- [x] `*.preview.flowmanner.com` DNS resolves to VPS IP
- [x] Wildcard TLS cert issued and valid
- [x] VPS nginx serves `*.preview.flowmanner.com` with valid TLS
- [x] HTTP→HTTPS redirect for preview subdomains
- [x] Traefik forward-auth middleware wired to FlowManner backend
- [x] `wake.yml` catch-all has forward-auth middleware
- [x] Traefik has `extra_hosts` for `host.docker.internal`
- [x] `GET /sandbox/forward-auth` validates sessions via cookie + Bearer
- [x] Unauthenticated preview requests return 401
- [x] `SandboxdClient.create()` defaults to `visibility=private`
- [x] sandboxd API token auth works (colon → equals fix)
- [x] `nginx -t` passes with no warnings
- [x] All 61 sandbox tests pass
- [x] Backend healthy after deploy
- [x] sandboxd healthy after restart
- [x] WireGuard connectivity verified
- [x] Cert expiry monitoring script deployed + cron configured
- [x] Renewal helper script deployed

---

## What's Next: Phase 3+

Remaining work not in Phase 2 scope:

| Item | Description |
|------|-------------|
| Frontend preview button | "🔗 Open Preview" in chat UI with status indicators (⏳/🟢/gray) |
| Auto-renewal setup | IONOS API credentials for `certbot-dns-ionos` plugin |
| Security headers | Add HSTS, X-Frame-Options to preview nginx block |
| Preview URL API endpoint | `GET /api/v1/sandbox/{id}/preview` returns `{preview_url, status}` |
| Log rotation | `/var/log/cert-expiry.log` rotation via logrotate |

---

*End of Phase 2 Exit Audit.*
