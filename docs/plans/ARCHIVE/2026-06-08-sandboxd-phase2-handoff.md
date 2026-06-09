# sandboxd Integration — Phase 2 Handoff

**Date:** June 8, 2026
**Prerequisite:** Phase 1 complete ✅ (see `docs/plans/2026-06-08-sandboxd-phase1-exit-audit.md`)

---

## Copy-Paste Prompt for New Session

```
I need to implement Phase 2 of the sandboxd integration for FlowManner — live preview URLs.

CONTEXT:
- Phase 1 is complete: 5 sandboxd tools (exec, file_read, file_write, file_list, preview) are registered in tools_catalog and working. 51 unit tests pass. 10/10 smoke test passes.
- sandboxd runs on the homelab (10.99.0.3), VPS is 74.208.115.142
- Backend is FastAPI on the homelab, frontend is Next.js on the VPS
- sandboxd currently binds to 127.0.0.1:9090 (internal API) and has Traefik on port 80 for preview routing
- sandboxd preview URL format: s-<id>-<port>.preview.<domain>
- Auth is currently DISABLED (SANDBOXD_API_AUTH_DISABLED=true)
- sandboxd .env still has dev defaults: PREVIEW_DOMAIN=localhost, PREVIEW_TLS=false, auth disabled
- FlowManner .env has ZERO SANDBOXD_* entries — all must be added in Step 2

PHASE 2 DELIVERABLES:

1. INFRASTRUCTURE (manual steps — I'll do these):
   - Wildcard DNS: *.preview.flowmanner.com → 74.208.115.142
   - Wildcard TLS cert via DNS-01 (certbot + IONOS API)
   - sandboxd .env: PREVIEW_DOMAIN=preview.flowmanner.com, PREVIEW_TLS=true, auth enabled

2. VPS NGINX (you help with config):
   - Add server block in /opt/flowmanner/nginx/default.conf
   - Route *.preview.flowmanner.com → homelab sandboxd Traefik via WireGuard (10.99.0.3:80)
   - Preserve Host header for Traefik Host-based routing
   - WebSocket upgrade support for HMR

3. BACKEND API (you implement):
   - New file: backend/app/api/v1/sandbox_preview.py
   - GET /api/v1/sandbox/{sandbox_id}/preview → returns {preview_url, status, sandbox_id}
   - Uses existing SandboxdClient.get() which already normalizes response
   - Tests: backend/tests/test_sandbox_preview_api.py

4. SANDBOXD AUTH (you help configure):
   - Generate token, add to FlowManner .env as SANDBOXD_AUTH_TOKEN
   - SandboxdClient already sends Bearer token — no code changes needed

5. FORWARD AUTH (you implement):
   - sandboxd exposes GET /forward-auth for Traefik forward auth
   - Gate preview URLs behind FlowManner session auth
   - Only authenticated users can access sandbox previews

6. FRONTEND (you implement):
   - Preview button in chat UI with status indicators (⏳ spinning / 🟢 ready / gray stopped)
   - Frontend source: /home/glenn/FlowmannerV2-frontend/ on homelab

KEY FILES TO READ FIRST:
- backend/app/integrations/sandboxd_client.py (Phase 1 client)
- backend/app/services/sandbox_service.py (Phase 1 service)
- backend/app/config.py (SANDBOXD_* settings)
- nginx/default.conf (current VPS nginx config)
- plans/sandboxd-integration-roadmap.md § Phase 2 (full plan)
- docs/plans/2026-06-08-sandboxd-phase1-exit-audit.md (what was built)

ARCHITECTURE:
User's browser → *.preview.flowmanner.com (VPS 74.208.115.142)
  → VPS Nginx (TLS termination)
  → WireGuard tunnel (10.99.0.3)
  → Homelab sandboxd Traefik (port 80)
  → Docker container port (e.g., 3000)

FRONTEND SOURCE: /home/glenn/FlowmannerV2-frontend/ on the homelab (deployed to VPS via deploy-frontend.sh)
sandboxd .env LOCATION: /mnt/apps/Softwares2/sandboxd/.env

START WITH: Read the key files above, then implement the backend preview API endpoint and tests. I'll handle DNS and TLS separately.
```

---

## Phase 2 Current State Assessment

### What Exists (from Phase 1)

| Component | Status | Notes |
|-----------|--------|-------|
| `SandboxdClient.get()` | ✅ Working | Returns normalized `{id, status, preview: {url, status}}` |
| `sandboxd_preview.py` tool | ✅ Registered | Agent tool that calls `client.get()` and returns preview info |
| `SANDBOXD_PREVIEW_DOMAIN` config | ✅ Set in `config.py` | ⚠️ sandboxd `.env` still has `PREVIEW_DOMAIN=localhost` — must be updated in Step 3 |
| `mission_sandboxes` table | ✅ Migrated | Tracks sandbox_id per mission |
| sandboxd Traefik | ✅ Running | Listens on port 80, does Host-based routing |
| sandboxd preview URL format | ✅ Known | `s-<id>-<port>.preview.<domain>` per exposed port |

