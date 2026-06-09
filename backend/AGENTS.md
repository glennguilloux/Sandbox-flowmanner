# Flowmanner — Backend Agent Instructions

## ⚠️ YOU ARE WORKING ON THE BACKEND

This file lives at `/opt/flowmanner/backend/` on the **homelab** (172.16.1.1 / 10.99.0.3).

You are working on a **FastAPI Python backend** that powers the Flowmanner platform.

## Backend Identity

- **Framework:** FastAPI 0.115 + Uvicorn 0.34
- **Python:** 3.11 (slim-bookworm Docker image)
- **ORM:** SQLAlchemy 2.0 (async) + Alembic 1.13
- **Task Queue:** Celery 5.3 + RabbitMQ
- **Cache:** Redis 4.5
- **Vector DB:** Qdrant 1.12
- **LLM:** LangChain 0.1 + OpenAI 1.68
- **Tracing:** OpenTelemetry → Jaeger
- **Validation:** Pydantic 2.10
- **Auth:** PyJWT 2.8 + passlib + pyotp (2FA)
- **Logging:** structlog
- **Metrics:** prometheus-client

## ⚠️ CRITICAL: No Volume Mounts

**The backend Docker container has NO volume mounts.** All code is baked into the image.

```
TO MAKE CODE CHANGES:
1. Edit files in /opt/flowmanner/backend/
2. Rebuild: docker build -t workflows-backend:restored /opt/flowmanner/backend/
   ⚠️ Build takes ~2 minutes. Use timeout=300.
3. Restart: docker compose up -d --no-deps --force-recreate backend

NEVER: docker cp into the container (changes are lost on rebuild)
```

## Source Structure

```
backend/
├── Dockerfile              # Multi-stage build (builder + runtime)
├── Dockerfile.dev          # Dev Dockerfile with volume mounts
├── requirements.txt        # Python dependencies
├── alembic.ini             # Database migration config
├── alembic/                # Migration scripts
├── mcp_gateway/            # MCP gateway configuration
│   └── client_config.json  # MCP server definitions
├── app/
│   ├── main_fastapi.py     # FastAPI app entry point
│   ├── api/                # API layer
│   │   ├── v1/             # 60+ endpoint modules
│   │   ├── v2/             # Next-gen API
│   │   ├── deps.py         # FastAPI dependencies
│   │   └── middleware/     # Audit, metrics, rate limit, security, versioning
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic request/response schemas
│   ├── routers/            # Route handlers
│   ├── services/           # Business logic layer
│   ├── core/               # Config, security, database connections
│   ├── dependencies/       # DI container
│   ├── middleware/          # FastAPI middleware
│   ├── tasks/              # Celery tasks
│   │   └── celery_app.py   # Celery app definition
│   ├── workers/            # Background workers
│   ├── websocket/          # WebSocket handlers
│   ├── tools/              # Tool implementations
│   ├── integrations/       # External service integrations
│   ├── agent_definitions/  # Agent configuration
│   ├── governance/         # Governance/approval workflows
│   ├── cache/              # Caching layer
│   ├── utils/              # Utility functions
│   ├── cli/                # CLI commands
│   ├── sdk/                # SDK generation
│   ├── tests/              # Unit/integration tests
│   └── scripts/            # Utility scripts
```

## API Structure

The backend exposes 60+ endpoint modules under `/api/v1/`:

| Category | Modules |
|----------|---------|
| Auth | auth, api_keys, oidc, two_fa |
| Core | chat, agent, mission, graph, files |
| Workspace | workspace, tenant, users, roles |
| Advanced | swarm, templates, triggers, webhooks |
| Intelligence | llm, llm_advanced, search, rag, memory |
| Operations | dashboard, analytics, usage, stats, observability |
| Platform | marketplace, community, changelog, roadmap |
| Integration | integrations, linear, browser, byok |
| Quality | evaluation, feedback, reliability |
| Admin | admin, audit_log, rate_limits, feature_flags |

## Database

