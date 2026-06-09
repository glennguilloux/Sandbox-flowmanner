# Virtual HTML Preview — sandboxd Live URL Feature

**Status:** Ready
**Owner:** DeepSeek
**Priority:** High (major feature, infrastructure done, needs polish + chat wiring)
**Estimated effort:** ~200 lines across 4 files (backend tool docs, frontend UX, agent system prompt)

---

## Summary

When a user asks a FlowManner agent to build something (a landing page, a dashboard, a tool), the agent spins up a Docker sandbox via sandboxd, writes the code inside, starts a dev server, and returns a clickable live preview URL like:

```
https://s-<sandbox-id>-3000.preview.flowmanner.com
```

This is the "virtual HTML" feature. The infrastructure (sandboxd, DNS, TLS, nginx, backend client, frontend components, VPS routing) is already built across Phases 1-4. This plan focuses on **polish and chat UX integration** so the feature feels seamless to users.

---

## Existing Infrastructure (DO NOT rebuild)

### sandboxd (Docker service on homelab)

| Resource | Location | Notes |
|---|---|---|
| sandboxd control plane | `/mnt/apps/Softwares2/sandboxd/` | Docker Compose, API on `127.0.0.1:9090` |
| sandboxd Traefik | Port 80 on host | Routes `Host: s-<id>-<port>.preview.flowmanner.com` → container |
| Auth | `SANDBOXD_API_TOKENS=flowmanner:...` in `.env` | Bearer token auth enabled |
| Preview domain | `PREVIEW_DOMAIN=preview.flowmanner.com` | In sandboxd `.env` |
| Base image | `sandboxd-base:1.0.0` | Node 22, Python 3.12, Go, pnpm, uv, bun, Claude Code, OpenCode |
| Templates | `react-standard`, `python`, `node` | ID assigned to `POST /v1/sandboxes` |

### Backend (FastAPI on homelab, port 8000)

| Resource | File | Notes |
|---|---|---|
| sandboxd client | `backend/app/integrations/sandboxd_client.py` | Full async client, 357 lines, all v1 endpoints + internal exec |
| SandboxService | `backend/app/services/sandbox_service.py` | Mission-scoped lifecycle (create, reap) |
| PlaygroundService | `backend/app/services/playground_service.py` | Anonymous sandboxes, claim, TTL, rate limits |
| Sandbox preview API | `backend/app/api/v1/sandbox_preview.py` | `GET /api/v1/sandbox/{id}/preview` + forward-auth + URL rewrite |
| Playground API | `backend/app/api/v1/playground.py` | `POST /api/v1/playground/sandboxes`, claim, file browser |
| Admin API | `backend/app/api/v1/admin_sandboxes.py` | Admin sandbox management |
| Agent tools | `backend/app/tools/sandboxd_*.py` | 5 tools: exec, file_read, file_write, file_list, preview |
| Mission executor | `backend/app/services/mission_executor.py:322-343` | Auto-creates sandbox per mission, sets context |
| Settings | `backend/app/config.py` | `SANDBOXD_API_URL`, `SANDBOXD_AUTH_TOKEN`, `SANDBOXD_PREVIEW_DOMAIN`, `SANDBOXD_ENABLED=True` |
| Cleanup | `backend/app/tasks/playground_cleanup.py` | Celery task for expired sandbox purge |

### Frontend (Next.js, on VPS via deploy)

| Resource | File | Notes |
|---|---|---|
| SandboxPreviewButton | `src/components/chat/SandboxPreviewButton.tsx` | Polls status, shows spinner/green link/stopped/error |
| ToolActivityFeed | `src/components/chat/ToolActivityFeed.tsx:240-242` | Renders `SandboxPreviewButton` when tool produces sandbox |
| SandboxPlayground | `src/components/sandbox/SandboxPlayground.tsx` | Template selector, create, claim, expiry countdown |
| Playground page | `src/app/[locale]/developers/playground/` | API explorer page |
| sandbox-api lib | `src/lib/sandbox-api.ts` | Frontend client for playground API |
| useSandboxPlayground | `src/hooks/useSandboxPlayground.ts` | React hook for playground state |
| getSandboxPreview | `src/lib/api/io.ts:153` | `GET /api/v1/sandbox/{id}/preview` caller |

