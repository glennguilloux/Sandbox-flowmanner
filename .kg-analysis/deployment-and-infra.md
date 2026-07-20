# Flowmanner — Deployment & Infrastructure-as-Code Analysis

> READ-ONLY KG analysis. No source was committed, pushed, or edited. Every claim is
> anchored to a file:line in `/opt/flowmanner`. Generated for knowledge-graph ingestion.

## 0. Scope & Method
- Source of truth inspected: `/opt/flowmanner` repo root (branch `agent/20260720-kg/infra`).
- Compose file of record: `docker-compose.yml` (root). `AGENTS.homelab.md:43` confirms this is THE compose.
- **Frontend source is NOT in this repo.** Per `AGENTS.md` / `AGENTS.homelab.md:42`, frontend
  source lives at `/home/glenn/FlowmapperV2-frontend` (double-N `Flowmanner`) — a separate,
  git-remote-less checkout rsync'd to the VPS by `deploy-frontend.sh`. No `frontend/Dockerfile`
  exists in `/opt/flowmanner` (search returned 0 hits). The only `frontend` build context in-repo
  is `docker-compose.staging.yml:114` (staging-only, builds `./frontend` which is absent at homelab root).
- **No VPS-side compose / nginx config is committed here.** `deploy-frontend.sh:148` references
  `/opt/flowmanner/nginx/default.conf` but that file is not present in the repo (search returned 0 hits).
  The VPS nginx + frontend image are built/persisted on the VPS itself.

---

## SERVICES INVENTORY
Enumeration from `docker-compose.yml` (root, the production homelab stack) + `docker-compose.dev.yml`
(dev override) + `docker-compose.staging.yml` (staging).

| service | image | port(s) (host:container) | depends_on | purpose / notes |
|---|---|---|---|---|
| `searxng` | `searxng/searxng:latest` | 55510:8080 | — | Self-hosted web search (json fmt patch at boot). `docker-compose.yml:7-48` |
| `postgres` | `postgres:15-alpine` | 5432:5432 | — | Primary RDBMS. Data: external vol `glenn_postgres_data`. `docker-compose.yml:50-73` |
| `qdrant` | `qdrant/qdrant:v1.12.0` | 6333:6333, 6334:6334 | — | Vector store. Data: external vol `glenn_qdrant_data`. `docker-compose.yml:75-108`. **Hardened ulimits (nofile 65536)** after reboot-loop incident — see KEY FINDINGS F4. |
| `redis` | `redis:7-alpine` | 6379:6379 | — | Cache + Celery result backend. AUTH via `REDIS_PASSWORD` (`requirepass`). Append-only. `docker-compose.yml:110-133` |
| `rabbitmq` | `rabbitmq:3-management-alpine` | 127.0.0.1:5672:5672, 127.0.0.1:15672:15672 | — | Celery broker. Bound to localhost only. `docker-compose.yml:135-158` |
| `celery-worker` | `${BACKEND_IMAGE:-workflows-backend:restored}` | (none published) | rabbitmq, postgres, redis (healthy) | Runs `app.tasks.celery_app`. `--concurrency=4 --max-tasks-per-child=100`. `docker-compose.yml:160-188` |
| `celery-beat` | `${BACKEND_IMAGE:-workflows-backend:restored}` | (none published) | rabbitmq, postgres, redis (healthy) | Periodic scheduler. `docker-compose.yml:190-218` |
| `backend` | `${BACKEND_IMAGE:-workflows-backend:restored}` | 8000:8000 | postgres, redis, qdrant (healthy) | FastAPI (uvicorn, 1 worker). Healthcheck `/health`. `docker-compose.yml:220-263`. Mounts: `uploads_data` + **read-only host Hermes `state.db`** at `/mnt/hermes-state/state.db:ro` (`docker-compose.yml:241-246`). |
| `dev-postgres` / `dev-redis` / `dev-qdrant` / `dev-rabbitmq` / `dev-celery-worker` / `dev-backend` | same upstream images | 5432/6379/6333/5672/8000 | as above | Self-contained dev stack in `dev/docker-compose.dev.yml` (own bridge net `flowmanner_dev`, own volumes). Backend built from `backend/Dockerfile.dev` with source volume-mounted. `dev/docker-compose.dev.yml:34-207` |
| `*-staging` (postgres-staging, qdrant-staging, redis-staging, backend-staging, frontend-staging) | as above + `frontend` build | 15432/16333/16379/18000/13000 | as above | `docker-compose.staging.yml:11-142`. Frontend built from `./frontend` (not present at homelab root — staging build context requires the source there). |

