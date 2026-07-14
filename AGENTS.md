# Flowmanner — Agent Instructions

**End-of-session ritual:** see [SESSION-RITUAL.md](./SESSION-RITUAL.md). Every
agent (me, DeepSeek, anything LLM) must run the exit audit, commit, and push
to origin at the end of every session that changed code. No deploy without
human review.

This project spans two machines. Use the file that matches where your agent runs.

- **VPS agents** (74.208.115.142) → [AGENTS.vps.md](./AGENTS.vps.md)
- **Homelab agents** (10.99.0.3 / 172.16.1.1) → [AGENTS.homelab.md](./AGENTS.homelab.md)
- **Ops/Dev agents** (172.16.1.2) → [AGENTS.ops.md](./AGENTS.ops.md)

## Docs

- **Mission template catalog** (35 built-in templates, node types, categories, add-a-template guide) → [templates/README.md](./templates/README.md)

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
6. **Verification scoping (path-aware):** The generic "run `make test; make lint; make build`" instruction applies **only when source code changed**. If the only modified files are documentation or handoff artifacts — anything under `.sisyphus/`, `docs/`, or top-level `*.md` — skip the full suite. Doc-only changes are verified by the session ritual checklist (`SESSION-RITUAL.md`), not by pytest. Only run `make test` / `make lint` / `make build` when `.py`, `.ts`, `.tsx`, or other source files were actually touched.

## Architecture

```
Internet → VPS (Nginx :443) ──┬── /* ──→ frontend:3000 (Next.js)
                               ├── /api/* ──→ WireGuard ──→ Homelab:8000 (FastAPI)
                               ├── /api/auth/* ──→ frontend:3000 (NextAuth)
                               └── /ws ──→ WireGuard ──→ Homelab:8000 (WebSocket)

Homelab services: PostgreSQL, Redis, Qdrant, RabbitMQ, Celery, llama.cpp
```

## ⚠️ Active Warnings (read first — applies to ALL machines)

The following items are in-flight or broken. Read the linked files before recommending any deploy or auth-related work:

- ~~**Sandbox preview auth chain**~~ ✅ RESOLVED 2026-06-10 — see `.hermes/plans/SANDBOX-PREVIEW-FIX-DEEPSEEK-PLAN.md`.
- ~~**REBUILD-ROADMAP.md**~~ ✅ ARCHIVED. Preserved at `.sisyphus/plans/OLD/REBUILD-ROADMAP-2026-06-12.md`. Current active plan: `.sisyphus/plans/frontend-wiring-roadmap.md`.
- **Memory stores are PER-MACHINE.** The agentmemory MCP store at `~/.agentmemory/data/state_store.db` is local to the machine where the agent runs. Do not assume a memory you saved on homelab is visible on ops (172.16.1.2) or VPS (74.208.115.142). For cross-instance context, rely on docs/AGENTS.md, not memory.