### Infrastructure (VPS + DNS + TLS)

| Resource | Location | Notes |
|---|---|---|
| DNS | IONOS: `*.preview  A  74.208.115.142` | Wildcard → VPS |
| VPS nginx | Docker container `flowmanner-nginx` | Routes `*.preview.flowmanner.com` → `http://10.99.0.3:80` (sandboxd Traefik via WireGuard) |
| Wildcard TLS | `/etc/nginx/certs/preview.flowmanner.com/` | ECDSA, valid until 2026-09-06 |
| WireGuard | `10.99.0.1` (VPS) ↔ `10.99.0.3` (homelab) | Preview traffic tunnels over WG |

---

## Data Flow

```
User: "Build me a landing page for my startup"
  │
  ├─ 1. Agent receives mission, mission_executor creates sandbox
  │     POST sandboxd /v1/sandboxes {project, user_id}
  │     sandboxd spins up Docker container (sandboxd-base:1.0.0 image)
  │
  ├─ 2. Agent uses tools to build:
  │     sandboxd_file_write(sandbox_id, "index.html", "<!DOCTYPE...")
  │     sandboxd_file_write(sandbox_id, "style.css", "body { ...")
  │     sandboxd_exec(sandbox_id, ["npm", "run", "dev"])
  │
  ├─ 3. sandboxd Traefik detects port 3000, assigns preview URL:
  │     s-<sandbox_id>-3000.preview.flowmanner.com
  │
  ├─ 4. Agent calls sandboxd_preview(sandbox_id) → gets URL
  │     OR backend GET /api/v1/sandbox/{id}/preview rewrites URL
  │
  ├─ 5. Frontend ToolActivityFeed renders SandboxPreviewButton
  │     Polls every 3s while "creating" → shows green "Open Preview" when ready
  │
  └─ 6. User clicks → browser → VPS:443 → nginx rewrites to 10.99.0.3:80
        → sandboxd Traefik routes by Host header → sandbox container :3000
```

---

## What's Working vs What Needs Work

### ✅ Working

- Backend client talks to sandboxd API with auth
- Missions auto-create sandboxes
- 5 sandboxd tools registered and functional
- Preview button appears in chat when sandbox tool runs
- DNS wildcard routes to VPS
- VPS nginx proxies to sandboxd Traefik via WireGuard
- TLS cert valid and serving
- Playground page creates anonymous sandboxes
- URL rewriting (`.preview.localhost` → `.preview.flowmanner.com`)
- Forward-auth endpoint gating preview access

### 🔧 Needs Work

1. **Auth token in backend .env** — `SANDBOXD_AUTH_TOKEN` defaults to empty string in config. The sandboxd client sends `Authorization: Bearer {token}` but no token is configured. Check whether the backend actually works against sandboxd with auth enabled. If sandboxd's internal API (on same host) bypasses auth, this may work already — verify.

2. **Agent system prompt doesn't mention sandboxd tools** — FlowManner agents (LLMs) need to know they have `sandboxd_exec`, `sandboxd_file_write`, `sandboxd_file_read`, `sandboxd_file_list`, `sandboxd_preview` available. These are registered as tools but the agent may not know to use them for "build me an HTML page" requests. The system prompt or tool descriptions need to guide agents to use sandboxd for multi-file/frontend tasks.

3. **Preview URL only appears for missions** — The `SandboxPreviewButton` is rendered in `ToolActivityFeed` when a tool returns `sandboxId`. This works for missions (which auto-create sandboxes) but direct chat messages without missions may not get a sandbox. Need a convention: chat agents should create sandboxes via `sandboxd_preview` tool that auto-provisions one.

