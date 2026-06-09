# Flowmanner — Agent Instructions

This project spans two machines. Use the file that matches where your agent runs.

- **VPS agents** (74.208.115.142) → [AGENTS.vps.md](./AGENTS.vps.md)
- **Homelab agents** (10.99.0.3 / 172.16.1.1) → [AGENTS.homelab.md](./AGENTS.homelab.md)
- **Ops/Dev agents** (172.16.1.2) → [AGENTS.ops.md](./AGENTS.ops.md)

## Quick Reference

| | VPS | Homelab | Ops/Dev |
|--|-----|---------|---------|
| **Public IP** | 74.208.115.142 | 176.141.9.146 | — |
| **LAN IP** | 10.99.0.1 (WG) | 10.99.0.3 / 172.16.1.1 | 172.16.1.2 |
| **Role** | Frontend (Next.js), Nginx, SSL | Backend (FastAPI), DBs, LLM | Deploy trigger, dev work |
| **SSH** | `ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142` | Local access only | `ssh glenn@172.16.1.1` (key auth) |
| **Project root** | `/opt/flowmanner/` | `/opt/flowmanner/` | `/opt/flowmanner/` |
| **Frontend source** | `/opt/flowmanner/frontend/` (rsync target) | `/home/glenn/FlowmannerV2-frontend/` (edit here) | — |
| **Backend source** | N/A | `/opt/flowmanner/backend/` | — |

## DNS

| Domain | A Record |
|--------|----------|
| flowmanner.com | 74.208.115.142 |
| www.flowmanner.com | 74.208.115.142 |

## Critical Rules (applies to all machines)

1. **NEVER edit files on the VPS directly.** All source edits happen on the homelab.
2. **Source edits never take effect without rebuild.** Docker images have no volume mounts.
3. **Frontend deploy:** `bash /opt/flowmanner/deploy-frontend.sh` (from homelab)
   ⚠️ **Deploy takes ~4 minutes** (rsync + docker build + restart + health checks). Use `timeout=300` or `background=true, notify_on_complete=true`. NEVER retry a deploy that timed out — check if it completed first (`docker compose ps` on VPS). Repeated retries waste resources.
4. **Backend rebuild:** `bash /opt/flowmanner/deploy-backend.sh` (from homelab)
   Optional: `--migrate`, `--dry-run`, `--rollback`
   ⚠️ **Deploy takes ~2 minutes** (backup + build + restart + health checks + auto-rollback on failure). Use `timeout=300`.
   ⚠️ **Use `deploy-backend.sh` instead of raw `docker build` commands** — the script handles image backup, health checks, and automatic rollback.
5. **CodeGraph MCP is available** — use it FIRST before reading files. See AGENTS.homelab.md for details.

## Architecture

```
Internet → VPS (Nginx :443) ──┬── /* ──→ frontend:3000 (Next.js)
                               ├── /api/* ──→ WireGuard ──→ Homelab:8000 (FastAPI)
                               ├── /api/auth/* ──→ frontend:3000 (NextAuth)
                               └── /ws ──→ WireGuard ──→ Homelab:8000 (WebSocket)

Homelab services: PostgreSQL, Redis, Qdrant, RabbitMQ, Celery, Jaeger, llama.cpp
```
# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

## Child DOX Index

Flowmanner is a two-machine stack (VPS frontend + homelab backend). Children are listed in the order an agent should read them when orienting.

### Top-level child contracts (machine- and machine-role-scoped)