### What's Missing (Phase 2 scope)

| Component | Status | Blocker? |
|-----------|--------|----------|
| `*.preview.flowmanner.com` DNS | 🔴 Not resolving | Yes — needs IONOS A record |
| Wildcard TLS cert | 🔴 Not configured | Yes — needs certbot DNS-01 |
| VPS Nginx preview routing | 🔴 No `*.preview` server block | Yes — needs nginx config |
| sandboxd prod `.env` | ⚠️ Exists but still has dev defaults (`PREVIEW_DOMAIN=localhost`, `PREVIEW_TLS=false`, auth disabled) | Yes — needs PREVIEW_DOMAIN, TLS, auth updates |
| Backend preview API endpoint | 🔴 Not started | No — can build without infra |
| Frontend preview button | 🔴 Not started | No — can build without infra |
| Forward auth | 🔴 Not started | No — can add after basic routing works |

---

## Implementation Order

### Step 1: Backend Preview API (no infra needed)

Create `backend/app/api/v1/sandbox_preview.py`:

```python
from fastapi import APIRouter, HTTPException
from app.integrations.sandboxd_client import SandboxdClient
from app.config import settings

router = APIRouter(prefix="/sandbox", tags=["sandbox-preview"])

@router.get("/{sandbox_id}/preview")
async def get_preview_url(sandbox_id: str) -> dict:
    """Return the live preview info for a sandbox."""
    client = SandboxdClient(
        base_url=settings.SANDBOXD_API_URL,
        auth_token=settings.SANDBOXD_AUTH_TOKEN or None,
    )
    try:
        resp = await client.get(sandbox_id)
        preview = resp.get("preview", {})
        return {
            "preview_url": preview.get("url"),
            "status": preview.get("status", "unknown"),
            "sandbox_id": sandbox_id,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Sandbox not found: {e}")
```

Write tests in `backend/tests/test_sandbox_preview_api.py`.

### Step 2: sandboxd Auth Setup

`SandboxdClient` already sends `Authorization: Bearer <token>` when `auth_token` is non-empty (see `_get_client()` in `sandboxd_client.py`). No code changes needed — just configure the token:

```bash
# Generate token
openssl rand -hex 32
```

**In `/mnt/apps/Softwares2/sandboxd/.env`** (update existing entries):
```bash
PREVIEW_DOMAIN=preview.flowmanner.com          # was: localhost
PREVIEW_ENTRYPOINT=websecure                    # was: web
PREVIEW_TLS=true                                # was: false
SANDBOXD_API_AUTH_DISABLED=false                # was: true
SANDBOXD_API_TOKENS=flowmanner=<generated-token>  # was: empty
SANDBOXD_SET_MEMORY_HIGH=true                   # was: false
```

**In FlowManner `.env`** (add all SANDBOXD_* entries — currently NONE exist):
```bash
SANDBOXD_API_URL=http://127.0.0.1:9090
SANDBOXD_AUTH_TOKEN=<generated-token>
SANDBOXD_PREVIEW_DOMAIN=preview.flowmanner.com
SANDBOXD_ENABLED=true
SANDBOXD_DEFAULT_TEMPLATE=react-standard
```

Restart sandboxd: `cd /mnt/apps/Softwares2/sandboxd && docker compose down && docker compose up -d`
Restart backend: `bash /opt/flowmanner/deploy-backend.sh`

### Step 3: Infrastructure (manual, no code)

1. IONOS DNS: Add `*.preview.flowmanner.com` A record → `74.208.115.142`
2. VPS certbot: `certbot certonly --manual --preferred-challenges dns -d '*.preview.flowmanner.com'`
3. sandboxd .env (`/mnt/apps/Softwares2/sandboxd/.env`): Update existing file — change these entries:
   ```bash
   PREVIEW_DOMAIN=preview.flowmanner.com          # was: localhost
   PREVIEW_ENTRYPOINT=websecure                    # was: web
   PREVIEW_TLS=true                                # was: false
   SANDBOXD_API_AUTH_DISABLED=false                # was: true
   SANDBOXD_API_TOKENS=flowmanner=<generated-token>  # was: empty
   SANDBOXD_SET_MEMORY_HIGH=true                   # was: false
   ```
4. Restart sandboxd: `cd /mnt/apps/Softwares2/sandboxd && docker compose down && docker compose up -d`

### Step 4: VPS Nginx Preview Routing

