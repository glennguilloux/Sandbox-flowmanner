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
