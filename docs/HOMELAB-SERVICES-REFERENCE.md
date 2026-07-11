# FlowManner Homelab — Local Services Reference

Everything accessible from the homelab machine (10.99.0.3 / 172.16.1.1) without going through the VPS.

---

## Core Backend Stack

| Service | Port | Access | Notes |
|---------|------|--------|-------|
| **FastAPI Backend** | 8000 | `localhost:8000` | Main API, healthy, Docker container `backend` |
| **Celery Worker** | 8000 (internal) | — | Async task processing, container `celery-worker` |
| **Celery Beat** | 8000 (internal) | — | Scheduled task scheduler, container `celery-beat` |
| **PostgreSQL 15** | 5432 | `localhost:5432` | Primary database, container `workflow-postgres` |
| **Redis 7** | 6379 | `localhost:6379` | Cache + Celery broker, container `workflow-redis` |
| **RabbitMQ 3** | 5672 / 15672 | `localhost:5672` (AMQP), `localhost:15672` (management UI) | Message queue, container `workflow-rabbitmq` |
| **Qdrant v1.12** | 6333-6334 | `localhost:6333` (REST), `localhost:6334` (gRPC) | Vector database, container `workflow-qdrant` |
| **Jaeger** | 4318 / 16686 | `localhost:4318` (OTLP), `localhost:16686` (UI) | Distributed tracing, container `jaeger` |
| **Static files (Nginx)** | 8080 (internal) | — | Serves static assets, container `workflows-static` |

### Quick DB connections

```
# PostgreSQL
psql postgresql://<user>:<pass>@localhost:5432/<db>

# Redis
redis-cli -h localhost -p 6379

# RabbitMQ management
http://localhost:15672
```

---

## Search — SearXNG

| | |
|---|---|
| **URL** | `http://localhost:55510` |
| **Container** | `searxng` |
| **API format** | JSON |
| **No auth** | Open on localhost |

### Usage

```bash
# Basic search (JSON API)
curl -s "http://localhost:55510/search?q=<query>&format=json"

# With categories
curl -s "http://localhost:55510/search?q=<query>&format=json&categories=general,news"

# With language
curl -s "http://localhost:55510/search?q=<query>&format=json&language=en"
```

### For Agents / Scripts

SearXNG is a **private meta-search engine** — it aggregates Google, Bing, DuckDuckGo, etc. without tracking. Any tool that can do HTTP GET can use it:

- Replace `web_search` calls with SearXNG JSON for local, rate-limit-free queries
- No API key needed
- Supports categories: `general`, `news`, `images`, `videos`, `science`, `it`, `files`
- Returns: URL, title, content snippet, engine source

### Example response fields

```json
{
  "query": "test",
  "results": [
    {
      "url": "https://example.com",
      "title": "Example Title",
      "content": "Snippet text...",
      "engines": ["google", "startpage"],
      "score": 12.5
    }
  ]
}
```

---

## Dev Sandboxes — Sandboxd

| | |
|---|---|
| **API** | `http://localhost:9090` |
| **Container** | `sandboxd-sandboxd-1` (control plane) + `sandboxd-traefik-1` (router) |
| **Compose dir** | `/mnt/apps/Softwares2/sandboxd/` |
| **Auth** | Bearer token required |
| **Preview domain** | `*.preview.flowmanner.com` (TLS) |
| **Project** | https://github.com/tastyeffectco/sandboxd |

### Auth

```bash
# Token is stored in: /mnt/apps/Softwares2/sandboxd/.env
# Usage: pass as Bearer token
curl -H "Authorization: Bearer <token>" http://localhost:9090/healthz
# → "ok"
```

### What It Does

Sandboxd creates **isolated Docker containers** that act as per-user dev environments. Each sandbox:

