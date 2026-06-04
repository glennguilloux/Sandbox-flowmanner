# P5: Docker Image/Service Hygiene Audit — H4 Baseline

**Audit date**: June 3, 2026
**Baseline**: 35 images, 527.1GB images, 219.8GB volumes, 581.8GB build cache

---

## 1. Active Containers (DO NOT TOUCH)

| Container | Image | Status |
|---|---|---|
| backend | workflows-backend:restored | healthy |
| celery-worker | (built from compose) | healthy |
| celery-beat | (built from compose) | healthy |
| workflow-postgres | postgres:15-alpine | healthy |
| workflow-qdrant | qdrant/qdrant:v1.12.0 | healthy |
| workflow-redis | redis:7-alpine | healthy |
| workflow-rabbitmq | rabbitmq:3-management-alpine | healthy |
| workflows-static | nginxinc/nginx-unprivileged:1.27-alpine | healthy |
| searxng | searxng/searxng:latest | healthy |
| jaeger | jaegertracing/all-in-one:latest | healthy |
| amazing_heisenberg | ghcr.io/github/github-mcp-server | running |
| unruffled_wozniak | ghcr.io/github/github-mcp-server | running |

---

## 2. Image Categorization

### KEEP — actively used by running containers or compose

| Image | Size | Reason |
|---|---|---|
| workflows-backend:restored | 11.8GB | Active backend container |
| postgres:15-alpine | 393MB | workflow-postgres |
| qdrant/qdrant:v1.12.0 | 277MB | workflow-qdrant |
| redis:7-alpine | 62.3MB | workflow-redis |
| rabbitmq:3-management-alpine | 275MB | workflow-rabbitmq |
| nginxinc/nginx-unprivileged:1.27-alpine | 75MB | workflows-static |
| nginx:alpine | 95.1MB | Compose VPS reference |
| searxng/searxng:latest | 375MB | searxng container |
| jaegertracing/all-in-one:latest | 124MB | jaeger container |
| ghcr.io/github/github-mcp-server:latest | 63MB | MCP server containers |

### KEEP — backup tag (emergency rollback)

| Image | Size | Reason |
|---|---|---|
| workflows-backend:backup-current | 11.8GB | Emergency rollback target |

### REMOVE — orphaned backup tags (one rollback saved)

| Image | Size | Reason |
|---|---|---|
| workflows-backend:backup-20260529-222933 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260530-200417 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260530-200654 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260530-201602 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260530-203948 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260530-204344 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260530-204647 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260601-085012 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260601-085245 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260601-090108 | 11.8GB | Old, superseded |
| workflows-backend:backup-20260601-175823 | 11.8GB | Old, superseded |

### REMOVE — unused/obsolete tags

| Image | Size | Reason |
|---|---|---|
| workflows-backend:latest | 9.42GB | Not in use; `restored` is active |
| workflows-backend:dev | 9.73GB | Not in use; dev workflow uses `restored` |

### REMOVE — test sandbox images (no running containers)

| Image | Size | Reason |
|---|---|---|
| test-sandbox-v4:latest | 11.8GB | Orphaned test image |
| test-sandbox-v3:latest | 11.8GB | Orphaned test image |
| test-sandbox-v2:latest | 11.8GB | Orphaned test image |
| test-sandbox-fix:latest | 11.8GB | Orphaned test image |
| test-sandbox-new:latest | 11.8GB | Orphaned test image |
| test-copy:latest | 14MB | Orphaned test image |

### REMOVE — unused

| Image | Size | Reason |
|---|---|---|
| alpine:latest | 14MB | Orphaned, no containers |
| mmartial/comfyui-nvidia-docker:ubuntu24_cuda13.0-20251006 | 14.2GB | Orphaned, unrelated to Flowmanner |

---

## 3. Cleanup Plan

### 3a — Remove orphaned images (estimated reclaim: ~190GB)

```bash
docker rmi $(docker images --filter "dangling=true" -q)  # dangling first
docker rmi workflows-backend:backup-20260529-222933
docker rmi workflows-backend:backup-20260530-200417
docker rmi workflows-backend:backup-20260530-200654
docker rmi workflows-backend:backup-20260530-201602
docker rmi workflows-backend:backup-20260530-203948
docker rmi workflows-backend:backup-20260530-204344
docker rmi workflows-backend:backup-20260530-204647
docker rmi workflows-backend:backup-20260601-085012
docker rmi workflows-backend:backup-20260601-085245
docker rmi workflows-backend:backup-20260601-090108
docker rmi workflows-backend:backup-20260601-175823
docker rmi workflows-backend:latest
docker rmi workflows-backend:dev
docker rmi test-sandbox-v4:latest
docker rmi test-sandbox-v3:latest
docker rmi test-sandbox-v2:latest
docker rmi test-sandbox-fix:latest
docker rmi test-sandbox-new:latest
docker rmi test-copy:latest
docker rmi alpine:latest
docker rmi mmartial/comfyui-nvidia-docker:ubuntu24_cuda13.0-20251006
```

### 3b — Prune build cache (estimated reclaim: ~519GB)

```bash
docker builder prune --all --force
```

### 3c — Prune unused volumes (estimated reclaim: ~219GB)

```bash
docker volume prune --force
```

### 3d — docker system prune (safe subset after above)

```bash
docker system prune --force
```

---

## 4. Pre-Cleanup Disk

- `/dev/nvme0n1p2`: 1.9T total, 1.5T used (80%), 373G available

## 5. Cleanup Order

1. Remove orphaned images first (safest)
2. Prune build cache (no running container impact)
3. Prune unused volumes (check for data-bearing volumes first)
4. Re-measure disk usage
