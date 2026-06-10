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

## ⚠️ Active Warnings (read first — applies to ALL machines)

The following items are in-flight or broken. Read the linked files before recommending any deploy or auth-related work:

- ~~**Sandbox preview auth chain**~~ ✅ **RESOLVED.** Fixed and deployed 2026-06-10 across 3 commits:
  - `4d8e04d` — UUID-vs-JWT bug fixed in `sandbox_preview.py` (added `_is_jwt()` heuristic + DB lookup for UUID cookies via `get_refresh_token()`)
  - `800b670` — ToolResult field name fix in `io.py` (code execute 422 → working)
  - `cd70bb6` — Auth chain completed (`auth.py` `_auth_response()` helper, `auth_cookies.py` cookie path widened to `/`)
  - Frontend: `auth.ts` session callback exposes `refreshToken` for `/api/auth/preview-cookie` route
  - 14 new tests in `test_sandbox_preview_auth.py`, all passing
  - Audit: [`.hermes/plans/SANDBOX-PREVIEW-401-DEEPSEEK-AUDIT.md`](.hermes/plans/SANDBOX-PREVIEW-401-DEEPSEEK-AUDIT.md)
  - Fix plan: [`.hermes/plans/SANDBOX-PREVIEW-FIX-DEEPSEEK-PLAN.md`](.hermes/plans/SANDBOX-PREVIEW-FIX-DEEPSEEK-PLAN.md)
  - Roadmap: `docs/REBUILD-ROADMAP.md` → ✅ DONE
- **REBUILD-ROADMAP.md is the canonical truth** for current rebuild state. Last verified 2026-06-10. If your work touches the rebuild phases, read it first.
- **Memory stores are PER-MACHINE.** The agentmemory MCP store at `~/.agentmemory/data/state_store.db` is local to the machine where the agent runs. Do not assume a memory you saved on homelab is visible on ops (172.16.1.2) or VPS (74.208.115.142). For cross-instance context, rely on docs/AGENTS.md, not memory.