- Gets its own container with a persistent workspace directory
- Can expose ports (default: 3000) with automatic Traefik routing
- **Sleeps when idle** (frees RAM), **wakes instantly** on access
- Includes OpenCode and Claude Code CLIs for AI coding agents
- Gets a unique preview URL: `https://s-<id>-<port>.preview.flowmanner.com`

### API Reference

**Base URL:** `http://localhost:9090`

| Method | Path | Body | Purpose |
|--------|------|------|---------|
| `GET` | `/healthz` | — | Health check |
| `GET` | `/readyz` | — | Readiness check |
| `POST` | `/sandbox` | `{"ports":[3000],"env":{...}}` | Create sandbox |
| `GET` | `/sandboxes` | — | List all sandboxes |
| `GET` | `/sandbox/{id}` | — | Get sandbox details |
| `POST` | `/sandbox/{id}/exec` | `{"cmd":["bash","-lc","..."]}` | Run command |
| `POST` | `/sandbox/{id}/keepalive` | — | Postpone idle reaper |
| `POST` | `/v1/sandboxes/{id}/stop` | — | Stop (frees RAM, wakes on next hit) |
| `DELETE` | `/sandbox/{id}` | — | Destroy container, keep workspace |
| `POST` | `/sandbox/{id}/purge` | — | Destroy and delete workspace |
| `POST` | `/v1/sandboxes/{id}/tasks` | `{"prompt":"...","agent":"opencode"}` | Run AI coding agent |
| `GET` | `/v1/sandboxes/{id}/tasks/{taskId}` | — | Task result |
| `GET` | `/v1/sandboxes/{id}/tasks/{taskId}/events` | — | Live task event stream (SSE) |
| `GET` | `/v1/sandboxes/{id}/files` | `?path=<path>` | List/read workspace files |
| `PUT` | `/v1/sandboxes/{id}/files` | `{"path","content","append"}` | Write workspace files |

### Common Workflows

#### Create a sandbox and serve a web page

```bash
TOKEN="<your-token>"
BASE="http://localhost:9090"

# 1. Create sandbox
SID=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ports":[3000]}' \
  "$BASE/sandbox" | jq -r '.id')

echo "Sandbox ID: $SID"
echo "Preview URL: https://s-${SID}-3000.preview.flowmanner.com"

# 2. Write an HTML file (use base64 to avoid shell escaping issues with HTML)
HTML=$(echo -n '<html><body><h1>Hello from Sandboxd!</h1></body></html>' | base64 -w0)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"cmd\":[\"bash\",\"-lc\",\"echo $HTML | base64 -d > ~/workspace/app/index.html && cd ~/workspace/app && nohup python3 -m http.server 3000 > /dev/null 2>&1 &\"]}" \
  "$BASE/sandbox/$SID/exec"

# 3. Verify it's serving
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cmd":["bash","-lc","curl -s http://localhost:3000/"]}' \
  "$BASE/sandbox/$SID/exec"
```

#### Run a coding agent inside a sandbox

```bash
# Create task (agent builds an app)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build a todo app with React","agent":"opencode"}' \
  "$BASE/v1/sandboxes/$SID/tasks"

# Stream task events (SSE)
curl -s -N -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/sandboxes/$SID/tasks/<taskId>/events"
```

#### Manage sandboxes

```bash
# List all
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/sandboxes" | jq '.[].id'

# Stop (free RAM, keep workspace)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/sandboxes/$SID/stop"

# Purge (delete everything)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$BASE/sandbox/$SID/purge"
```

### Tips

- **HTML in exec commands**: Use base64 encoding to avoid angle-bracket escaping issues with the JSON API
- **Background servers**: Use `nohup ... &` to keep servers running after exec returns
### PREVIEW_DOMAIN Gotcha

