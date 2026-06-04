# FlowManner Production Deploy Runbook

**Audience:** DevOps / Backend engineers  
**Last updated:** 2026-06-02  
**Machines:** Homelab (172.16.1.1) runs backend + Hermes; VPS (74.208.115.142) runs frontend + nginx  
**SSH key:** `~/.ssh/vps_flowmanner_new` — all VPS commands require this key  
**SSH alias:** Copy this into `~/.ssh/config` or use the `VPS_SSH` variable below:

```bash
# Add to ~/.ssh/config (one-time):
Host vps-flowmanner
    HostName 74.208.115.142
    User root
    IdentityFile ~/.ssh/vps_flowmanner_new
    StrictHostKeyChecking accept-new

# Then all commands simplify to: ssh vps-flowmanner "..."
# For copy/paste convenience, this runbook uses: VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"
```

---

## Table of Contents

- [A. Preflight](#a-preflight)
- [B. Frontend Deploy](#b-frontend-deploy-canonical)
- [C. Backend Deploy](#c-backend-deploy)
- [D. Verification Matrix](#d-verification-matrix)
- [E. Rollback Matrix](#e-rollback-matrix)
- [F. Cutover GO/NO-GO Checklist](#f-cutover-gono-go-checklist)
- [G. Team Announcement Template](#g-team-announcement-template)
- [Single-Shot Command List](#single-shot-command-list-experienced-operators)

---

## A. Preflight

Run these checks on the homelab BEFORE any deploy.  Every check must pass (or be explicitly waived).

Define the VPS_SSH variable first:

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"
```

| # | Command | Success criteria | If fail |
|---|---------|-----------------|---------|
| 1 | `docker ps --filter name=backend --filter status=running -q` | Non-empty output | Backend container is down — investigate `docker logs backend --tail 50` before deploying |
| 2 | `curl -sf --max-time 10 http://localhost:8000/health` | HTTP 200 + JSON body | Backend not serving health endpoint — check uvicorn logs |
| 3 | `docker ps --filter name=workflow-postgres --filter status=running -q` | Non-empty output | PostgreSQL down — check disk, restart container |
| 4 | `docker ps --filter name=workflow-redis --filter status=running -q` | Non-empty output | Redis down — restart |
| 5 | `docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend alembic current` | Single head revision shown | If backend is running: run `docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend alembic upgrade head`. If backend is down, deploy first then migrate. |
| 6 | `sudo wg show wg0 \| grep "latest handshake"` | Shows timestamp < 2 min ago | WireGuard tunnel down — `sudo wg-quick down wg0 && sudo wg-quick up wg0` |
| 7 | `$VPS_SSH "echo OK"` | Prints `OK` | VPS unreachable — check network, IONOS status |
| 8 | `$VPS_SSH "cd /opt/flowmanner && docker compose ps --format json"` | Shows running containers (frontend, nginx) | VPS Docker Compose down — investigate before deploying |
| 9 | `cd /opt/flowmanner/backend && python -m pytest -q 2>&1 \| tail -1` | `N passed, 0 failed` | Fix failing tests before deploying |
| 10 | `df -h / \| awk 'NR==2{print $5}' \| tr -d '%'` | < 85 | Disk nearly full — clean logs/images before deploying |

### Preflight One-Liner (copy/paste)

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"
echo "=== Preflight ===" && \
docker ps --filter name=backend --filter status=running -q | grep -q . && echo "✓ backend running" || echo "✗ backend DOWN" && \
curl -sf --max-time 10 http://localhost:8000/health >/dev/null && echo "✓ backend health OK" || echo "✗ backend health FAIL" && \
docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend alembic current 2>/dev/null | head -1 && \
sudo wg show wg0 | grep "latest handshake" && \
$VPS_SSH "echo ✓ VPS reachable" && \
$VPS_SSH "cd /opt/flowmanner && docker compose ps --format json 2>/dev/null | grep -c running" | xargs -I{} echo "✓ VPS containers running: {}"
```

---

## B. Frontend Deploy (canonical)

**Source:** `/home/glenn/FlowmannerV2-frontend/` (homelab)  
**Target:** VPS at `/opt/flowmanner/frontend/`  
**Duration:** ~4 minutes (rsync + docker build + restart + health checks)  
**Script:** `/opt/flowmanner/deploy-frontend.sh`

### B.1 — Canonical path (use the deploy script)

```bash
bash /opt/flowmanner/deploy-frontend.sh
```

**What it does:**
1. Pre-deploy health check (frontend container + nginx)
2. Saves current image as `flowmanner-frontend:backup-current` (rollback safety)
3. Rsyncs source from homelab → VPS (`/home/glenn/FlowmannerV2-frontend/`)
4. `docker compose build frontend` on VPS
5. `docker compose up -d --no-deps frontend` on VPS
6. `docker compose restart nginx` on VPS
7. Post-deploy health check with 10 retries at 5s intervals

### B.2 — Dry-run (preview without executing)

```bash
bash /opt/flowmanner/deploy-frontend.sh --dry-run
```

### B.3 — Rollback to previous frontend version

```bash
bash /opt/flowmanner/deploy-frontend.sh --rollback
```

### B.4 — Manual path (if the script is unavailable)

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"

# Step 1: Save current image
$VPS_SSH "docker tag flowmanner-frontend:latest flowmanner-frontend:backup-current"

# Step 2: Rsync source (homelab → VPS)
rsync -avz --delete --progress \
  -e "ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new" \
  --exclude /node_modules --exclude /.next/cache --exclude /.git --exclude /.env.local \
  /home/glenn/FlowmannerV2-frontend/ \
  root@74.208.115.142:/opt/flowmanner/frontend/

# Step 3: Build + deploy (VPS, ~3 min, use timeout=300)
$VPS_SSH "cd /opt/flowmanner && docker compose build frontend && docker compose up -d --no-deps frontend && docker compose restart nginx"

# Step 4: Verify
sleep 15
$VPS_SSH "docker compose -f /opt/flowmanner/docker-compose.yml ps frontend --format json | grep -q running && echo 'OK' || echo 'FAIL'"
```

### B.5 — Stale-build protection (chunk verification)

After a frontend deploy, verify the deployed JavaScript actually changed (not a cached/stale build):

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"

# Record pre-deploy chunk hash
PRE_HASH=$($VPS_SSH \
  "docker exec flowmanner-frontend ls -t /app/.next/static/chunks/*.js 2>/dev/null | head -1 | xargs stat -c%s" 2>/dev/null || echo "N/A")
echo "Pre-deploy largest chunk: $PRE_HASH bytes"

# Deploy ...
bash /opt/flowmanner/deploy-frontend.sh

# Verify chunk changed
POST_HASH=$($VPS_SSH \
  "docker exec flowmanner-frontend ls -t /app/.next/static/chunks/*.js 2>/dev/null | head -1 | xargs stat -c%s" 2>/dev/null)
if [ "$PRE_HASH" = "$POST_HASH" ] && [ "$PRE_HASH" != "N/A" ]; then
  echo "WARNING: Chunk size unchanged — possible stale build"
else
  echo "OK: Chunk changed ($PRE_HASH → $POST_HASH bytes)"
fi

# Verify live chunk via curl (not just container inspection)
curl -sSL --max-time 10 -o /dev/null -w "%{http_code}" https://flowmanner.com/ | grep -qE "^(200|307)$" && echo "OK: frontend live" || echo "FAIL: frontend not responding"
```

---

## C. Backend Deploy

**Source:** `/opt/flowmanner/backend/` (homelab)  
**Image:** `workflows-backend:restored`  
**Duration:** ~2 minutes (build + restart + health)  
**Script:** `/opt/flowmanner/deploy-backend.sh`

### C.1 — Canonical path (use the deploy script)

```bash
# Without migrations (routine code change)
bash /opt/flowmanner/deploy-backend.sh

# With migrations (schema change)
bash /opt/flowmanner/deploy-backend.sh --migrate
```

**What it does:**
1. Pre-deploy health check (`curl localhost:8000/health`)
2. Saves current image as `workflows-backend:backup-current`
3. (Optional) Runs `alembic upgrade head` inside the current container
4. `docker build -t workflows-backend:restored /opt/flowmanner/backend/`
5. `docker compose up -d --no-deps --force-recreate backend`
6. Post-deploy health check with 15 retries at 3s intervals

### C.2 — Dry-run

```bash
bash /opt/flowmanner/deploy-backend.sh --migrate --dry-run
```

### C.3 — Manual path

```bash
# Step 1: Save current image
docker tag workflows-backend:restored workflows-backend:backup-current

# Step 2: Run migrations (if schema changed)
docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend alembic upgrade head

# Step 3: Build + deploy (~2 min, use timeout=300)
docker build -t workflows-backend:restored /opt/flowmanner/backend/ && \
cd /opt/flowmanner && docker compose up -d --no-deps --force-recreate backend

# Step 4: Verify
sleep 10
curl -sf --max-time 10 http://localhost:8000/health && echo "OK" || echo "FAIL"
```

**Warning:** After a backend rebuild, the `celery-worker` and `celery-beat` containers are **NOT** restarted automatically (they use `${BACKEND_IMAGE:-workflows-backend:restored}`). If your changes affect Celery tasks, restart them too:

```bash
cd /opt/flowmanner && docker compose up -d --no-deps --force-recreate celery-worker celery-beat
```

### C.4 — Alembic safety

```bash
# Before deploying, check the migration state
docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend alembic current

# If multiple heads exist, create a merge migration FIRST
docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend alembic heads

# After deploy, confirm migration was applied
docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend alembic current
```

---

## D. Verification Matrix

Run these checks post-deploy.  All must pass before declaring success.

First define the VPS_SSH alias:

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"
```

| # | Endpoint / Check | Command | Success | If fail |
|---|-----------------|---------|---------|---------|
| V1 | Backend health (homelab) | `curl -sf --max-time 10 http://localhost:8000/health` | HTTP 200 | Check `docker logs backend --tail 30` |
| V2 | Backend health via VPS proxy | `$VPS_SSH "curl -s --max-time 10 -o /dev/null -w '%{http_code}' http://localhost/api/health"` | `200` | WireGuard issue or backend deadlocked |
| V3 | Frontend homepage | `$VPS_SSH "curl -sSL --max-time 15 -o /dev/null -w '%{http_code}' https://flowmanner.com/"` | `200` or `307` | Check nginx config, frontend container |
| V4 | Auth redirect | `$VPS_SSH "curl -sSL --max-time 15 -o /dev/null -w '%{http_code}' https://flowmanner.com/en/dashboard"` | `200` or `307` | Auth middleware or NextAuth issue |
| V5 | API v2 missions (auth-gated) | `$VPS_SSH "curl -s --max-time 10 -o /dev/null -w '%{http_code}' http://localhost/api/v2/missions"` | `200`, `401`, or `307` — any means backend is reachable | Backend route not registered or auth broken |
| V6 | API v2 envelope shape | `$VPS_SSH "curl -s --max-time 10 http://localhost/api/v2/health | grep -q '\"data\"' && grep -q '\"meta\"' && grep -q '\"error\"' && echo OK"` | Prints `OK` | Envelope contract broken |
| V7 | Websocket upgrade | `$VPS_SSH "curl -sI --max-time 5 -H 'Upgrade: websocket' -H 'Connection: Upgrade' https://flowmanner.com/ws | head -1"` | HTTP 101 or 426 | WebSocket proxy broken |
| V8 | Container health (homelab) | `docker ps --filter "health=unhealthy" -q` | Empty output | Unhealthy container — check `docker inspect` |
| V9 | Container health (VPS) | `$VPS_SSH "cd /opt/flowmanner && docker compose ps --format json" | grep -cvE '"healthy"|"running"'` | `0` (no unhealthy containers) | Unhealthy VPS container |
| V10 | Database connectivity | `docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend python -c "import asyncio;from app.database import engine;asyncio.run(engine.connect())" 2>&1` | No error output | Database down or connection pool exhausted |

### API v2 Envelope Expectations

```
Success:  { "data": <payload>, "meta": { "request_id": "...", "timestamp": "..." }, "error": null }
Paginated: { "data": { "items": [...], "total": N, "page": N, "per_page": N, "pages": N }, "meta": {...}, "error": null }
Error:    { "data": null, "error": { "code": "...", "message": "...", "details": {...} }, "meta": {...} }
```

**Auth-gated endpoints:** HTTP 401 or 307 (redirected to login) is **HEALTHY** — it means the backend is reachable and auth is enforced.

### Frontend Stale-Build Detection

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"

# Container-only check (necessary but not sufficient)
$VPS_SSH "docker exec flowmanner-frontend ls -la /app/.next/static/chunks/ | tail -5"

# Live check (authoritative): pull the HTML page, extract the build-id, compare against known
curl -sSL https://flowmanner.com/ | grep -oP '__NEXT_DATA__.*?"buildId":"\K[^"]+' || echo "No buildId found"
```

---

## E. Rollback Matrix

First define VPS_SSH:

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"
```

### E.1 — Frontend Rollback

| Step | Command | Expected output | Time |
|------|---------|-----------------|------|
| 1. Verify backup exists | `$VPS_SSH "docker image inspect flowmanner-frontend:backup-current >/dev/null 2>&1 && echo EXISTS \|\| echo MISSING"` | `EXISTS` | 2s |
| 2. Execute rollback | `bash /opt/flowmanner/deploy-frontend.sh --rollback` | `Rollback completed successfully` | 60s |
| 3. Verify | See [D. Verification Matrix](#d-verification-matrix) checks V3-V4 | All pass | 30s |

### E.2 — Backend Rollback

| Step | Command | Expected output | Time |
|------|---------|-----------------|------|
| 1. Verify backup exists | `docker image inspect workflows-backend:backup-current >/dev/null 2>&1 && echo EXISTS \|\| echo MISSING` | `EXISTS` | 1s |
| 2. Execute rollback | `bash /opt/flowmanner/deploy-backend.sh --rollback` | `Backend rollback completed successfully` | 30s |
| 3. Verify | See [D. Verification Matrix](#d-verification-matrix) checks V1-V2,V8,V10 | All pass | 30s |

### E.3 — Fast Rollback Under 5 Minutes (Manual)

If the script-based rollback fails or you need to bypass health checks:

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"

# FRONTEND — fastest path (~2 min)
$VPS_SSH "docker tag flowmanner-frontend:backup-current flowmanner-frontend:latest && \
   cd /opt/flowmanner && docker compose up -d --no-deps frontend && \
   docker compose restart nginx"

# BACKEND — fastest path (~90 sec)
docker tag workflows-backend:backup-current workflows-backend:restored && \
cd /opt/flowmanner && docker compose up -d --no-deps --force-recreate backend celery-worker celery-beat
```

### E.4 — Rollback Verification

```bash
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"

# Combined rollback health check (copy/paste)
echo "=== Rollback Verification ==="
curl -sf --max-time 10 http://localhost:8000/health && echo "✓ backend" || echo "✗ backend"
$VPS_SSH "curl -sSL --max-time 15 -o /dev/null -w '%{http_code}' https://flowmanner.com/" | grep -qE "^(200|307)$" && echo "✓ frontend" || echo "✗ frontend"
```

---

## F. Cutover GO/NO-GO Checklist

Complete this checklist **before** starting a deploy and **after** finishing verification.

### Pre-Deploy GO/NO-GO

| # | Check | GO if | NO-GO if |
|---|-------|-------|----------|
| F1 | All preflight checks pass (Section A) | All 10 pass | Any check fails and cannot be resolved within 5 min |
| F2 | Someone is available for rollback if deploy fails | At least 1 engineer online | No one else available — defer deploy |
| F3 | No in-flight critical database operations | Run: `docker compose -f /opt/flowmanner/docker-compose.yml exec -T postgres psql -U flowmanner -d flowmanner -c "SELECT count(*) FROM pg_stat_activity WHERE state='active' AND query NOT LIKE '%pg_stat_activity%'" -t` — output is < 20 | Heavy DB activity — wait for quiet period |
| F4 | Git working tree clean | `git -C /opt/flowmanner/backend status --porcelain` is empty | Uncommitted changes — commit or stash first |
| F5 | Tests pass locally | `cd /opt/flowmanner/backend && python -m pytest -q` — 0 failures | Fix tests before deploying |
| F6 | Deploy window open | Between 09:00-17:00 UTC | Outside hours — assess risk, get manager sign-off |
| F7 | Notification sent to team | Slack/Teams message sent | Team unaware — send notification first |

### Post-Deploy GO/NO-GO

| # | Check | GO if | NO-GO if |
|---|-------|-------|----------|
| F8 | All verification checks pass (Section D) | All 10 pass | Any check fails — initiate rollback |
| F9 | Error rate unchanged in logs | `docker logs backend --since 2m 2>&1 | grep -c ERROR` < 5 | Spike in errors — investigate, consider rollback |
| F10 | Health endpoint latency < 500ms | `curl -s -o /dev/null -w '%{time_total}' http://localhost:8000/health` < 0.5 | Slow response — may indicate resource exhaustion |
| F11 | 5 minutes of stable operation | No alerts fired | Any alert during cooldown — investigate root cause |
| F12 | Team confirmation | Announcement sent (Section G) | Skip if 2+ NO-GO items above |

---

## G. Team Announcement Template

Copy and paste into Slack/Teams/Discord after a successful deploy.

```
:rocket: **FlowManner Deploy — $(date +%Y-%m-%d)**

**Deployed by:** @YOURNAME
**Duration:** ~4 min frontend / ~2 min backend
**Type:** [routine / hotfix / schema-migration / rollback]

**Changes:**
- [list 2-3 bullet points of what changed]

**Verification:** All 10 verification gates passed
  :white_check_mark: Backend health
  :white_check_mark: Frontend homepage
  :white_check_mark: API v2 envelope
  :white_check_mark: Database connectivity
  :white_check_mark: No error spike

**Rollback available:** `flowmanner-frontend:backup-current` / `workflows-backend:backup-current`
**Rollback command:** `bash /opt/flowmanner/deploy-backend.sh --rollback`

:eyes: **Please report any issues within the next 15 minutes.**
```

---

## Single-Shot Command List (Experienced Operators)

Copy/paste these blocks in order.  Each block is self-contained.

```bash
# ═══════════════════════════════════════════════════════════════════
# PREFLIGHT
# ═══════════════════════════════════════════════════════════════════
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"
echo "=== PREFLIGHT ===" && \
docker ps --filter name=backend --filter status=running -q | grep -q . && echo "✓ backend" || exit 1 && \
curl -sf --max-time 10 http://localhost:8000/health >/dev/null && echo "✓ health" || exit 1 && \
docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend alembic current 2>/dev/null | head -1 && \
sudo wg show wg0 | grep -q "latest handshake" && echo "✓ wireguard" || exit 1 && \
$VPS_SSH "echo ✓ vps-up"

echo "Preflight OK — proceed"
```

```bash
# ═══════════════════════════════════════════════════════════════════
# BACKEND DEPLOY (with migrations)
# ═══════════════════════════════════════════════════════════════════
bash /opt/flowmanner/deploy-backend.sh --migrate || bash /opt/flowmanner/deploy-backend.sh --rollback
```

```bash
# ═══════════════════════════════════════════════════════════════════
# FRONTEND DEPLOY
# ═══════════════════════════════════════════════════════════════════
bash /opt/flowmanner/deploy-frontend.sh || bash /opt/flowmanner/deploy-frontend.sh --rollback
```

```bash
# ═══════════════════════════════════════════════════════════════════
# POST-DEPLOY VERIFICATION
# ═══════════════════════════════════════════════════════════════════
VPS_SSH="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142"
echo "=== VERIFICATION ===" && \
curl -sf --max-time 10 http://localhost:8000/health >/dev/null && echo "✓ backend-local" || echo "✗ backend-local" && \
$VPS_SSH "curl -s --max-time 10 -o /dev/null -w '%{http_code}' http://localhost/api/health" | grep -q 200 && echo "✓ backend-vps" || echo "✗ backend-vps" && \
$VPS_SSH "curl -sSL --max-time 15 -o /dev/null -w '%{http_code}' https://flowmanner.com/" | grep -qE "^(200|307)$" && echo "✓ frontend" || echo "✗ frontend" && \
docker ps --filter "health=unhealthy" -q | grep -q . && echo "✗ unhealthy-containers" || echo "✓ all-healthy"
```

```bash
# ═══════════════════════════════════════════════════════════════════
# FAST ROLLBACK (if verification fails)
# ═══════════════════════════════════════════════════════════════════
# Choose one:
bash /opt/flowmanner/deploy-backend.sh --rollback     # backend only
bash /opt/flowmanner/deploy-frontend.sh --rollback    # frontend only
# Or both:
bash /opt/flowmanner/deploy-backend.sh --rollback && bash /opt/flowmanner/deploy-frontend.sh --rollback
```

```bash
# ═══════════════════════════════════════════════════════════════════
# ANNOUNCEMENT
# ═══════════════════════════════════════════════════════════════════
cat <<'EOF'
:rocket: FlowManner Deploy Complete — All gates green, rollback tagged as backup-current.
:eyes: Report issues in #eng-alerts within 15 min.
EOF
```
