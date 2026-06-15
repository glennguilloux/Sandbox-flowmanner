# FlowManner Disaster Recovery

If the homelab SSD dies, this is how to bring FlowManner back from a backup
in `/mnt/apps/Flowmanner-Backups/latest/`.

## 0. What you need first

- Fresh homelab install (or a replacement Linux box)
- A copy of the GitHub repos (already pushed):
  - `git clone https://github.com/glennguilloux/flowmanner.git /opt/flowmanner`
  - `git clone https://github.com/glennguilloux/flowmanner.git /home/glenn/FlowmannerV2-frontend`
- The latest backup directory: `/mnt/apps/Flowmanner-Backups/latest/` (or
  any dated subdir)
- WireGuard keys for the homelab<->VPS tunnel (in the backup under `ssh/`)

## 1. Restore secrets

```bash
sudo cp /mnt/apps/Flowmanner-Backups/latest/env/root.env /opt/flowmanner/.env
sudo cp /mnt/apps/Flowmanner-Backups/latest/env/backend.env /opt/flowmanner/backend/.env
sudo cp /mnt/apps/Flowmanner-Backups/latest/env/sandboxd.env /mnt/apps/Softwares2/sandboxd/.env
chmod 600 /opt/flowmanner/.env /opt/flowmanner/backend/.env /mnt/apps/Softwares2/sandboxd/.env
```

## 2. Restore SSH keys

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cp /mnt/apps/Flowmanner-Backups/latest/ssh/* ~/.ssh/
chmod 600 ~/.ssh/vps_flowmanner_new ~/.ssh/id_rsa ~/.ssh/id_ed25519 ~/.ssh/config
chmod 644 ~/.ssh/known_hosts
```

## 3. Start the docker stack

```bash
cd /opt/flowmanner
docker compose up -d postgres redis rabbitmq qdrant
# Wait for postgres to be healthy
docker compose exec -T postgres pg_isready -U flowmanner
```

## 4. Restore PostgreSQL

```bash
# Find the dump file (date-stamped)
ls /mnt/apps/Flowmanner-Backups/latest/postgres/
DUMP=$(ls /mnt/apps/Flowmanner-Backups/latest/postgres/*.sql.gz | head -1)

# Drop and recreate the DB to ensure clean restore
docker compose exec -T postgres psql -U flowmanner -d postgres \
  -c "DROP DATABASE flowmanner;"
docker compose exec -T postgres psql -U flowmanner -d postgres \
  -c "CREATE DATABASE flowmanner;"

# Restore
gunzip -c "$DUMP" | docker compose exec -T postgres psql -U flowmanner -d flowmanner
```

## 5. Restore the data volumes

```bash
# Uploads
docker run --rm \
  -v flowmanner_uploads_data:/to \
  -v /mnt/apps/Flowmanner-Backups/latest/uploads:/from \
  alpine sh -c "tar xzf /from/uploads-*.tgz -C /to"

# Qdrant
docker run --rm \
  -v flowmanner_qdrant_data:/to \
  -v /mnt/apps/Flowmanner-Backups/latest/qdrant:/from \
  alpine sh -c "tar xzf /from/qdrant-*.tgz -C /to"

# Redis (optional — sessions can be re-established)
docker run --rm \
  -v flowmanner_redis_data:/to \
  -v /mnt/apps/Flowmanner-Backups/latest/redis:/from \
  alpine sh -c "tar xzf /from/redis-*.tgz -C /to"

# RabbitMQ (optional — pending tasks will be lost anyway)
docker run --rm \
  -v flowmanner_rabbitmq_data:/to \
  -v /mnt/apps/Flowmanner-Backups/latest/rabbitmq:/from \
  alpine sh -c "tar xzf /from/rabbitmq-*.tgz -C /to"
```

## 6. Run migrations

```bash
cd /opt/flowmanner
docker compose exec -T backend alembic upgrade head
```

## 7. Build and start the backend

```bash
cd /opt/flowmanner
docker build -t workflows-backend:restored backend/
docker compose up -d backend celery-worker celery-beat
curl http://127.0.0.1:8000/api/health
```

## 8. (Re)deploy the frontend to the VPS

```bash
bash /opt/flowmanner/deploy-frontend.sh
```

## 9. Restore IONOS firewall + WireGuard + cron

These are NOT backed up by the script (they live in IONOS web UI and
`/etc/wireguard/` + crontab). You'll need to:

- Re-add WireGuard peer in VPS IONOS panel
- Restore `/etc/wireguard/wg0.conf` on the homelab (from your notes)
- Restore crontab: `crontab -e` and re-add any backup-cron lines
- Restore IONOS firewall inbound rules (ports 22, 80, 443, 51820, 8443)
- Restore the systemd llama-server service if you used it

## What the backup script does NOT cover (intentional)

- IONOS firewall rules (web UI only)
- WireGuard keys (in IONOS panel + VPS /etc/wireguard)
- systemd service files
- Docker named-volume definitions (in docker-compose.yml, which IS in git)
- LLM model weights on the llama.cpp host
- The 4c8bec6, 9457948 etc. commit history (covered by git push)