**Homelab services cited in `AGENTS.homelab.md` but NOT present in committed `docker-compose.yml`:**
- `jaeger` (`:16686`) — listed at `AGENTS.homelab.md:61`, but the OTEL `OTLP_ENDPOINT` is
  **commented out / disabled** in compose (`docker-compose.yml:232`, `docker-compose.dev.yml:49`):
  `# DISABLED 2026-07-03 — Glenn not using Jaeger`. Tracing is therefore inactive in practice.
- `workflows-static` (nginx, `:80`) — listed at `AGENTS.homelab.md:62` but absent from committed compose.
- These two are documentation drift; the running stack is the 8 services above + searxng.

---

## BUILD PIPELINE

### Backend image — `backend/Dockerfile` (HARDENED MULTI-STAGE)
- **Stage 1 `builder`** (`backend/Dockerfile:6`): `python:3.11.11-slim-bookworm`. Installs gcc +
  Playwright system deps, creates `/opt/venv`, `pip install -r requirements.txt`, then
  `playwright install chromium` (browsers cached to `/ms-playwright`).
- **Stage 2 `runtime`** (`backend/Dockerfile:43`): same base (no gcc/dev headers). Installs runtime
  libs incl. `chromium`, `ffmpeg`, `tesseract-ocr`. Creates **non-root user `flowmanner` (uid 1000)**
  (`backend/Dockerfile:65-66`); entrypoint drops to it (`backend/Dockerfile:116`, `docker-entrypoint.py:23`).
- **Baked-in code** (`backend/Dockerfile:77-92`): `app/`, `alembic/`, `alembic.ini`, `pyproject.toml`,
  `mcp_gateway/`, `agent_definitions/`, `scripts/`, `integrations/`, `schemas/`, `tests/`,
  `seed_templates.py`, `LICENSE`. **No volume mounts at runtime** (see constraint below).
- **Entrypoint** (`backend/Dockerfile:107-110`): `/docker-entrypoint.py` → ensures `/app/uploads` writable,
  drops to `flowmanner`, runs best-effort boot hooks (reload builtin templates, seed marketplace, seed
  changelog — all swallow failures so startup is never blocked), then `exec`s the CMD.
- **CMD** (`backend/Dockerfile:123`): `uvicorn app.main_fastapi:app --host 0.0.0.0 --port 8000 --workers 1`.
- **HEALTHCHECK** (`backend/Dockerfile:120-121`): `curl -f http://localhost:8000/health`.
- **EXPOSE 8000** (`backend/Dockerfile:118`).

### `backend/Dockerfile.dev` (DEV ONLY, single-stage)
- `python:3.11.11-slim-bookworm`; installs only `curl git libpq5 postgresql-client`.
- **No app code baked** — relies on volume mounts (`app/`, `alembic/`, `alembic.ini`) at runtime
  (`backend/Dockerfile.dev:32-45`). Used by `docker-compose.dev.yml` for hot-reload.

### `backend/app/Dockerfile` (LEGACY / UNUSED by prod)
- Single-stage `python:3.11-slim`, `--workers 4`, no Playwright/tesseract. Superseded by the
  hardened root `backend/Dockerfile` (the root `Dockerfile.dev` is the one referenced by dev compose).

### `sandboxd/` Dockerfiles
- `sandboxd/Dockerfile.sandboxd-base`, `sandboxd/Dockerfile.browser` — separate build targets for the
  sandbox execution subsystem (referenced by `app/integrations/sandboxd_client.py`), not part of the
  main backend/celery image.

### NO-VOLUME-MOUNTS CONSTRAINT (critical)
- The production backend image is **fully baked**; the running container has **no code volume mounts**
  (`AGENTS.homelab.md:65-88`). Implication: `docker compose build backend` is a **no-op** because
  compose uses `image:` not `build:` (`docker-compose.yml:221`). The ONLY supported update path is
  `deploy-backend.sh`, which runs `docker build --target runtime` directly (`deploy-backend.sh:557`)
  and force-recreates the 3 image-pinned containers together. `docker cp` edits are lost on rebuild.

### Frontend build
- **Not in repo.** Built on the VPS from `/home/glenn/FlowmannerV2-frontend` (Next.js) via
  `deploy-frontend.sh`. The VPS `docker compose build frontend` + `docker compose restart nginx`
  (`deploy-frontend.sh:140-153`) builds the image there; no image-tag rollback flow exists
  (`--rollback` is a documented no-op, `deploy-frontend.sh:118-125`).