4. **No "Build & Preview" quick action** — The playground page is a standalone creation flow. There's no way in chat to say "preview this" and get a sandbox. Consider adding a `sandboxd_preview` tool that creates a sandbox on first call and returns the URL.

5. **Sandbox idle timeout = 35 min** — sandboxd's idle reaper kills containers after 2100 seconds. For long-running previews, the frontend could call the keepalive endpoint or warn users.

---

## Implementation Steps

### Step 1: Verify end-to-end pipeline works

**File:** none (verification only)

```bash
# 1. Verify sandboxd responds to auth requests
curl -s http://127.0.0.1:9090/v1/sandboxes \
  -H "Authorization: Bearer ${SANDBOXD_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"project":{"id":"verify","user_id":"test"},"template":"react-standard","visibility":"private"}'

# 2. Write a test HTML file to the sandbox
curl -s -X PUT "http://127.0.0.1:9090/v1/sandboxes/<id>/files?path=index.html" \
  -H "Authorization: Bearer ${SANDBOXD_TOKEN}" \
  --data-binary '<!DOCTYPE html><html><body><h1>Hello</h1></body></html>'

# 3. Start a dev server
curl -s -X POST "http://127.0.0.1:9090/sandbox/<id>/exec" \
  -H "Authorization: Bearer ${SANDBOXD_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"cmd":["bash","-lc","cd /home/sandbox/workspace && python3 -m http.server 3000 &"]}'

# 4. Hit the preview URL from the homelab
curl -sI "http://s-<id>-3000.preview.flowmanner.com" -H "Host: s-<id>-3000.preview.flowmanner.com"

# 5. Clean up
curl -s -X DELETE "http://127.0.0.1:9090/v1/sandboxes/<id>" \
  -H "Authorization: Bearer ${SANDBOXD_TOKEN}"
```

### Step 2: Fix auth token in backend config

**File:** `backend/app/config.py` (line 160)

