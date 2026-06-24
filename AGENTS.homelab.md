# Flowmanner — Homelab Agent Instructions

## ⚠️ CRITICAL RULES (read before anything else)

- NEVER edit files on the VPS. All edits on homelab: /home/glenn/FlowmannerV2-frontend/
- NEVER SSH VPS without the key file: `ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142`
- Source edits NEVER take effect without rebuild. Deploy: `bash /opt/flowmanner/deploy-frontend.sh`
  ⚠️ **DEPLOY TIMING: `deploy-frontend.sh` takes ~4 minutes** (rsync ~30s + docker build ~2min + restart + 10 health checks at 5s each). Use `timeout=300` or `background=true, notify_on_complete=true`. If it times out, do NOT retry blindly — check if it actually completed: `ssh -i ~/.ssh/vps_flowmanner_new root@74.208.115.142 "cd /opt/flowmanner && docker compose ps"` and check the image creation time. Repeated retries that timeout are a sign the previous one may have succeeded or is still running.
- After deploy, verify: login works, nav shows Dashboard after login, chat no 401, no offline banner
- Two auth systems: NextAuth JWT cookie + Zustand localStorage key "fm_tokens". Both must agree.
- LocalStorage key is "fm_tokens" (SSH output filter may show "***" — ignore, real key is fm_tokens)
- **Always verify suspicious `***` values with `od -c` or Python `repr()` before acting**

---

## ⚠️ YOU ARE ON THE HOMELAB

This machine is the **homelab** at `10.99.0.3` / `172.16.1.1`.

You are NOT on the VPS. The VPS is a SEPARATE machine at `74.208.115.142` (WireGuard: `10.99.0.1`) — you reach it via SSH with key auth. Do NOT tell the user to "run commands on the homelab" — you are already here. Just run commands directly.

## Homelab Role

The homelab runs the **API backend and data stores**. The VPS proxies public traffic here through a WireGuard tunnel.

```
VPS (10.99.0.1) → WireGuard → Homelab (10.99.0.3:8000) → FastAPI backend
                                                     → PostgreSQL (:5432)
                                                     → Redis (:6379)
                                                     → Qdrant (:6333)
                                                     → RabbitMQ (:5672)
                                                     → Celery workers
                                                     → Celery beat
                                                     → Jaeger (:16686)
```

## Paths

| What | Path | Notes |
|------|------|-------|
| Project root | `/opt/flowmanner/` | Docker Compose lives here |
| Backend source | `/opt/flowmanner/backend/` | Dockerfile, app/, alembic/, mcp_gateway/ |
| Frontend source (local) | `/home/glenn/FlowmannerV2-frontend/` | rsync'd to VPS for deploy |
| Docker Compose | `/opt/flowmanner/docker-compose.yml` | THIS is the compose file |
| Environment | `/opt/flowmanner/.env` | Backend env vars |
| WireGuard config | `/etc/wireguard/wg0.conf` | |
| Deploy scripts | `/opt/flowmanner/deploy-*.sh` | Frontend, backend, all |
| Helper scripts | `/opt/flowmanner/scripts/` | Pre-flight, post-deploy, health check, etc. |
| Better-exceptions log | `/tmp/better-exceptions.log` | Detailed error traces (when enabled) |

## Services

| Service | Container | IP/Port | Notes |
|---------|-----------|---------|-------|
| Backend (FastAPI) | `backend` | 10.0.4.6:8000 | Image: `workflows-backend:restored` |
| PostgreSQL | `workflow-postgres` | 10.0.4.2:5432 | Data in `postgres_data` volume |
| Redis | `workflow-redis` | 10.0.4.5:6379 | Data in `redis_data` volume |
| Qdrant | `workflow-qdrant` | 10.0.4.3:6333 | Data in `qdrant_data` volume |
| RabbitMQ | `workflow-rabbitmq` | 10.0.4.9:5672 | Data in `rabbitmq_data` volume |
| Celery Worker | `celery-worker` | — | 4 concurrency, 100 max-tasks-per-child |
| Celery Beat | `celery-beat` | — | Periodic task scheduler |
| Jaeger | `jaeger` | 10.0.4.7:16686 | Distributed tracing |
| Static files | `workflows-static` | 10.0.4.8:80 | nginx serving /opt/flowmanner/static/ |
| llama.cpp | bare metal (systemd) | 0.0.0.0:11434 | NOT in Docker |

