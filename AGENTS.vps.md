# Flowmanner — VPS Agent Instructions

## ⚠️ YOU ARE ON THE VPS

This machine is the **VPS (IONOS)** at `74.208.115.142` (WireGuard: `10.99.0.1`).

You are NOT on the homelab. The homelab is a SEPARATE machine at `10.99.0.3` — you reach it through the WireGuard tunnel, not locally. Do NOT tell the user to "run commands on the VPS" — you are already here. Do NOT tell the user to "run commands on the homelab" — that is a different machine you cannot directly access beyond the WireGuard tunnel.

## SSH Access

SSH access uses key-based authentication.

**CRITICAL: SSH starts in `/root/`, NOT `/opt/flowmanner/`.** Every `docker compose` command MUST be prefixed with `cd /opt/flowmanner &&`. Without it you get: `no configuration file provided: not found`.

```
# WRONG — will fail
ssh -i ~/.ssh/vps_flowmanner_new root@74.208.115.142 "docker compose ps"

# RIGHT — cd first, then command
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 "cd /opt/flowmanner && docker compose ps"
```

**Prefer the helper scripts instead of raw SSH commands:**

```bash
# Deploy frontend (rsync + rebuild + restart nginx) — RUN FROM HOMELAB
bash /opt/flowmanner/deploy-frontend.sh

# Restart nginx only — RUN FROM HOMELAB OR VPS
bash /opt/flowmanner/frontend/scripts/restart-nginx.sh
```

rsync doesn't need `cd` (it takes absolute paths):
```bash
rsync -avz --progress \
  -e "ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new" \
  /local/path/ root@74.208.115.142:/opt/flowmanner/remote/path/
```

## Deploy Timing (IMPORTANT)

⚠️ **All deploy/build commands take minutes, not seconds.** When running from an AI agent via SSH, use `timeout=300`.

- `docker compose build frontend` → ~2 minutes
- `docker compose up -d` + `docker compose restart nginx` → ~30 seconds
- Full `deploy-frontend.sh` (from homelab) → ~4 minutes

**NEVER retry a timed-out deploy without checking if it already completed.** Use:
```bash
ssh -i ~/.ssh/vps_flowmanner_new root@74.208.115.142 "cd /opt/flowmanner && docker compose ps"
```

## VPS Role

The VPS runs the **public-facing frontend stack**. It proxies API traffic through a WireGuard tunnel to the homelab backend.

```
Internet → Nginx (SSL, :80/:443) → /api/* → 10.99.0.3:8000 (homelab backend)
                                 → /api/auth/* → frontend:3000 (NextAuth)
                                 → /*     → frontend:3000 (Next.js)
                                 → /ws    → ws://10.99.0.3:8000/ws
```

## Services

| Service | Container | Port | Notes |
|---------|-----------|------|-------|
| Nginx | `flowmanner-nginx` | 80, 443 | SSL termination, reverse proxy |
| Next.js | `flowmanner-frontend` | 3000 (internal) | Built from `/opt/flowmanner/frontend/` |
| WireGuard | `wg0` | 51820/udp | Tunnel to homelab (10.99.0.3) |
| Plesk | `sw-cp-serverd` | 8443 | Control panel (Apache disabled) |

## Paths

| What | Path |
|------|------|
| Project root | `/opt/flowmanner/` |
| Frontend source | `/opt/flowmanner/frontend/` |
| Nginx config | `/opt/flowmanner/nginx/default.conf` |
| SSL certs | `/opt/flowmanner/certs/fullchain.pem`, `privkey.pem` |
| Environment | `/opt/flowmanner/.env` |
| Docker Compose | `/opt/flowmanner/docker-compose.yml` |

## Frontend Deployment

**DO NOT edit frontend source on the VPS directly.** Source lives on the homelab at `/home/glenn/FlowmannerV2-frontend/`.

Deployment flow:
1. Edit source on homelab
2. Run `bash /opt/flowmanner/deploy-frontend.sh` from homelab
3. Script rsyncs to VPS, rebuilds Docker image, restarts containers, runs health checks
4. Failed deploys auto-rollback to previous image

