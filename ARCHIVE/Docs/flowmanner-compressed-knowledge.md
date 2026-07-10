# Flowmanner — Compressed Knowledge Representation

## Executive Summary

Flowmanner is a **two-machine AI workflow platform** (VPS frontend + Homelab backend) connected via WireGuard. Next.js 16 frontend serves flowmanner.com through Nginx on IONOS VPS. FastAPI backend on homelab runs PostgreSQL, Redis, Qdrant, RabbitMQ, Celery, Jaeger, and llama.cpp (Qwen 27B). A third ops/dev machine triggers deploys. **Iron rule: never edit on VPS — all source edits on homelab, then deploy.**

## Core Principles

1. **Edit homelab, deploy to VPS.** VPS receives rsync'd frontend. Backend lives exclusively on homelab.
2. **No volume mounts on backend.** Docker images are immutable — every code change requires `docker build` + restart.
3. **Deploys take minutes, not seconds.** Frontend ~4min, backend ~2min. Use `timeout=300`. Never retry timed-out deploys without verifying completion.
4. **CodeGraph first, files later.** 96% token reduction. Search → get_context → only then read files.
5. **Two auth systems must agree.** NextAuth JWT cookie + Zustand `fm_tokens` localStorage key.
6. **Source ≠ runtime.** Docker containers have no live source mounts. Editing files doesn't change running behavior.
7. **Deploy scripts have auto-rollback.** Failed deploys revert to previous image automatically.

## Dimensions

| Dimension | Specification |
|-----------|--------------|
| **Scale** | 2 physical machines, 3 agent roles, ~15 Docker services, 60+ API endpoints |
| **Traffic flow** | Internet → Nginx:443 → Next.js:3000 or WireGuard → FastAPI:8000 |
| **Data persistence** | 5 named Docker volumes (PG, Redis, Qdrant, RabbitMQ, uploads) survive rebuilds |
| **Code size** | Frontend: 80+ files, 384+ symbols. Backend: ~60 endpoint modules, full FastAPI app |
| **LLM throughput** | Qwen 27B @ ~38 tok/s (Q5_MTP), ~44 tok/s (Q4_MTP) on 2× RTX 5060 Ti (32GB VRAM) |
| **Auth surface** | GitHub OAuth + credentials, NextAuth v5, JWT + localStorage bridge |
| **Observability** | OpenTelemetry → Jaeger, Sentry (frontend), structlog (backend), prometheus metrics |

## Components

### Machines
| Machine | Public IP | LAN IP | Role | Key file |
|---------|-----------|--------|------|----------|
| VPS (IONOS) | 74.208.115.142 | 10.99.0.1 (WG) | Nginx SSL, Next.js, frontend Docker | `~/.ssh/vps_flowmanner_new` |
| Homelab | 176.141.9.146 | 172.16.1.1 / 10.99.0.3 | FastAPI, all data stores, LLM, all source code | local |
| Ops/Dev | — | 172.16.1.2 | Deploy trigger, dev workstation | `glenn@172.16.1.1` |

### Services (Homelab Docker)
| Container | IP (:port) | Image | Memory | Persistence |
|-----------|------------|-------|--------|-------------|
| `backend` (FastAPI) | 10.0.4.6:8000 | `workflows-backend:restored` | 4GB | uploads volume only |
| `workflow-postgres` | 10.0.4.2:5432 | postgres:15-alpine | 2GB | `postgres_data` |
| `workflow-redis` | 10.0.4.5:6379 | redis:7-alpine | 512MB | `redis_data` |
| `workflow-qdrant` | 10.0.4.3:6333 | qdrant:v1.12.0 | 1GB | `qdrant_data` |
| `workflow-rabbitmq` | 10.0.4.9:5672 | rabbitmq:3-management | 512MB | `rabbitmq_data` |
| `celery-worker` | — | same as backend | 2GB | — |
| `celery-beat` | — | same as backend | 512MB | — |
| `jaeger` | 10.0.4.7:16686 | jaegertracing/all-in-one | — | — |
| `workflows-static` | 10.0.4.8:80 | nginx-unprivileged | 128MB | `./static` (ro) |
| `searxng` | 10.0.4.11:8080 | searxng/searxng | — | tmpfs |

### Bare Metal (Homelab)
- **llama.cpp**: systemd service, `0.0.0.0:11434`, Qwen3.6-27B, 2× RTX 5060 Ti (32GB VRAM), CUDA 13.2

### Services (VPS Docker)
| Container | Role |
|-----------|------|
| `flowmanner-nginx` | SSL termination, reverse proxy (:80/:443) |
| `flowmanner-frontend` | Next.js 16 (:3000 internal) |
| `wg0` | WireGuard tunnel to homelab |

### Nginx Routing (VPS)
```
/api/auth/*  → frontend:3000  (NextAuth — BEFORE /api/ catch-all)
/api/*       → 10.99.0.3:8000 (homelab backend)
/docs,/redoc → 10.99.0.3:8000
/ws          → ws://10.99.0.3:8000
/*           → frontend:3000  (Next.js)
```

