# Homelab Reboot Recovery

Everything on the homelab should auto-start after reboot via Docker restart policies and systemd. This document is a reference for manual recovery if anything fails.

## Quick Check

```bash
# All-in-one status check
docker ps --format 'table {{.Names}}\t{{.Status}}' && systemctl is-active llama-server
```

## Docker Containers (managed by docker compose)

All containers have `restart: unless-stopped` and should come back automatically.

| Container | Image | Purpose | Health Check |
|-----------|-------|---------|--------------|
| `backend` | `workflows-backend:restored` | FastAPI backend on `:8000` | `curl http://127.0.0.1:8000/api/health` |
| `workflow-postgres` | `postgres:15-alpine` | PostgreSQL on `:5432` | `docker exec workflow-postgres pg_isready` |
| `workflow-redis` | `redis:7-alpine` | Redis cache on `:6379` | `docker exec workflow-redis redis-cli ping` |
| `workflow-qdrant` | `qdrant/qdrant:v1.12.0` | Vector store on `:6333` | `curl http://127.0.0.1:6333/healthz` |
| `workflow-rabbitmq` | `rabbitmq:3-management-alpine` | Message broker on `:5672` (UI on `:15672`) | `docker exec workflow-rabbitmq rabbitmq-diagnostics -q ping` |
| `celery-worker` | same as `backend` | Celery task worker | `docker logs celery-worker --tail 5` |
| `celery-beat` | same as `backend` | Celery scheduler | `docker logs celery-beat --tail 5` |
| `jaeger` | `jaegertracing/all-in-one:latest` | Tracing UI on `:16686` | `curl http://127.0.0.1:16686/` |
| `workflows-static` | `nginxinc/nginx-unprivileged:1.27-alpine` | Static files on `:8080` | `curl http://127.0.0.1:8080/` |

### Manual restart (if needed)

```bash
cd /opt/flowmanner && docker compose up -d
```

If only one container is down:
```bash
docker start <container-name>
# or
cd /opt/flowmanner && docker compose up -d --no-deps --force-recreate <service-name>
```

## Bare Metal Service: llama.cpp

| Service | Binary | Model | Port |
|---------|--------|-------|------|
| `llama-server.service` | `/mnt/apps/llama.cpp-mtp/build/bin/llama-server` | Qwen3.6-27B-Q5_K_M (MTP) | `0.0.0.0:11434` |

```bash
# Check status
systemctl status llama-server

# Restart
sudo systemctl restart llama-server

# Health
curl http://localhost:11434/health

# VRAM check (2x RTX 5060 Ti, ~32GB total)
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
```

### Systemd unit location
`/etc/systemd/system/llama-server.service`

## Startup Order

If restarting from scratch, the dependency order is:

1. **Data stores first** — postgres, redis, qdrant, rabbitmq
2. **Backend** — depends on all four data stores
3. **Celery worker + beat** — depend on backend image + rabbitmq + redis
4. **Static + Jaeger** — independent, start anytime
5. **llama.cpp** — independent (bare metal systemd, not Docker)

In practice, `docker compose up -d` handles order via `depends_on` and restart policies. The only manual step is `llama-server` if systemd didn't auto-start it.

## Post-Reboot Verification

```bash
# 1. Backend health (checks postgres, redis, langfuse, LLM)
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool

# 2. LLM health
curl http://localhost:11434/health

# 3. All containers running
docker ps --format 'table {{.Names}}\t{{.Status}}'

# 4. llama.cpp running
systemctl is-active llama-server

# 5. VPS connectivity (from homelab, checks WireGuard tunnel)
curl -s http://10.99.0.1/ -o /dev/null -w "%{http_code}"
```

## If Something Won't Start

| Problem | Fix |
|---------|-----|
| Backend unhealthy | `docker logs backend --tail 30` — usually waiting for postgres |
| postgres won't start | Check disk space: `df -h`. Data is on named volume `workflow-postgres-data` |
| redis auth error | Password in `/opt/flowmanner/.env` under `REDIS_PASSWORD` |
| llama.cpp OOM | `nvidia-smi` — check VRAM. Kill stale processes: `sudo fuser -v /dev/nvidia*` |
| Celery crash loop | Usually an import error — `docker logs celery-worker --tail 50` |
| WireGuard down (VPS unreachable) | `sudo wg show` — if no handshake, `sudo systemctl restart wg-quick@wg0` |
| RabbitMQ management UI | `http://127.0.0.1:15672` — guest/guest (default) |
