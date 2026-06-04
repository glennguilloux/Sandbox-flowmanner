# Backend Rebuild Pattern

**CRITICAL**: The homelab backend container does NOT auto-rebuild when source files change.

## The Problem

```bash
# This does NOT rebuild the image — it's a no-op if image already exists
docker compose build backend
docker compose up -d --no-deps --force-recreate backend
# Container still runs OLD code!
```

The `docker-compose.yml` uses `image: workflows-backend:restored` (not a `build:` section), so `docker compose build` does nothing useful.

## The Fix — Always Use This Sequence

```bash
# Step 1: Build the image FROM the Dockerfile (not via compose)
docker build -t workflows-backend:restored /opt/flowmanner/backend/

# Step 2: Recreate the container with the new image
docker compose up -d --no-deps --force-recreate backend
```

Or as a one-liner:

```bash
docker build -t workflows-backend:restored /opt/flowmanner/backend/ && \
docker compose up -d --no-deps --force-recreate backend
```

## Why This Happens

| What | Why |
|------|-----|
| `docker compose build backend` | Looks for `build:` in docker-compose.yml — there isn't one, so it's a no-op |
| `docker build -t workflows-backend:restored ...` | Actually builds from `/opt/flowmanner/backend/Dockerfile` |
| `--force-recreate` | Forces container to use the newly built image |
| `--no-deps` | Don't restart postgres/redis/qdrant (unnecessary) |

## Verification

After rebuild, verify the container is running fresh code:

```bash
# Check container start time
docker inspect backend --format '{{.State.StartedAt}}'

# Check image creation time
docker images workflows-backend:restored --format "{{.CreatedAt}}"

# Test a known endpoint
curl -s http://127.0.0.1:8000/health
```

## Related Notes

- Backend source: `/opt/flowmanner/backend/`
- Image name: `workflows-backend:restored`
- Container name: `backend`
- Docker Compose file: `/opt/flowmanner/docker-compose.yml`
- **NEVER** use `docker cp` to update files — always rebuild the image