### Deploy script steps
**`deploy-backend.sh`** (homelab → rebuilds `workflows-backend:restored`, ~2 min):
1. Pre-deploy gate: `scripts/pre-deploy-check.sh` (`PRECHECK_SCOPE=backend`) unless `--skip-precheck`
   (`deploy-backend.sh:641-655`).
2. `pre_deploy_health` baseline check (`deploy-backend.sh:316-324`).
3. `save_current_image` → tags timestamped backup + `workflows-backend:backup-current`
   (`deploy-backend.sh:136-159`). DRY-RUN never overwrites the backup slot (prevents silent state loss).
4. `build_and_deploy`: stages `seed_templates.py` + `LICENSE` into build ctx, `docker build --target runtime`,
   then `boot_smoke_test` (pre-promotion guard — run new image in throwaway container, curl `/health`,
   abort if not 200 so a bad image never reaches prod) (`deploy-backend.sh:184-282, 525-585`).
5. `recreate_backend_services` force-recreates `backend` + `celery-worker` + `celery-beat` TOGETHER
   (all share `BACKEND_IMAGE`; mismatch silently drops task handlers) (`deploy-backend.sh:44, 164-167`).
6. `seed_templates_reload` reconciles builtin gallery to seed (anti-drift).
7. `--migrate`: runs `validate-migration.sh` gate, then `alembic upgrade head` with before/after head
   verification (`deploy-backend.sh:419-520`).
8. `post_deploy_health` → on failure **automatic rollback** to `backup-current` (`deploy-backend.sh:621-734`).

**`deploy-frontend.sh`** (homelab → VPS, ~4 min):
1. Precheck (`PRECHECK_SCOPE=frontend`) unless `--skip-precheck` (`deploy-frontend.sh:98-112`).
2. `rsync` `/home/glenn/FlowmannerV2-frontend/` → VPS `/opt/flowmanner/frontend/` (excl. node_modules/.next/.git).
3. SSH: `docker compose build frontend && docker compose up -d --no-deps frontend`.
4. Sync `/opt/flowmanner/nginx/default.conf` + `docker compose restart nginx`.
5. `--rollback` = no-op (no image-tag flow) (`deploy-frontend.sh:118-125`).

**`scripts/pre-deploy-check.sh`, `scripts/post-deploy-verify.sh`, `deploy-all.sh`,
`deploy-frontend-remote.sh`** exist as supporting orchestration (precheck gate + umbrella).

---

## BACKGROUND PROCESSING (Celery / RabbitMQ / Redis)

- **App definition:** `backend/app/tasks/celery_app.py`. `Celery("workflows", broker=amqp://rabbitmq:5672//,
  backend=REDIS_URL)` (`celery_app.py:36-41`). Broker = RabbitMQ; **result backend = Redis**.
- **Serialization:** json in/out (`celery_app.py:44-50`).
- **Worker command** (`docker-compose.yml:168`):
  `celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4 --max-tasks-per-child=100`.
  Beat (`docker-compose.yml:198`): `celery -A app.tasks.celery_app beat --schedule=/tmp/celerybeat-schedule`.
- **Beat schedule** (`celery_app.py:53-75`):
  - `expire-hitl-items` (hitl.expire_items) — 5 min
  - `integration-health-check-all` (integration.health_check_all) — 15 min
  - `decay-memory-entries` (memory.decay_entries) — daily 03:00 UTC (Epic 3.3 retrieval-lifecycle decay)
  - `expire-paused-missions` (mission.expire_paused) — 5 min (pause-timeout auto-fail)
- **Task registration (critical latent-bug history):** custom tasks are NOT auto-imported; the worker
  only imports `app.tasks.celery_app`. `_register_custom_tasks()` (`celery_app.py:133-208`) explicitly
  imports 14 task modules (`background_review_tasks`, `batch_processing`, `deepagents_tasks`,
  `hitl_resume`, `hitl_expiry`, `integration_health_tasks`, `n8n_callback`, `swarm_tasks`,
  `training_tasks`, `eval_run`, `memory_extraction_tasks`, `decay_memory`, `expire_paused_missions`,
  `event_bus_tasks`) + registers class-based `ExecuteMissionTask`. Failures per module are logged, not
  fatal. (History: 6 modules moved to `app.tasks._disabled/` on 2026-06-12 — `celery_app.py:16-23`.)