## ⚠️ Backend Container Rules (READ THIS)

**The backend container has NO volume mounts.** All code is baked into the Docker image via `COPY . /app/` in the Dockerfile.

```
WHAT THIS MEANS:
- Files copied into a running container (`docker cp`) are LOST on rebuild
- To make changes permanent, edit files in /opt/flowmanner/backend/ THEN rebuild
- The ONLY way to update the running backend is: rebuild the image + restart the container
- Database data (PostgreSQL, Redis, Qdrant, RabbitMQ) IS persistent via named volumes
```

**To make ANY code change to the backend:**
1. Edit the source file in `/opt/flowmanner/backend/`
2. Deploy with health checks + auto-rollback:
   `bash /opt/flowmanner/deploy-backend.sh`
   Optional: `--migrate` (run alembic first), `--dry-run`, `--rollback`
   ⚠️ **Takes ~2 minutes.** Use `timeout=300`.
   ⚠️ **Always use `deploy-backend.sh` instead of raw `docker build` + `docker compose` commands.** The script handles: pre-deploy health check → image backup → build → restart → post-deploy health check → auto-rollback on failure.
3. Verify: `curl http://127.0.0.1:8000/api/health`

**NEVER** `docker cp` into the backend container unless it's a temporary debug action that you expect to lose.

> **Why not `docker compose build backend`?** The compose file uses `image:` not `build:`, so `docker compose build` is a no-op. See [REBUILD-BACKEND.md](./REBUILD-BACKEND.md) for details.

## Development Workflow

Three commands installed at `~/.local/bin/`:

| Command | What it does |
|---------|-------------|
| `dev` | Start the Next.js dev server (systemd user service, auto-starts on boot) |
| `wip` | Silent local save-point. No push, no deploy. |
| `ship` | **Only way to reach production** — auto-commits dirty files, pushes origin, then runs `deploy-frontend.sh`. |

**Dev server:** `http://172.16.1.1:3000` — HMR on save. Logs: `journalctl --user -u flowmanner-dev -f`.

⛔ **Never run Docker commands on the VPS directly.** Always use `ship`.

## Frontend Deployment to VPS

The frontend source lives locally at `/home/glenn/FlowmannerV2-frontend/`. It has no git remote.

**Canonical deploy command:** `ship` (auto-commits + pushes + calls the deploy script).

Or directly (fallback): `bash /opt/flowmanner/deploy-frontend.sh`

⚠️ **TIMING: The full deploy pipeline takes ~4 minutes.** Breakdown:
- rsync: ~30 seconds
- docker compose build frontend (VPS): ~2 minutes
- docker compose up + nginx restart: ~30 seconds
- Health checks (10 retries × 5s delay): ~50 seconds

**When invoking from an AI agent: use `timeout=300` or `background=true, notify_on_complete=true`.**
**NEVER retry a timed-out deploy without first checking if it completed** — the containers may already be updated. Check: `ssh -i ~/.ssh/vps_flowmanner_new root@74.208.115.142 "cd /opt/flowmanner && docker compose ps"` to see container uptime.

```bash
# Use the deploy script (preferred — includes health checks + auto-rollback)
# ⚠️ This command takes ~4 minutes. Use timeout=300 or background=true.
bash /opt/flowmanner/deploy-frontend.sh

# Or dry-run to preview:
bash /opt/flowmanner/deploy-frontend.sh --dry-run

# Rollback to previous version:
bash /opt/flowmanner/deploy-frontend.sh --rollback

# Or manually (NOT recommended — use the script):
rsync -avz --progress \
  -e "ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new" \
  --exclude node_modules --exclude .next --exclude .git --exclude .env.local \
  /home/glenn/FlowmannerV2-frontend/ \
  root@74.208.115.142:/opt/flowmanner/frontend/

ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "cd /opt/flowmanner && docker compose build frontend && docker compose up -d --no-deps frontend && docker compose restart nginx"
```