### Frontend Stack
Next.js 16.2.6 (App Router, TypeScript strict), Tailwind 3.4, Radix UI, Zustand 5, TanStack Query 5, SWR 2, NextAuth v5, next-intl 4, @xyflow/react 12, socket.io-client 4, Sentry 10. Testing: Vitest 4 + Playwright 1.60.

### Backend Stack
FastAPI 0.115, Python 3.11, SQLAlchemy 2.0 (async), Alembic 1.13, Celery 5.3, Pydantic 2.10, LangChain 0.1, OpenAI 1.68, OpenTelemetry → Jaeger, structlog, PyJWT 2.8.

### API Modules (60+)
Auth (auth, api_keys, oidc, 2FA), Core (chat, agent, mission, graph, files), Workspace (tenant, users, roles), Advanced (swarm, templates, triggers, webhooks), Intelligence (llm, search, rag, memory), Ops (dashboard, analytics, usage, stats), Platform (marketplace, community), Integration (linear, browser, byok), Quality (evaluation, feedback), Admin (audit, rate_limits, feature_flags).

### Key Paths
| What | Path |
|------|------|
| Homelab project root | `/opt/flowmanner/` |
| Backend source | `/opt/flowmanner/backend/` |
| Frontend source | `/home/glenn/FlowmannerV2-frontend/` |
| VPS frontend (rsync target) | `/opt/flowmanner/frontend/` |
| Docker Compose (homelab) | `/opt/flowmanner/docker-compose.yml` |
| Environment | `/opt/flowmanner/.env` |
| SSL certs (VPS) | `/opt/flowmanner/certs/` (expires Aug 15, 2026) |
| Nginx config (VPS) | `/opt/flowmanner/nginx/default.conf` |
| llama.cpp model | `/mnt/apps/models/mtp/Qwen3.6-27B-Q5_K_M-mtp.gguf` (19.7GB) |
| CodeGraph index (frontend) | `/home/glenn/FlowmannerV2-frontend/.codegraph/codegraph.db` (6.5MB) |

### Deploy Commands
```bash
# Frontend (from homelab, ~4 min)
bash /opt/flowmanner/deploy-frontend.sh

# Backend (from homelab, ~2 min)
docker build -t workflows-backend:restored /opt/flowmanner/backend/
docker compose up -d --no-deps --force-recreate backend

# Migrations
docker compose exec backend alembic upgrade head
```

## Relationships

```
Ops Machine ──SSH──→ Homelab ──rsync+SSH──→ VPS
                         │                      │
                    [edits source]        [receives rsync]
                    [builds backend]      [builds frontend]
                    [runs all DBs]        [serves public traffic]
                         │                      │
                    WireGuard tunnel ───────────┘
                    (10.99.0.3 ←→ 10.99.0.1)
```

- **Homelab → VPS**: rsync frontend source, trigger `docker compose build frontend`
- **VPS → Homelab**: Nginx proxies `/api/*`, `/ws` through WireGuard tunnel
- **Ops → Homelab**: SSH to edit source, trigger deploys via `deploy-frontend-remote.sh`
- **Frontend auth bridge**: NextAuth cookie ←→ Zustand `fm_tokens` must sync via `initialize()` from `/api/auth/session`
- **Backend rebuild chain**: Edit → `docker build` → `docker compose up -d --no-deps --force-recreate` → (optional) `alembic upgrade head`
- **Frontend deploy chain**: Edit → `npm test` → `npm run build` → `rsync` → VPS `docker compose build` → restart → health checks → auto-rollback on fail

### Auth System (Critical)
```
SignIn (client component, next-auth/react) → JWT cookie set
  ↓
window.location.href = "/dashboard" (hard nav, NOT router.push)
  ↓
AuthProvider remounts → initialize() → GET /api/auth/session
  ↓
fm_tokens localStorage populated → Zustand isAuthenticated=true
```

**Fragile points:**
- Server Action `signIn()` from `@/auth` silently fails (JWT never set)
- `router.push()` doesn't remount AuthProvider (Zustand stays unauthenticated)
- Expired `fm_tokens` causes `refreshUser()` 401 → state cleared without session fallback
- `$` in template literals must not become `\$` in auth.ts

## Open Questions

1. **Git remote for frontend?** AGENTS.md says "no git remote" — is version control only local on homelab?
2. **Backup strategy?** Makefile has `db-backup` but no automated schedule. Are backups running?
3. **Staging environment?** `docker-compose.staging.yml` and `.env.staging` exist — is staging active?
4. **Monitoring/alerting?** Jaeger + Sentry + prometheus metrics present, but are alerts configured (PagerDuty, Slack)?
5. **Horizontal scaling?** Single backend container. Is there a plan for multi-replica behind load balancer?
6. **Secrets rotation?** `SECRETS-ROTATION.md` exists — how often are secrets rotated and is it automated?
7. **Disaster recovery?** VPS homelab dependency — if homelab is down, entire API is down. DR plan?
8. **CI/CD?** No mention of GitHub Actions or CI pipeline. Is all deployment manual via Makefile/scripts?
9. **Frontend E2E in CI?** Playwright tests exist but run against localhost:3000 — are they run pre-deploy?
10. **CodeGraph for backend?** Only frontend is indexed (`.codegraph/` in frontend dir). Backend has `.codegraph/` dir too — is it active?