- **Lease reclaimer lifecycle:** `@worker_ready` starts a daemon-thread `LeaseReclaimer` (gated by
  `FLOWMANNER_LEASE_RECLAIMER_ENABLED`, default true); `@worker_shutdown` stops it
  (`celery_app.py:81-110`). Each worker process = its own reclaimer + asyncio loop.
- **depends_on:** both celery services wait for `rabbitmq`, `postgres`, `redis` healthy
  (`docker-compose.yml:174-180, 204-210`). Healthcheck = `celery inspect ping` (`docker-compose.yml:181-186`).
- **extra_hosts `host.docker.internal:host-gateway`** on backend + celery (`docker-compose.yml:166-167, 227-228`)
  so containers can reach host-bound services (llama.cpp at `10.0.4.1:11434` via Docker gateway).

---

## DATA & VECTOR STORES

- **PostgreSQL 15** (`docker-compose.yml:50-73`): `flowmanner`/`flowmanner` DB (env-overridable).
  Persistent via external named volume `glenn_postgres_data` (`docker-compose.yml:266-268`).
  DDL managed by **Alembic** — 30 migration files in `backend/alembic/versions/`
  (e.g. `20260712_mission_paused_at.py`, `20260711_governance_poison_scan.py`, `gov11_merge_heads_*.py`).
  Migrations run inside the baked container (`docker compose exec backend alembic upgrade head`) and
  survive image rebuilds (data is in the volume, not the image).
- **Redis 7** (`docker-compose.yml:110-133`): AUTH-enabled (`requirepass`), append-only (`--appendonly yes`),
  volume `glenn_redis_data`. Dual role: (a) Celery **result backend**, (b) application cache
  (cache hit/miss metrics in `app/core/metrics.py:64-80`).
- **Qdrant 1.12.0** (`docker-compose.yml:75-108`): vector DB, HTTP 6333 / gRPC 6334, volume
  `glenn_qdrant_data`. Used for embeddings/semantic memory (memory-entry retrieval-lifecycle decay is a
  Beat task). **Hardened `ulimits.nofile=65536`** after a 134x restart loop from `EMFILE` panic
  (`docker-compose.yml:100-108`).
- **RabbitMQ 3 (management)** (`docker-compose.yml:135-158`): Celery **broker** only. management UI on
  localhost `15672`. Volume `glenn_rabbitmq_data`.
- **llama.cpp** is **NOT in Docker** — bare-metal systemd on homelab (`AGENTS.homelab.md:171-198`),
  reachable at `http://10.0.4.1:11434` (Docker gateway), OpenAI-compatible `/v1/chat/completions`.
- **Uploads:** `uploads_data` named volume mounted at `/app/uploads` (`docker-compose.yml:242`).
- **Hermes state bridge:** host `~/.hermes/state.db` mounted **read-only** into backend at
  `/mnt/hermes-state/state.db:ro` for the `/api/hermes-studio` router (`docker-compose.yml:241-246`).

---

## OBSERVABILITY STACK

- **Structured logging:** `structlog` configured in `main_fastapi.py:29-47`. Processors chain:
  contextvars → log level → stack info → exc info → ISO timestamp → **`structlog_scrub_processor`**
  (redacts BYOK secrets/keys from every line) → JSON renderer in prod / Console in dev
  (`main_fastapi.py:37-38`). Factory = `PrintLoggerFactory`, INFO filter.
- **Metrics (Prometheus):** `prometheus_client` gauges/counters/histograms in `app/core/metrics.py`
  (mission totals/duration/tokens, LLM requests/latency/tokens, cache hits/misses, active requests,
  dependency health, eval runs/scores/cost, deploy totals, auth-redirect loops, SSE token latency,
  model fallback, circuit-breaker guard failures, memory-extraction claims). Exposed at **`GET /metrics`**
  via `generate_latest()` (`app/api/v1/health.py:281-285`).
- **HTTP metrics middleware:** `MetricsMiddleware` (`app/api/middleware/metrics.py`) — defines
  `REQUEST_COUNT` / `REQUEST_LATENCY` prom counters but the `dispatch` body **does NOT record them**
  (no `.inc()`/`.observe()` on the actual response) — i.e. the HTTP request metrics are declared but
  currently inert; business metrics from `app/core/metrics.py` are the live ones. Middleware is wired
  at `main_fastapi.py:148`.