Add to `nginx/default.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name ~^(?<subdomain>.+)\.preview\.flowmanner\.com$;

    ssl_certificate /etc/letsencrypt/live/preview.flowmanner.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/preview.flowmanner.com/privkey.pem;

    location / {
        proxy_pass http://10.99.0.3:80;  # sandboxd Traefik via WireGuard
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

Deploy: `bash /opt/flowmanner/deploy-frontend.sh` (rsyncs nginx config to VPS)

### Step 5: Frontend Preview Button

Frontend source: `/home/glenn/FlowmannerV2-frontend/` on the homelab.

In the chat message renderer, detect `preview_url` in tool results and render a preview card:

```tsx
// In the tool result renderer component
{result.preview_url && (
  <div className="sandbox-preview-card">
    {result.status === 'running' && (
      <>
        <span className="status-dot green">●</span>
        <span>Dev server running</span>
        <a href={result.preview_url} target="_blank" rel="noopener noreferrer">
          🔗 Open Preview
        </a>
      </>
    )}
    {(result.status === 'starting' || result.status === 'creating') && (
      <>
        <span className="spinner" />
        <span>Sandbox starting…</span>
      </>
    )}
    {result.status === 'stopped' && (
      <>
        <span className="status-dot gray">●</span>
        <span>Sandbox stopped</span>
      </>
    )}
  </div>
)}
```

Deploy: `bash /opt/flowmanner/deploy-frontend.sh`

### Step 6: Forward Auth (security hardening)

sandboxd exposes `GET /forward-auth` — a Traefik forward-auth endpoint that validates cookies/JWT. Configure Traefik middleware on preview routes to call this endpoint before proxying to the sandbox. This gates all preview URLs behind FlowManner session auth.

Traefik middleware config (in sandboxd's docker-compose labels or Traefik dynamic config):
```yaml
middlewares:
  flowmanner-auth:
    forwardAuth:
      address: "http://localhost:9090/forward-auth"
      trustForwardHeader: true
```

This is optional for initial launch but recommended before exposing to users.

---

## Key Technical Details

### sandboxd Preview URL Format

```
s-<sandbox-id>-<port>.preview.<domain>
```

Examples:
- `s-abc123-3000.preview.flowmanner.com` (React dev server)
- `s-abc123-8080.preview.flowmanner.com` (API server)

Each exposed port gets its own subdomain. Traefik routes based on `Host` header.

### sandboxd Traefik Routing

sandboxd's Traefik uses label-based routing:
- Priority 100: Active sandboxes (specific Host match)
- Priority 1: Catch-all for wake path

The `Host` header must be preserved through Nginx proxy for Traefik to match.

### Internal vs v1 API for Preview

`GET /v1/sandboxes/{id}` returns:
```json
{
  "id": "sb-abc",
  "status": "running",
  "preview": {
    "url": "http://s-abc-3000.preview.localhost",
    "status": "running"
  }
}
```

`GET /sandbox/{id}` (internal) returns:
```json
{
  "row": {
    "id": "sb-abc",
    "state": "running",
    ...
  }
}
```

Phase 1's `SandboxdClient.get()` already normalizes both to a consistent shape with `status` and `preview` fields.

### Auth Flow

sandboxd auth is Bearer token based:
```
Authorization: Bearer <SANDBOXD_API_TOKENS value>
```

The token is set in sandboxd's `.env` as `SANDBOXD_API_TOKENS=flowmanner=<token>`.

Forward auth (`GET /forward-auth`) is a separate mechanism for gating preview URLs behind session cookies, not API tokens.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| DNS propagation delay | Medium | Low | Wait up to 48h, test with `dig` |
| IONOS API certbot plugin unavailable | Low | High | Use manual DNS-01 challenge instead |
| Traefik Host routing mismatch | Medium | High | Test with curl, verify Host header preserved |
| sandboxd auth breaks existing tools | Low | Medium | Add auth token to SandboxdClient, test all 5 tools |
| Preview URL not accessible from browser | Medium | High | Check firewall, WireGuard, Traefik logs |

---

## Verification Checklist (Phase 2)

- [ ] `dig s-test-3000.preview.flowmanner.com` → resolves to VPS IP
- [ ] `curl -v https://s-test-3000.preview.flowmanner.com` → TLS handshake OK
- [ ] `GET /api/v1/sandbox/{id}/preview` → returns preview URL and status
- [ ] Create sandbox with dev server → preview URL loads app in browser
- [ ] Multiple concurrent sandboxes → each has unique, working preview URL
- [ ] Sandbox stopped → wake path shows "warming up" page → auto-refreshes
- [ ] Sandbox destroyed → preview URL returns 502/503
- [ ] Auth enabled → unauthenticated preview access returns 401/403
- [ ] Auth enabled → FlowManner API calls still work with Bearer token
- [ ] Chat UI shows preview button with correct status indicators
- [ ] `pytest backend/tests/test_sandbox_preview_api.py -v` → all pass

---

*End of Phase 2 Handoff.*