The `SANDBOXD_AUTH_TOKEN` default is `""` but sandboxd has auth enabled. The token value is `flowmanner` (from sandboxd's `.env`: `SANDBOXD_API_TOKENS=flowmanner:...`). Set it in the backend `.env`:

```bash
# Add to /opt/flowmanner/backend/.env:
SANDBOXD_AUTH_TOKEN=flowmanner
```

Or pass it as an environment variable to the Docker container:

```yaml
# In docker-compose.yml, under backend service:
environment:
  SANDBOXD_AUTH_TOKEN: flowmanner
```

**Rebuild:** After changing `.env`, rebuild and restart the backend:
```bash
cd /opt/flowmanner
docker build -t workflows-backend:restored backend/
docker compose up -d --no-deps --force-recreate backend celery-worker
```

### Step 3: Enhance agent tool descriptions for HTML building

**Files:**
- `backend/app/tools/sandboxd_exec.py`
- `backend/app/tools/sandboxd_file_write.py`
- `backend/app/tools/sandboxd_preview.py`

Update tool descriptions so agents understand when to use sandboxd vs subprocess sandboxes:

```python
# In sandboxd_exec.py — update the description field:
description = (
    "Execute a shell command inside an isolated Docker sandbox. "
    "Use this for multi-file projects, frontend apps, or anything "
    "that needs a real filesystem and dev server. "
    "Commands run with bash -lc for proper shell environment. "
    "PREFER this over `sandboxd_exec` for: building HTML pages, "
    "React apps, Python web servers, or any multi-file project "
    "that should be previewed at a live URL."
)
```

```python
# In sandboxd_file_write.py — update the description:
description = (
    "Write a file to the sandbox workspace. Use this to create "
    "index.html, style.css, app.js, or any project file. "
    "Files are persisted across exec calls. "
    "For HTML previews: write index.html, then use exec to start "
    "a dev server, then use sandboxd_preview to get the live URL."
)
```

```python
# In sandboxd_preview.py — update the description:
description = (
    "Get the live preview URL for a sandbox. If no sandbox_id is "
    "provided, creates a new sandbox automatically. "
    "The preview URL is publicly accessible at "
    "s-<id>-3000.preview.flowmanner.com. "
    "Always call this after writing HTML files and starting a dev server."
)
```

### Step 4: Add system prompt guidance for sandboxd

**File:** Backend agent definition or system prompt template (check `backend/app/agent_definitions/`)

Add to the agent's system instructions:

```markdown
## Sandboxd Preview Tools

When the user asks you to build something visual (landing page, dashboard,
chart, tool, app), use the sandboxd tools to create a live preview:

1. **sandboxd_preview** — call without arguments to create a new sandbox.
   Returns the sandbox_id. Save this for subsequent calls.
2. **sandboxd_file_write** — write your HTML/CSS/JS files to the sandbox
   workspace. Start with index.html.
3. **sandboxd_exec** — run shell commands inside the sandbox. Use this to
   start a dev server: `["bash", "-lc", "npx serve -l 3000"]` or
   `["bash", "-lc", "python3 -m http.server 3000"]`.
4. **sandboxd_preview(sandbox_id)** — call again to get the live preview URL.
   Share this URL with the user in your response.

The preview URL format is:
https://s-<sandbox_id>-3000.preview.flowmanner.com

The URL is publicly accessible. The sandbox stays alive for 35 minutes.
```

### Step 5: Wire up standalone sandbox creation in chat (non-mission)

**File:** `backend/app/tools/sandboxd_preview.py`

The `sandboxd_preview` tool should handle the case where no sandbox exists yet. Currently it returns a preview URL for an existing sandbox. Enhance it to auto-create a sandbox if called without a sandbox_id, or if the provided sandbox_id doesn't exist:

```python
# Pseudocode for sandboxd_preview tool execution:
async def execute(sandbox_id=None):
    client = get_sandboxd_client()
    
    # If no sandbox_id, create one for this chat session
    if not sandbox_id:
        sandbox_id = get_current_sandbox_id()  # from context
        if not sandbox_id:
            result = await client.create(
                project_id=f"chat-{uuid4().hex[:12]}",
                user_id=str(current_user.id),
            )
            sandbox_id = result["id"]
            set_current_sandbox_id(sandbox_id)
    
    # Get preview info
    info = await client.get(sandbox_id)
    preview = info.get("preview", {})
    return {
        "sandbox_id": sandbox_id,
        "preview_url": _rewrite_url(preview.get("url")),
        "status": info.get("status"),
    }
```

### Step 6: Add "Open Preview" inline in chat message responses

**File:** `frontend/src/components/chat/ToolActivityFeed.tsx` (already done at line 240-242)

Verify the current wiring works: when a tool call produces `sandboxId` in its result, the `ToolActivityFeed` renders a `SandboxPreviewButton`. No code changes needed — just verify this path:

```
Agent calls sandboxd_preview
  → tool result includes sandbox_id
  → ToolActivityFeed detects sandboxId field
  → Renders <SandboxPreviewButton sandboxId={tool.sandboxId} />
  → Button polls GET /api/v1/sandbox/{id}/preview every 3s
  → Shows green "Open Preview" link when ready
```

### Step 7: Test end-to-end

```bash
# From homelab:
# 1. Create a sandbox via frontend playground
curl -X POST http://127.0.0.1:8000/api/v1/playground/sandboxes?template=react-standard

# 2. Write index.html to the sandbox
curl -X PUT "http://127.0.0.1:9090/v1/sandboxes/<id>/files?path=index.html" \
  -H "Authorization: Bearer flowmanner" \
  --data-binary '<!DOCTYPE html><html><head><title>Test</title></head><body><h1>It works!</h1></body></html>'

# 3. Start a dev server via exec
curl -X POST "http://127.0.0.1:9090/sandbox/<id>/exec" \
  -H "Authorization: Bearer flowmanner" \
  -H "Content-Type: application/json" \
  -d '{"cmd":["bash","-lc","cd /home/sandbox/workspace && python3 -m http.server 3000"]}'

# 4. Hit preview via public URL
curl -sI "https://s-<id>-3000.preview.flowmanner.com"
# Expect: HTTP/2 200, content-type: text/html, body contains "It works!"

# 5. Verify the preview API returns correct URL
curl -s http://127.0.0.1:8000/api/v1/sandbox/<id>/preview
```

---

## Files Summary

### Files to Modify (existing)

| File | Change | ~LOC |
|---|---|---|
| `backend/app/tools/sandboxd_exec.py` | Better description for HTML building use case | +15 |
| `backend/app/tools/sandboxd_file_write.py` | Better description mentioning preview workflow | +15 |
| `backend/app/tools/sandboxd_preview.py` | Auto-create sandbox if none exists | +40 |
| `backend/app/config.py` | Ensure SANDBOXD_AUTH_TOKEN is set | +1 |
| `backend/.env` | Add SANDBOXD_AUTH_TOKEN | +1 |

### Files to Create (new)

None needed — all plumbing exists. This is a wiring + polish pass.

### No Changes Needed

- DNS (IONOS *.preview → VPS — done)
- TLS cert (valid until 2026-09-06 — done)
- VPS nginx (preview server block — done)
- sandboxd (container + Traefik running — done)
- SandboxdClient (all v1 endpoints covered — done)
- Playground API (anonymous sandboxes work — done)
- SandboxPreviewButton (polls correctly — done)
- ToolActivityFeed (renders preview button — done)
- Mission executor (auto-creates sandboxes — done)

---

## Edge Cases & Design Constraints

1. **Sandbox idle timeout = 35 minutes.** sandboxd's idle reaper kills stopped containers. The preview button should warn users when a sandbox is close to expiry. The `SandboxPreviewButton` polls every 3s only while "creating" — consider adding a TTL countdown display.

2. **No dev server == no preview URL.** If the agent writes files but forgets to start a dev server, the preview URL will return 502 (bad gateway from Traefik). The tool descriptions should emphasize the "start a dev server" step. The `SandboxPreviewButton` already handles "running (no dev server)" state with a yellow indicator.

3. **Anonymous users can't create sandboxes in missions.** Mission sandboxes require auth. The playground API is anonymous — but playground sandboxes are separate from mission sandboxes. An anonymous chat user would need the playground path.

4. **Concurrent sandbox limit.** sandboxd doesn't enforce a hard limit, but Docker and memory constraints apply. The playground rate-limits: 1 per IP per 60s, max 10 per hour.

5. **Preview forwarding auth.** The forward-auth endpoint (`GET /sandbox/forward-auth`) gates preview URLs behind FlowManner sessions. Browser cookies (`fm_refresh_token`) are checked. External users without a session get 401 and can't see the preview.

6. **URL rewriting.** sandboxd returns `http://s-<id>-3000.preview.localhost` (or `https://...`). The backend rewrites to `https://s-<id>-3000.preview.flowmanner.com`. This happens in both `sandbox_preview.py` and `playground.py`.

---

## Acceptance Criteria

- [ ] Backend auth token configured and sandboxd client can create sandboxes with auth
- [ ] Agent tool descriptions mention "use sandboxd for HTML/frontend projects"
- [ ] Agent system prompt includes sandboxd preview workflow instructions
- [ ] `sandboxd_preview` tool auto-creates sandbox when called without an ID
- [ ] Chat agent can: create sandbox → write index.html → start dev server → return preview URL
- [ ] SandboxPreviewButton shows green "Open Preview" link in chat when sandbox is running
- [ ] Preview URL resolves at `https://s-<id>-3000.preview.flowmanner.com` and shows the HTML
- [ ] Anonymous playground sandboxes get a preview URL and can be claimed by logged-in users
- [ ] Forward-auth works: unauthenticated users get 401 on private sandbox previews
- [ ] Idle reaper doesn't kill sandbox mid-work (agent uses keepalive for long tasks)