- **Health endpoints** (`app/api/v1/health.py`, router mounted at `/health` AND `/api/health`,
  `main_fastapi.py:388-389`):
  - `GET /health` — **TTL-cached 5s** (`_HEALTH_CACHE_TTL`, `health.py:41-44`) probe of Postgres
    (SELECT 1), Redis (ping), LLM config, reliability report, circuit state. Caching added to avoid
    3 round-trips × 500 RPS saturation (`health.py:35-52`).
  - `GET /health/full` — uncached real-time diagnostics (`health.py:177-178`).
  - `GET /metrics` — Prometheus scrape (`health.py:281-285`).
- **Distributed tracing (OTEL):** `app/core/telemetry.py` opt-in via `OTLP_ENDPOINT`. Instruments
  FastAPI + Redis + SQLAlchemy with span-attribute scrubber (`SpanAttributeScrubber`) before export to
  Jaeger/OTLP. **Currently DISABLED** — `OTLP_ENDPOINT` is unset in compose
  (`docker-compose.yml:232`, `docker-compose.dev.yml:49`), so `setup_telemetry` is a no-op
  (`telemetry.py:14-17`). Jaeger service absent from committed compose.
- **External monitoring:** Langfuse integration (`app/services/langfuse_service.py`,
  `app/services/langfuse_metrics.py`) for LLM observability + circuit state; Datadog client present
  (`app/services/datadog/datadog_client.py`).
- **Container healthchecks:** backend (`curl /health`), celery (`celery inspect ping`), postgres
  (`pg_isready`), redis (`redis-cli ping`), qdrant (tcp 6333), rabbitmq (`rabbitmq-diagnostics ping`),
  searxng (`wget`), staged in compose with intervals/retries/`start_period`.

---

## THREE-HOST TOPOLOGY

Three logical hosts (per `AGENTS.md` Quick Reference + `AGENTS.homelab.md:15-34`):

| Host | Public/LAN IP | WireGuard | Role |
|---|---|---|---|
| **VPS** | 74.208.115.142 (public) / 10.99.0.1 (WG) | WG endpoint | Frontend (Next.js), Nginx, SSL termination |
| **Homelab** | 176.141.9.146 (public) / 10.99.0.3 + 172.16.1.1 (LAN) / 10.99.0.3 (WG) | WG peer | Backend (FastAPI), all data stores, llama.cpp |
| **Ops/Dev** | 172.16.1.2 | — | Deploy trigger (human dev work) |

**Network flow (request path):**
```
Internet
  │  :443 (TLS, SSL via nginx/certbot on VPS)
  ▼
VPS  (74.208.115.142)
  ├─ Nginx :443
  │    ├─ /*                → frontend container :3000 (Next.js)
  │    ├─ /api/*            → WireGuard tunnel → Homelab 10.99.0.3:8000 (FastAPI)
  │    ├─ /api/auth/*       → frontend :3000 (NextAuth)
  │    └─ /ws               → WireGuard tunnel → Homelab :8000 (WebSocket)
  │
  ║══════ WireGuard tunnel (VPS 10.99.0.1 ⇄ Homelab 10.99.0.3) ══════║
  ▼
Homelab (10.99.0.3 / 172.16.1.1)
  backend:8000 (Docker, workflows-backend:restored)
     ├─ PostgreSQL :5432   (glenn_postgres_data)
     ├─ Redis :6379        (glenn_redis_data)        ← Celery result backend + cache
     ├─ Qdrant :6333/6334  (glenn_qdrant_data)
     ├─ RabbitMQ :5672     (glenn_rabbitmq_data)     ← Celery broker
     ├─ celery-worker / celery-beat (same image)
     └─ llama.cpp :11434   (bare metal, systemd)    ← via host.docker.internal / 10.0.4.1 gateway
```

- **VPS → Homelab connectivity is exclusively the WireGuard tunnel.** The VPS holds no backend code or
  data; it is a pure TLS/reverse-proxy + static-frontend host. `AGENTS.homelab.md:19` stresses the VPS
  is a *separate* machine reached only by SSH (key `vps_flowmanner_new`) for deploys.
- **Deploy trigger (Ops/Dev, 172.16.1.2):** runs `deploy-backend.sh` / `deploy-frontend.sh`. Backend
  deploy runs on homelab (rebuilds local Docker image). Frontend deploy rsyncs to VPS then builds there.
- **Containers reach host llama.cpp** via `extra_hosts: host.docker.internal:host-gateway`
  (`docker-compose.yml:166-167, 227-228`) and Docker gateway `10.0.4.1:11434` (`AGENTS.homelab.md:198`).