| Doc | Scope | Owns |
|-----|-------|------|
| [`AGENTS.homelab.md`](./AGENTS.homelab.md) | Homelab (10.99.0.3 / 172.16.1.1) — backend host | FastAPI/Postgres/Redis/Qdrant/RabbitMQ/Celery/Jaeger + llama.cpp on bare metal. Source-of-truth for backend edits, `deploy-backend.sh`, alembic, WireGuard egress. **Read this first when working on the backend.** |
| [`AGENTS.vps.md`](./AGENTS.vps.md) | VPS (74.208.115.142) — public edge | Nginx SSL termination, Next.js frontend container, WireGuard ingress, cert renewal, firewall. Read-only source — all edits happen on homelab. |
| [`AGENTS.ops.md`](./AGENTS.ops.md) | Ops/dev workstation (172.16.1.2) | SSH-triggered deploys, no local services. Hosts `deploy-frontend-remote.sh`. |
| [`backend/AGENTS.md`](./backend/AGENTS.md) | Backend source subtree (`/opt/flowmanner/backend/`) | FastAPI app structure, no-volume-mount rule, build/restart commands, alembic, MCP gateway, testing. Read in addition to `AGENTS.homelab.md` when touching backend code. |
| [`backend/app/api/AGENTS.md`](./backend/app/api/AGENTS.md) | API HTTP layer (`/opt/flowmanner/backend/app/api/`) | v1 (legacy stable) / v2 (current default) / v3 (workspace + cookie+Bearer sessions) versioning policy, the standardized envelope, the `_mission_cqrs` / `_blueprint_cqrs` split, the Phase 10.1 dual-write + `USE_NEW_READS` feature flag. Read first when adding a route. |
| [`backend/app/services/AGENTS.md`](./backend/app/services/AGENTS.md) | Business-logic services layer (`/opt/flowmanner/backend/app/services/`) | 22 named service clusters (mission exec, RAG, LLM routing, substrate, integrations, auth, memory, observability, self-improvement, etc.) and the cross-cutting contracts (async-first, late-bound callables, BYOK precedence, no-`db.commit()` in sub-modules). |
| [`backend/app/services/substrate/AGENTS.md`](./backend/app/services/substrate/AGENTS.md) | Unified execution substrate (H5.1, GA) | The single durable executor, 7 strategies, shared node executor, event log, replay engine, adapters, assertion engine, baseline extractor, trigger bridge. Read first when touching workflow execution. |

### Operational scripts & deploy surfaces (project root)

| Path | Purpose | DOX coverage |
|------|---------|--------------|
| `deploy-backend.sh` | Rebuild backend image with health checks + auto-rollback. **Use this — never raw `docker build` + `docker compose up`.** | Documented in `AGENTS.homelab.md` |
| `deploy-frontend.sh` | rsync + VPS build + nginx restart + 10-retry health check (~4 min) | Documented in `AGENTS.homelab.md` and `AGENTS.ops.md` |
| `deploy-frontend-remote.sh` | Same as above, triggered from ops/dev workstation | Documented in `AGENTS.ops.md` |
| `deploy-all.sh` | Backend + frontend in one shot | Root-level script — semantics inherited from `deploy-backend.sh` + `deploy-frontend.sh` |
| `restart-nginx.sh` | VPS-side nginx restart helper | Documented in `AGENTS.vps.md` |
| `Makefile` | Top-level task shortcuts | Open to read; no dedicated doc |
| `docker-compose.yml` | Homelab stack | Open to read; canonical reference is `AGENTS.homelab.md` |
| `docker-compose.dev.yml`, `docker-compose.staging.yml` | Dev / staging variants | Open to read |
| `nginx/default.conf` | Reverse proxy + SSL config | Documented in `AGENTS.vps.md` |
| `seed_templates.py`, `query_users.py`, `check_schema.py`, `validate_constraints.py` | Ad-hoc DB/utility scripts | Open to read; not in the agent's normal flow |

### Backend subtree (under `backend/`)

Backend has a dedicated child contract at `backend/AGENTS.md`. Subtree-relative notes:

| Path | Purpose | Notes |
|------|---------|-------|
| `backend/app/main_fastapi.py` | App entry point | Uvicorn target |
| `backend/app/api/v1/` | v1 endpoints (60+ modules) | Stable API surface; do not break schemas casually |
| `backend/app/api/v2/`, `v3/` | Next-gen API versions | Used for newer features; not 1:1 with v1 |
| `backend/app/api/_mission_cqrs/`, `_blueprint_cqrs/` | CQRS command/query splits for missions + blueprint runs | Underscore prefix marks internal/non-public |
| `backend/app/api/middleware/` | Audit, metrics, rate limit, security, versioning | |
| `backend/app/services/` | Business logic layer (100+ services) | Heaviest directory; check before adding new code |
| `backend/app/models/` | SQLAlchemy ORM models | Every new model needs an alembic migration |
| `backend/app/schemas/`, `routers/`, `core/`, `dependencies/`, `tasks/`, `workers/`, `websocket/`, `tools/`, `integrations/`, `cache/`, `utils/`, `cli/`, `sdk/`, `governance/`, `observability/`, `middleware/` | Conventional FastAPI layers | See `backend/AGENTS.md` for the full layout |
| `backend/alembic/` | Database migrations | New model → `alembic revision --autogenerate` then commit. Migrations run on the persistent Postgres volume. |
| `backend/mcp_gateway/client_config.json` | MCP server definitions (codegraph-ai, filesystem, github) | Edit JSON, not code |
| `backend/agent_definitions/` | 15 domain agent config trees (academic, browser, design, engineering, finance, game-dev, marketing, paid-media, product, project-mgmt, sales, spatial-computing, specialized, support, testing) | Pure config; treat as data |
| `backend/tests/` | 100+ test files incl. `chaos/`, `integration/` subdirs | Run with `docker compose exec backend pytest app/tests/ -v` |
| `backend/docs/`, `backend/Docs/` | Backend-specific narrative docs (H1–H5 reports, sprint plans, architecture, plan-fix, etc.) | Open to read; not the source of truth — the root `docs/` and `Docs/` are |