## Database Migrations (Alembic)

```bash
# Run migration inside the backend container
cd /opt/flowmanner
docker compose exec backend alembic upgrade head

# Check current migration state
docker compose exec backend alembic current

# Create a new migration (after model changes)
docker compose exec backend alembic revision --autogenerate -m "description"
```

**Migrations run against the persistent PostgreSQL volume** — they survive rebuilds. The migration scripts live in `/opt/flowmanner/backend/alembic/`.

## Backend API Structure

The backend is FastAPI with the following router structure:
- `/api/v1/` — 60+ endpoint modules covering auth, chat, missions, agents, files, workspace, etc.
- `/api/v2/` — Next-gen API version
- `/ws` — WebSocket for real-time events
- `/docs` / `/redoc` — Auto-generated API documentation
- `/health` — Health check endpoint

Key modules: chat, agent, mission, auth, file, graph, swarm, templates, workflows, webhooks, integrations, llm, search, memory, evaluation

## llama.cpp Server

OpenAI-compatible LLM server. Runs on bare metal via systemd (NOT Docker).

### Paths

| What | Path |
|------|------|
| Active binary | `/mnt/apps/llama.cpp-mtp/build/bin/llama-server` |
| Source code | `/mnt/apps/llama.cpp-mtp/` |
| Active model (Q5) | `/mnt/apps/models/mtp/Qwen3.6-27B-Q5_K_M-mtp.gguf` (19.7GB) |
| Alt model (Q4) | `/mnt/apps/models/mtp/Qwen3.6-27B-Q4_K_M-mtp.gguf` (17GB) |
| Old model (no MTP) | `/mnt/apps/models/Qwen_Qwen3.6-27B-Q4_K_M.gguf` (17GB) |
| Service file | `/etc/systemd/system/llama-server.service` |
| Service backup | `/etc/systemd/system/llama-server.service.bak` |
| Logs | `/var/log/llama-server.log` |

### Hardware

2x RTX 5060 Ti (16GB each, ~32GB total VRAM), CUDA 13.2, Blackwell (SM 12.0).

### Config

`--spec-type draft-mtp --spec-draft-n-max 3 --ctx-size 32768 --gpu-layers 99 --flash-attn on --parallel 1 --cont-batching`

Performance: ~38 tok/s (Q5_MTP), ~44 tok/s (Q4_MTP), ~21 tok/s baseline (no MTP).

Backend access: `http://10.0.4.1:11434` (Docker gateway), OpenAI API at `/v1/chat/completions`.

### Commands (run as `glenn`)

```bash
systemctl status llama-server          # Status
sudo systemctl restart llama-server    # Restart
tail -50 /var/log/llama-server.log     # Logs
curl http://localhost:11434/health     # Health
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader  # VRAM
```

### Rebuild from Source

```bash
cd /mnt/apps/llama.cpp-mtp/build
PATH=/usr/local/cuda/bin:$PATH CUDACXX=/usr/local/cuda/bin/nvcc CUDAHOSTCXX=/usr/bin/g++-14 \
  cmake --build . -j$(nproc)
sudo systemctl restart llama-server
```

### Rollback (no MTP)

```bash
sudo cp /etc/systemd/system/llama-server.service.bak /etc/systemd/system/llama-server.service
sudo systemctl daemon-reload
sudo systemctl restart llama-server
```

---

## 🧠 CodeGraph MCP — Code Intelligence

**CodeGraph is the primary code-understanding tool for the Flowmanner frontend.** It indexes the codebase with tree-sitter, builds a dependency graph, and serves structured context via MCP. Use it BEFORE reading files manually.

### What it does

- Parses every TypeScript/TSX file with tree-sitter
- Extracts functions, classes, imports, exports, types
- Builds a dependency graph (nodes = symbols, edges = imports/uses)
- Stores in SQLite with FTS5 full-text search
- Serves via MCP protocol to AI agents
- **96% token reduction** vs. reading raw files

