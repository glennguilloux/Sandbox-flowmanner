# Flowmanner — Ops/Dev Machine Agent Instructions

## ⚠️ YOU ARE ON THE OPS/DEV MACHINE

This machine is the **ops/dev workstation** at `172.16.1.2`.

You are NOT on the homelab and NOT on the VPS. You reach both via SSH.

## Role

This machine is used for **triggering deployments** and **development work** on the Flowmanner frontend. It does NOT host any services — it's a thin client that:
- SSHs into the homelab to kick off deploys
- Edits frontend source code (if checked out locally)
- Runs tests and checks

## Architecture

```
Ops Machine (172.16.1.2)
    │
    │  SSH (key auth, user: glenn)
    ▼
Homelab (172.16.1.1)
    │  Runs: deploy-frontend.sh
    │  - rsyncs /home/glenn/FlowmannerV2-frontend/ to VPS
    │  - triggers docker compose build on VPS
    │  - health checks
    │
    │  SSH (key auth, user: root)
    ▼
VPS (74.208.115.142)
    └─ flowmanner.com (Next.js via Nginx)
```

## Paths

| What | Path | Notes |
|------|------|-------|
| Remote deploy trigger | `/opt/flowmanner/deploy-frontend-remote.sh` | Run this to deploy |
| (on homelab) Deploy script | `/opt/flowmanner/deploy-frontend.sh` | The actual deploy logic |
| (on homelab) Frontend source | `/home/glenn/FlowmannerV2-frontend/` | Edit before deploying |

## SSH Access

```bash
# To homelab (passwordless key auth required)
ssh glenn@172.16.1.1

# To VPS (via homelab, or directly if WireGuard is up)
# From homelab: ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142
```

**To set up SSH key to homelab (one-time):**
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id glenn@172.16.1.1
```

## Editing Frontend Source

Frontend source lives on the **homelab** at `/home/glenn/FlowmannerV2-frontend/`. There are two workflows:

**A) Edit directly on homelab (recommended):**
```bash
ssh glenn@172.16.1.1
cd /home/glenn/FlowmannerV2-frontend
# edit files, then deploy with:
bash /opt/flowmanner/deploy-frontend.sh
```

**B) Edit on this machine, then push to homelab:**
```bash
# After editing locally, rsync to homelab:
rsync -avz --exclude node_modules --exclude .next --exclude .git \
  /path/to/your/FlowmannerV2-frontend/ \
  glenn@172.16.1.1:/home/glenn/FlowmannerV2-frontend/

# Then deploy from homelab:
bash /opt/flowmanner/deploy-frontend-remote.sh
```

## Deploy Frontend

```bash
# Full deploy (~4 minutes — rsync + docker build + health checks)
bash /opt/flowmanner/deploy-frontend-remote.sh

# Dry-run (no changes made, just previews what would happen)
bash /opt/flowmanner/deploy-frontend-remote.sh --dry-run

# Rollback to previous frontend version
bash /opt/flowmanner/deploy-frontend-remote.sh --rollback
```

**What happens during deploy:**
1. Pre-deploy health check (checks current frontend is healthy as baseline)
2. Backs up current frontend image for rollback
3. Rsyncs source from homelab to VPS (~30s)
4. `docker compose build frontend` on VPS (~2 min)
5. `docker compose up -d --no-deps frontend` + nginx restart (~30s)
6. Post-deploy health check (10 retries × 5s = up to 50s)

**If deploy times out or fails:**
- Do NOT retry blindly — the deploy may have completed but the SSH session died
- Check VPS container status from homelab:
  ```bash
  ssh glenn@172.16.1.1 "ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 'cd /opt/flowmanner && docker compose ps'"
  ```
- Auto-rollback runs on failure — check the deploy output

## Check Status

```bash
# Check if homelab is reachable
ssh -o ConnectTimeout=5 glenn@172.16.1.1 "echo ok"

# Check if VPS is reachable (from homelab)
ssh glenn@172.16.1.1 "ssh -i ~/.ssh/vps_flowmanner_new -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new root@74.208.115.142 'echo ok'"

# Check frontend is serving
curl -s -o /dev/null -w "%{http_code}" https://flowmanner.com
# Should return 200
```

## Troubleshooting

| Problem | Check |
|---------|-------|
| Can't reach homelab | `ssh glenn@172.16.1.1` — check network, SSH key |
| Deploy script not found | The script lives at `/opt/flowmanner/deploy-frontend-remote.sh` on THIS machine. If missing, copy it from homelab: `scp glenn@172.16.1.1:/opt/flowmanner/deploy-frontend-remote.sh /opt/flowmanner/` |
| Deploy hangs indefinitely | The homelab's deploy script may have issues. SSH to homelab and check: `ssh glenn@172.16.1.1` then `docker compose ps` on VPS. The deploy-frontend.sh was recently fixed with proper timeout guards — make sure you have the latest version. |
| Permission denied (docker) | The `glenn` user on homelab must be in the `docker` group for `deploy-frontend.sh` to run `docker compose` commands on VPS remotely |
| Frontend not updating | Check that the frontend source at `/home/glenn/FlowmannerV2-frontend/` on homelab has your latest changes before deploying |