- **Data stores are LAN-only** (postgres/redis/qdrant/rabbitmq published ports are host-bound; rabbitmq
  mgmt bound to `127.0.0.1` only — `docker-compose.yml:149-150`), not exposed to the public internet.

---

## KEY FINDINGS

- **F1 — Image is fully baked; `docker compose build` is a no-op.** Compose uses `image:` not `build:`
  (`docker-compose.yml:221`), so the only update path is `deploy-backend.sh` → `docker build --target runtime`
  (`deploy-backend.sh:557`). This is intentional (no volume mounts) but means any `docker compose build`
  invocation silently does nothing. `AGENTS.homelab.md:88` documents the trap.
- **F2 — Three containers MUST be recreated together.** `backend`, `celery-worker`, `celery-beat` all pin
  `workflows-backend:restored`; an out-of-sync rebuild silently drops Celery task handlers or runs tasks
  against a stale model schema (`deploy-backend.sh:38-43, 164-167`). The deploy script force-recreates all
  three in one call — a real operational coupling worth recording as an ADR.
- **F3 — Custom Celery tasks need explicit import-side-effect registration.** The worker only imports
  `app.tasks.celery_app`; without `_register_custom_tasks()` (14 modules + `ExecuteMissionTask`) every
  custom task is rejected as "unregistered" while RabbitMQ still accepts it — silent drop
  (`celery_app.py:113-208`). This is a latent production risk if the registration list drifts from the
  decorator locations.
- **F4 — Qdrant ulimit hardening is incident-driven.** A hard reboot caused a 134x restart loop from
  actix `EMFILE` (errno 24); fixed with `ulimits.nofile: 65536` (`docker-compose.yml:100-108`). The
  comment is the canonical record of the root cause.
- **F5 — Observability is "prometheus + structlog JSON", NOT Jaeger/OTEL in practice.** `OTLP_ENDPOINT`
  is unset/disabled (`docker-compose.yml:232`); `setup_telemetry` no-ops (`telemetry.py:14-17`). The
  `jaeger` service in `AGENTS.homelab.md:61` is documentation drift — it does not exist in committed
  compose. Live signals: `/metrics` (Prometheus) + JSON logs + `/health` + Langfuse.
- **F6 — HTTP request metrics middleware is inert.** `MetricsMiddleware.dispatch` (`app/api/middleware/metrics.py:14-19`)
  defines `REQUEST_COUNT`/`REQUEST_LATENCY` but never records them; the registered prom counters from
  `app/core/metrics.py` are the only live ones. Prometheus `/metrics` will still export the (zero) HTTP
  series — a gap if someone expects request-rate dashboards.
- **F7 — Frontend is off-repo and deploy has no image-tag rollback.** Source at
  `/home/glenn/FlowmannerV2-frontend` (no git remote); `deploy-frontend.sh --rollback` is a documented
  no-op (`deploy-frontend.sh:118-125`). Rollback = revert a commit + re-deploy. VPS nginx + frontend
  compose are NOT committed in this repo (only referenced by `deploy-frontend.sh`).
- **F8 — Secret defaults are committed in compose.** Redis/RabbitMQ/Postgres fall back to hardcoded
  default passwords in env interpolation (e.g. `redis` default `oFvdKE3HRxsm5CscZpifmwImDidNUmX5`,
  `docker-compose.yml:119,127`; postgres `flowmanner_dev_password`), overridable by `.env`. The real
  prod secrets live in `/opt/flowmanner/.env` (not in repo).
- **F9 — Read-only Hermes state bridge into backend.** Host `~/.hermes/state.db` is mounted `:ro` at
  `/mnt/hermes-state/state.db` (`docker-compose.yml:241-246`) so `/api/hermes-studio` can surface Hermes
  sessions without sharing the agent runtime process. Contract: container opens it `mode=ro`, never
  writes/locks the writer.
- **F10 — Boot-smoke-test guard prevents bad-image prod pushes.** `deploy-backend.sh` runs the freshly
  built image in a throwaway container and aborts the swap if `/health` ≠ 200 (`deploy-backend.sh:184-282`),
  catching runtime import-time crashes that ruff/mypy miss. Post-recreate health check only detects
  (doesn't prevent) a bad image, so this pre-promotion test is the real safety net.

---

*End of analysis. READ-ONLY — no commits, pushes, or edits were made.*