### Setup (one-time)

```bash
# Install
npm install -g codegraph-ai

# Index the project (re-run when files change)
cd /home/glenn/FlowmannerV2-frontend
npx codegraph-ai index .
```

The index database lives at `/home/glenn/FlowmannerV2-frontend/.codegraph/codegraph.db`. It's already been indexed (6.5MB).

### MCP Tools Available

| Tool | Description | Usage |
|------|-------------|-------|
| `search` | Full-text search for symbols (functions, classes, types) | Find where something is defined |
| `get_context` | Get a symbol with its dependencies and dependents | Understand relationships |
| `get_file_deps` | Get all imports and exports for a file | Map module dependencies |
| `project_overview` | High-level stats: hub nodes, entry points, connections | Understand project structure |

### HOW TO USE (mandatory workflow)

When you need to understand code:

1. **FIRST** use CodeGraph (`project_overview` or `search`) to find what you need
2. **THEN** use `get_context` on relevant symbols to understand relationships
3. **ONLY THEN** read the actual file if you still need the full source

**DO NOT** just start reading files blindly. Use CodeGraph to narrow down what's relevant.

### MCP Config for Agent Clients

Add to your MCP config (Claude Code, Cursor, Windsurf, etc.):

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "npx",
      "args": ["codegraph-ai", "serve", "/home/glenn/FlowmannerV2-frontend"]
    }
  }
}
```

### Token Savings Benchmark

Tested on a production Next.js project (82 files, 384 symbols):

| Scenario | Without | With CodeGraph | Reduction |
|----------|---------|----------------|-----------|
| Understand symbol + relationships | 19,220 tk | 637 tk | 97% |
| Understand high-usage symbol (40 deps) | 40,742 tk | 1,736 tk | 96% |
| Search for a term | 4,716 tk | 475 tk | 90% |
| Understand project structure | 15,145 tk | 1,047 tk | 93% |
| **Total (8 operations)** | **126,488 tk** | **5,558 tk** | **96%** |

---

## Frontend Test Infrastructure

### Unit / Component Tests (Vitest)
```bash
cd /home/glenn/FlowmannerV2-frontend
npm test                    # Run all unit tests
npm test -- --coverage      # With coverage
```

Tests are in `src/**/*.test.{ts,tsx}`. Config: jsdom environment, path alias `@/` → `./src/`.

### E2E Tests (Playwright)
```bash
cd /home/glenn/FlowmannerV2-frontend
npx playwright test         # Run all E2E tests
npx playwright test --ui    # Interactive UI mode
```

Tests are in `e2e/`. Runs against local dev server (localhost:3000).

## Credentials

| Service | Username | Password |
|---------|----------|----------|
| PostgreSQL | flowmanner | FlowDB2026! |

## Troubleshooting

| Problem | Check |
|---------|-------|
| Backend down | `docker ps \| grep backend`, `curl http://127.0.0.1:8000/api/health` |
| VPS can't reach backend | `sudo wg show`, check from VPS: `curl http://10.99.0.3:8000/api/health` |
| Code changes not taking effect | You must rebuild the image (backend has no volume mounts) |
| Migration needed | `docker compose exec backend alembic upgrade head` |
| LLM not responding | `systemctl status llama-server`, `curl http://localhost:11434/health` |
| VRAM issues | `nvidia-smi` |
| Frontend deploy timed out | Do NOT retry. First check: `ssh -i ~/.ssh/vps_flowmanner_new root@74.208.115.142 "cd /opt/flowmanner && docker compose ps"` and compare image dates. The deploy may have succeeded but the agent just didn't wait long enough (~4 min). |
| Frontend deploy failed | Check `/opt/flowmanner/deploy-frontend.sh` output — auto-rollback runs on failure |
| CodeGraph index stale | `cd /home/glenn/FlowmannerV2-frontend && npx codegraph-ai index .` |
| Deploy guard rejects untracked session files | Per-session exit audits at `.sisyphus/exit-audit-*.md` are gitignored — leave them untracked, they will not trip the deploy guard |