sandboxd's Go code **hardcodes** `.preview.` in the host label (`traefik.go:58`):
```go
host := fmt.Sprintf("s-%s-%d.preview.%s", id, p, domain)
```
So `PREVIEW_DOMAIN` must be just the **base domain** (e.g. `flowmanner.com`), NOT `preview.flowmanner.com`. Setting it to `preview.flowmanner.com` produces double `.preview.preview` in the Traefik Host rule, causing TLS name mismatch (cert covers `*.preview.flowmanner.com`, not `*.preview.preview.flowmanner.com`).

### Preview URLs — Full Chain

**URL format:** `https://s-<id>-3000.preview.flowmanner.com`

**Routing chain:**
```
Browser → VPS Nginx (443, wildcard TLS) → WireGuard → Homelab Traefik (:80) → Sandbox container (:3000)
```

**VPS Nginx config** (already in `flowmanner-nginx` container, `/etc/nginx/conf.d/default.conf`):
- Catches `~^(?<subdomain>.+)\.preview\.flowmanner\.com$` on port 80/443
- Wildcard TLS cert at `/etc/nginx/certs/preview.flowmanner.com/` (valid until Sep 2026)
- Proxies to `http://10.99.0.3:80` (homelab Traefik via WireGuard)
- Preserves `Host` header (required — Traefik routes by Host)

**Auth (Traefik forward-auth):**
- Traefik's `sandbox-preview-auth` middleware calls the FlowManner backend at `/api/sandbox/forward-auth`
- Accepts: `Authorization: Bearer <flowmanner_access_token>` OR `fm_refresh_token` httpOnly cookie
- The cookie is set with `Domain=.flowmanner.com` — covers `*.preview.flowmanner.com`
- **Users must be logged into FlowManner** to see preview pages
- No auth → 401 from Traefik (correct security behavior)

**So yes, any sandbox can serve a live page at `https://s-<id>-3000.preview.flowmanner.com`** — it's fully wired end-to-end. The page is gated behind FlowManner auth.

---

## LLM Inference (Systemd, not Docker)

| | |
|---|---|
| **Service** | `llama-server.service` |
| **Port** | `11434` |
| **Model** | Qwen3.6-27B-MTP (Q5_K_M) |
| **Speed** | ~40-48 tok/s |
| **MTP acceptance** | 93.8% |
| **Binary** | `/mnt/apps/llama.cpp-mtp/build/bin/` |
| **API** | OpenAI-compatible |

```bash
# Check status
systemctl status llama-server

# Test
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Hello"}]}'
```

---

## MCP Servers

Two **GitHub MCP Server** containers are running (internal port 8082), used by the Hermes agent for GitHub operations. No direct API interaction needed — accessed via the MCP tool bridge.

---

## Network Diagram

```
                    Homelab (10.99.0.3 / 172.16.1.1)
                    ================================
                    
  localhost:8000 ←→ [Backend FastAPI] ←→ [PostgreSQL :5432]
                                        ←→ [Redis :6379]
                                        ←→ [RabbitMQ :5672]
                                        ←→ [Qdrant :6333]
                                        
  localhost:55510 ←→ [SearXNG] (private meta-search)
  
  localhost:9090  ←→ [Sandboxd Control Plane]
                       ↕ manages
                    [Sandbox Containers] ←→ [Traefik :80]
                                              ↕ routes *.preview
                                           Preview URLs
  
  localhost:11434 ←→ [llama.cpp / Qwen3.6-27B] (systemd)
  
  localhost:16686 ←→ [Jaeger] (tracing UI)
  
  VPS (74.208.115.142)
    │
    ├── flowmanner.com → Frontend (Next.js)
    ├── /api/* → WireGuard → Homelab :8000
    └── *.preview.flowmanner.com → WireGuard → Homelab Traefik :80 (needs config)
```
➜  ~ grep SANDBOXD_API_TOKENS /mnt/apps/Softwares2/sandboxd/.env

#   SANDBOXD_API_TOKENS=name1:secret1,name2:secret2
SANDBOXD_API_TOKENS=flowmanner=REDACTED_SANDBOXD_TOKEN
➜  ~ 