### Frontend subtree

Frontend source **does not live in this repo** on disk. It lives at `/home/glenn/FlowmannerV2-frontend/` on the homelab and rsyncs to the VPS at `/opt/flowmanner/frontend/` at deploy time. See `AGENTS.homelab.md` for the full deploy flow, `ship`/`wip`/`dev` commands, and CodeGraph MCP usage.

### Documentation & planning

| Path | Purpose | Notes |
|------|---------|-------|
| `docs/` | Current operational docs | `mission-architecture.md`, `HOMELAB-REBOOT.md`, `blog-…`, `PORTFOLIO-…`, `PROFESSIONALIZATION-PLAN.md` |
| `docs/adr/` | Architecture Decision Records | One entry so far: `001-mission-executor-decomposition.md`. Add new ADRs here. |
| `docs/plans/` | Forward-looking plans (separate from `plans/`) | |
| `Docs/` | Long-form strategic + analysis docs (canonical knowledge, roadmap, deep research, brainstorm context, phase reports) | Treat as reference, not instructions |
| `Docs/OLD/` | Archived docs | Do not edit; read-only history |
| `plans/` | Active planning + prompt + research files | `tools-catalog-roadmap.json`, `NEXT-SESSION.md`, `sandboxd-integration-*`, `ARCHIVED-PHASES-1-5.md` |
| `plans/tasks/`, `plans/TEMP/`, `plans/vps-rebuild/`, `plans/research/` | Working subfolders | May be ephemeral |
| `scripts/` | Operational shell scripts | `pre-flight.sh`, `post-edit-check.sh`, `post-deploy-verify.sh`, `mission-gate.sh`, `health-monitor.sh`, `restore-db.sh` / `restore-verify.sh`, `backup-db.sh` / `backup-staging.sh`, `setup-cron.sh`, `generate-ts-sdk.sh` / `generate-python-sdk.sh`, `deploy_flowmanner.sh`, `phase10_soak_reminder.sh`, `test_missions.py` |
| `scripts/cron/`, `scripts/prompts/`, `scripts/tests/`, `scripts/plans/` | Cron entries, prompt library, script tests, script plans | Read on demand |

### Generated assets & infra

| Path | Purpose | Notes |
|------|---------|-------|
| `sdk-python/` | Auto-generated Python SDK (OpenAPI → client) | Regenerate with `scripts/generate-python-sdk.sh`; do not hand-edit |
| `openapi.json` | Exported OpenAPI spec from the backend | Source of truth for SDK generation |
| `static/` | Static file volume for `workflows-static` nginx | |
| `uploads/` | User-uploaded file volume | Persistent |
| `backups/` | DB / image backups produced by `backup-*.sh` | |
| `dev/` | Local-dev overrides | `docker-compose.dev.yml`, `docker-entrypoint.dev.sh`, `.env.dev` |
| `nginx/` | Proxy config + cert mount | Documented in `AGENTS.vps.md` |
| `.github/`, `.hermes/`, `.sisyphus/` | Tooling caches/dirs | Not in agent's normal flow |
| `.env`, `.env.staging`, `backend/.env` | Secrets | Never commit; never edit in a session without explicit ask |

### Open DOX gaps (follow-up work)

These are durable subtrees that **do not yet have a child AGENTS.md** and would benefit from one. Listed so the next agent can pick them up:

- `backend/app/services/` — largest single directory in the project; deserves a map of service clusters (mission, agent, rag, llm_router, integration, observability, substrate, etc.)
- `backend/alembic/versions/` — 80+ migrations; the merge heads and naming convention deserve a short contract
- `backend/app/api/v1/` vs `v2/` vs `v3/` — versioning policy is not documented anywhere
- `backend/agent_definitions/` — 15 domain trees; a manifest/index would help
- `sdk-python/` — regeneration policy and consumption guidance
- `scripts/` — what runs on cron, what is one-shot, what is safe to run by hand
- `docs/adr/` — needs a short template + writing guide

Create a child AGENTS.md in any of the above when working in that subtree for the first time, per the DOX "Read Before Editing / Update After Editing" rules.
