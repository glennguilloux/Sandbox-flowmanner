# Flowmanner — Homelab Agent Instructions

## ⚠️ YOU ARE ON THE HOMELAB

This machine is the **homelab** at `10.99.0.3` / `172.16.1.1`.

You are NOT on the VPS. The VPS is a SEPARATE machine at `74.208.115.142` (WireGuard: `10.99.0.1`) — you reach it via SSH with sshpass. Do NOT tell the user to "run commands on the homelab" — you are already here. Just run commands directly.

## Homelab Role

The homelab runs the **API backend and data stores**. The VPS proxies public traffic here through a WireGuard tunnel.

```
VPS (10.99.0.1) → WireGuard → Homelab (10.99.0.3:8000) → FastAPI backend
                                                     → PostgreSQL (:5432)
                                                     → Redis (:6379)
                                                     → Qdrant
```

## Paths

| What | Path | Notes |
|------|------|-------|
| Project root | `/opt/flowmanner/` | Docker Compose lives here |
| Backend source | `/opt/flowmanner/backend/` | Dockerfile, app/, alembic/, etc. |
| Frontend source (local) | `/home/glenn/FlowmannerV2-frontend/` | rsync'd to VPS for deploy |
| Docker Compose | `/opt/flowmanner/docker-compose.yml` | THIS is the compose file, not /mnt/workflows/ |
| Environment | `/opt/flowmanner/.env` | Backend env vars |
| WireGuard config | `/etc/wireguard/wg0.conf` | |

## Services

| Service | Container | IP/Port | Notes |
|---------|-----------|---------|-------|
| Backend (FastAPI) | `backend` | 10.0.4.6:8000 | Image: `workflows-backend:restored` |
| PostgreSQL | `workflow-postgres` | 10.0.4.2:5432 | Data in `postgres_data` volume |
| Redis | `workflow-redis` | 10.0.4.5:6379 | Data in `redis_data` volume |
| Qdrant | `workflow-qdrant` | 10.0.4.3:6333 | Data in `qdrant_data` volume |
| Static files | `workflows-static` | 10.0.4.8:80 | nginx serving /opt/flowmanner/static/ |
| llama.cpp | bare metal (systemd) | 0.0.0.0:11434 | NOT in Docker |
| WireGuard | `wg0` | 51820/udp | Tunnel to VPS |

## ⚠️ Backend Container Rules (READ THIS)

**The backend container has NO volume mounts.** All code is baked into the Docker image via `COPY . /app/` in the Dockerfile.

```
WHAT THIS MEANS:
- Files copied into a running container (`docker cp`) are LOST on rebuild
- To make changes permanent, edit files in /opt/flowmanner/backend/ THEN rebuild
- The ONLY way to update the running backend is: rebuild the image + restart the container
- Database data (PostgreSQL, Redis, Qdrant) IS persistent via named volumes
```

**To make ANY code change to the backend:**
1. Edit the source file in `/opt/flowmanner/backend/`
2. Build the image: `docker build -t workflows-backend:restored /opt/flowmanner/backend/`
3. Restart: `docker compose up -d --no-deps --force-recreate backend`

**NEVER** `docker cp` into the backend container unless it's a temporary debug action that you expect to lose.

> **Why not `docker compose build backend`?** The compose file uses `image:` not `build:`, so `docker compose build` is a no-op. See [REBUILD-BACKEND.md](./REBUILD-BACKEND.md) for details.

## Backend Deployment

```bash
# Health check
curl http://127.0.0.1:8000/api/health

# Rebuild after code changes (MANDATORY — no volume mount)
docker build -t workflows-backend:restored /opt/flowmanner/backend/
docker compose up -d --no-deps --force-recreate backend
```

### Database Migrations (Alembic)

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

## Frontend Deployment to VPS

The frontend source lives locally at `/home/glenn/FlowmannerV2-frontend/`. It has no git remote.

```bash
# Use the deploy script (preferred)
bash /opt/flowmanner/deploy-frontend.sh

# Or manually:
rsync -avz --progress \
  -e "sshpass -p '@Geegee197623' ssh -o StrictHostKeyChecking=accept-new" \
  --exclude node_modules --exclude .next --exclude .git \
  /home/glenn/FlowmannerV2-frontend/ \
  root@74.208.115.142:/opt/flowmanner/frontend/

sshpass -p '@Geegee197623' ssh -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "cd /opt/flowmanner && docker compose build frontend && docker compose up -d --no-deps frontend"
```

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

## Credentials

| Service | Username | Password |
|---------|----------|----------|
| PostgreSQL | flowmanner | FlowDB2026! |

## Troubleshooting

| Problem | Check |
|---------|-------|
| Backend down | `docker ps \| grep backend`, `curl http://127.0.0.1:8000/api/health` |
| VPS can't reach backend | `sudo wg show`, check from VPS: `curl http://10.99.0.3:8000/api/health` |
| Code changes not taking effect | You must rebuild: `cd /opt/flowmanner && docker compose build backend && docker compose up -d --no-deps --force-recreate backend` |
| Migration needed | `cd /opt/flowmanner && docker compose exec backend alembic upgrade head` |
| LLM not responding | `systemctl status llama-server`, `curl http://localhost:11434/health` |
| VRAM issues | `nvidia-smi` |