PostgreSQL 15 with async SQLAlchemy. Migrations via Alembic.

```bash
# Check migration status
docker compose exec backend alembic current

# Apply pending migrations
docker compose exec backend alembic upgrade head

# Create new migration after model changes
docker compose exec backend alembic revision --autogenerate -m "description"
```

## Docker Commands

```bash
cd /opt/flowmanner

# Health check
curl http://127.0.0.1:8000/api/health

# Rebuild backend image (MANDATORY after code changes)
# ⚠️ Takes ~2 minutes. Use timeout=300.
docker build -t workflows-backend:restored /opt/flowmanner/backend/

# Restart backend
docker compose up -d --no-deps --force-recreate backend

# Restart celery workers too (if tasks changed)
docker compose up -d --no-deps --force-recreate celery-worker celery-beat

# View logs
docker compose logs backend --tail 50
docker compose logs celery-worker --tail 50

# Shell into container
docker compose exec backend bash

# Run tests inside container
docker compose exec backend pytest app/tests/ -v
```

## MCP Gateway

The backend includes an MCP gateway at `/opt/flowmanner/backend/mcp_gateway/client_config.json`. Currently configured with:
- `codegraph-ai` — CodeGraph code intelligence (frontend TS/TSX indexing)
- `@modelcontextprotocol/server-filesystem` — filesystem operations
- `@modelcontextprotocol/server-github` — GitHub API (needs token)

Add more MCP servers by editing `client_config.json`.

## Testing

```bash
# Run specific test file
docker compose exec backend pytest app/tests/test_auth_api.py -v

# Run all tests
docker compose exec backend pytest app/tests/ -v

# With coverage
docker compose exec backend pytest app/tests/ -v --cov=app --cov-report=term
```

## Deploy Process

⚠️ **TIMING: Backend rebuild takes ~2 minutes.** Use `timeout=300` or `background=true, notify_on_complete=true`.

```
Edit source in /opt/flowmanner/backend/
    ↓
docker build -t workflows-backend:restored /opt/flowmanner/backend/    (~2 min)
    ↓
docker compose up -d --no-deps --force-recreate backend                 (fast)
    ↓
docker compose exec backend alembic upgrade head  (if schema changed)   (fast)
    ↓
curl http://127.0.0.1:8000/api/health  (verify)                         (instant)
```

## What NOT to Do

- Do NOT edit backend files on VPS — they don't exist there
- Do NOT run `docker compose build backend` — compose uses `image:`, not `build:`
- Do NOT use `docker cp` for permanent changes — they're lost on rebuild
- Do NOT commit `.env` files — they contain secrets
- Do NOT run Alembic without checking current migration state first
- Do NOT forget to restart celery workers if you changed tasks

## Middleware registration order

**Rule:** When registering a custom middleware class via `app.add_middleware(MyClass)`, the class must be **defined earlier in the file** than the `add_middleware` call. Python's `add_middleware` defers class resolution, so a forward reference produces a **silent** failure mode:

- The module imports without error.
- Uvicorn reports `Application startup complete`.
- `/api/health` returns non-2xx on every attempt.
- No Python traceback is written to stdout/stderr.
- `deploy-backend.sh` auto-rolls back to the previous image.

**Diagnosis shortcut:** if a deploy fails 15/15 health checks with no traceback, the first thing to check is whether a newly registered middleware class is defined below its `add_middleware` call.

**Fix:** move the class definition above the `add_middleware` call. Re-deploy; the issue resolves immediately.

**Exception:** inside a function (closure), class lookups are resolved at call time via LEGB — order does not matter.

## Recent changes (bisect record)

**`feat: GraphQL deprecation middleware` (5-step bisect, completed clean).** Adds four structured fields to every request's structlog context and registers a pure ASGI middleware that advertises RFC 8594 `Deprecation` / `Sunset` / `Link` headers on the legacy `/api/v2/graphql` endpoint (sunset 2026-07-09). The middleware class is defined above the `app.add_middleware` call in `main_fastapi.py` per the rule above.