If you must manually deploy from the VPS (emergency only):
```bash
cd /opt/flowmanner
docker compose build frontend    # ⚠️ Takes ~2 minutes. Use timeout=300.
docker compose up -d --no-deps frontend
docker compose restart nginx
```

## Nginx Proxy Rules

The nginx config at `/opt/flowmanner/nginx/default.conf` routes:

| Path | Destination |
|------|-------------|
| `/api/auth/*` | `http://frontend:3000/api/auth/` (NextAuth — BEFORE /api/ catch-all) |
| `/api/*` | `http://10.99.0.3:8000/api/` (homelab backend via WireGuard) |
| `/docs`, `/redoc` | `http://10.99.0.3:8000/docs` (API docs) |
| `/ws` | `ws://10.99.0.3:8000/ws` (WebSocket) |
| `/*` | `http://frontend:3000` (Next.js) |

After nginx config changes: `docker compose restart nginx`

## SSL

Let's Encrypt cert at `/opt/flowmanner/certs/`, expires Aug 15, 2026. Auto-renewed via certbot hook at `/etc/letsencrypt/renewal-hooks/deploy/flowmanner.sh` which copies certs and restarts nginx.

## Environment Variables (`/opt/flowmanner/.env`)

- `AUTH_SECRET` — NextAuth v5 secret
- `AUTH_GITHUB_ID` / `AUTH_GITHUB_SECRET` — GitHub OAuth
- `NEXTAUTH_URL` — `https://flowmanner.com`
- `BACKEND_URL` — `http://10.99.0.3:8000`
- `AUTH_TRUST_HOST` — `true`
- `NEXT_PUBLIC_API_URL` — `https://flowmanner.com/api`

## Common Commands

```bash
# Container status
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "cd /opt/flowmanner && docker compose ps"

# Logs
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "docker logs flowmanner-frontend --tail 50"
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "docker logs flowmanner-nginx --tail 50"

# Restart all
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "cd /opt/flowmanner && docker compose restart"

# Backend connectivity (through WireGuard)
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "curl -s http://10.99.0.3:8000/api/health"

# Check WireGuard
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 "wg show"

# Check firewall
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 "ufw status"

# SSL cert expiry
ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "openssl x509 -in /opt/flowmanner/certs/fullchain.pem -noout -dates"
```

## What NOT to Do

- Do NOT edit frontend source on VPS — all edits happen on homelab
- Do NOT use `ssh flowmanner@...` — user doesn't exist on VPS
- Do NOT use `ssh root@74.208.115.142` without the key file — will hang
- Do NOT edit `/etc/apache2/` configs — Apache is disabled, Nginx is the web server
- Do NOT edit Plesk vhost configs in `/var/www/vhosts/` — Plesk is not managing the domain
- Do NOT put backend code on the VPS — it stays on the homelab
- Do NOT expose backend port 8000 publicly — it's only accessible through WireGuard
- Do NOT delete `/opt/flowmanner/certs/` — SSL certs live there
- Do NOT use `docker` commands without `cd /opt/flowmanner` first — compose project is there
- Do NOT run `docker compose build backend` — backend image is built on homelab

## Troubleshooting

| Problem | Check |
|---------|-------|
| Site down | `cd /opt/flowmanner && docker compose ps`, `ufw status` |
| API 502 | `curl http://10.99.0.3:8000/api/health` from VPS, `wg show` |
| API 404 for auth routes | Check nginx config: `/api/auth/` must route to `frontend:3000`, NOT to backend |
| SSL error | `openssl x509 -in /opt/flowmanner/certs/fullchain.pem -noout -dates` |
| Frontend not updating | Rebuild: `cd /opt/flowmanner && docker compose build frontend && docker compose up -d --no-deps frontend && docker compose restart nginx` |
| Deploy/build timed out | Do NOT retry. First check: `cd /opt/flowmanner && docker compose ps` to see if it actually completed. Docker build takes ~2 min; full deploy takes ~4 min. |
| WireGuard down | `wg show` on both sides, `ufw status` (51820/udp must be open) |
