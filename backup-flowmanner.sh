#!/bin/bash
# =============================================================================
# FlowManner Manual Backup Script
# =============================================================================
# Usage:  bash /opt/flowmanner/backup-flowmanner.sh
#         bash /opt/flowmanner/backup-flowmanner.sh --quick   (skip qdrant/redis/rabbit)
#
# Writes a dated, complete backup to /mnt/apps/Flowmanner-Backups/YYYY-MM-DD-HHMMSS/
# Always symlinks /mnt/apps/Flowmanner-Backups/latest to the newest run.
#
# What gets backed up:
#   1. PostgreSQL (flowmanner DB) — pg_dump via the running container
#   2. Uploads volume (user files)
#   3. Backend .env + root .env (DB password, JWT, API keys)
#   4. Sandboxd .env (sandbox token)
#   5. SSH keys (~/.ssh/*)
#   6. Qdrant named volume (semantic memory vectors)
#   7. Redis named volume (sessions, cache, queues metadata)
#   8. RabbitMQ named volume (task queue state)
#
# Restore instructions are at the bottom of this file (also: /opt/flowmanner/RESTORE.md).
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
BACKUP_ROOT="/mnt/apps/Flowmanner-Backups"
COMPOSE_DIR="/opt/flowmanner"
TS=$(date +%Y%m%d-%H%M%S)
DEST="$BACKUP_ROOT/$TS"
LATEST_LINK="$BACKUP_ROOT/latest"
LOG_FILE="$DEST/backup.log"

QUICK_MODE=0
[[ "${1:-}" == "--quick" ]] && QUICK_MODE=1

# Load DB password from .env (single source of truth)
DB_USER=$(grep -E "^POSTGRES_USER=" "$COMPOSE_DIR/.env" | cut -d= -f2)
DB_PASS=$(grep -E "^POSTGRES_PASSWORD=" "$COMPOSE_DIR/.env" | cut -d= -f2)
DB_NAME=$(grep -E "^POSTGRES_DB=" "$COMPOSE_DIR/.env" | cut -d= -f2)

if [[ -z "$DB_USER" || -z "$DB_PASS" || -z "$DB_NAME" ]]; then
  echo "FATAL: could not parse POSTGRES_* from $COMPOSE_DIR/.env"
  exit 1
fi

# ── Setup ───────────────────────────────────────────────────────────────────
mkdir -p "$DEST"/{postgres,uploads,env,ssh,qdrant,redis,rabbitmq,manifest}
exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== FlowManner backup started at $TS ==="
echo "Destination: $DEST"
echo "Mode: $([ $QUICK_MODE -eq 1 ] && echo 'quick (postgres+files+env only)' || echo 'full')"
echo

# ── 1. PostgreSQL dump ───────────────────────────────────────────────────────
echo "[1/8] PostgreSQL dump (database=$DB_NAME, user=$DB_USER)"
docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T postgres \
  pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl --clean --if-exists \
  | gzip > "$DEST/postgres/flowmanner-${TS}.sql.gz"
echo "  → postgres/flowmanner-${TS}.sql.gz ($(du -h "$DEST/postgres/flowmanner-${TS}.sql.gz" | cut -f1))"

# ── 2. Uploads volume ─────────────────────────────────────────────────────────
echo "[2/8] Uploads volume"
docker run --rm \
  -v flowmanner_uploads_data:/from:ro \
  -v "$DEST/uploads":/to \
  alpine sh -c "tar czf /to/uploads-${TS}.tgz -C /from ."
echo "  → uploads/uploads-${TS}.tgz"

# ── 3. Backend .env + root .env ──────────────────────────────────────────────
echo "[3/8] Backend + root .env"
cp "$COMPOSE_DIR/.env" "$DEST/env/root.env"
chmod 600 "$DEST/env/root.env"
cp "$COMPOSE_DIR/backend/.env" "$DEST/env/backend.env" 2>/dev/null || echo "  WARN: backend/.env not found"
chmod 600 "$DEST/env/backend.env" 2>/dev/null || true
echo "  → env/root.env + env/backend.env"

# ── 4. Sandboxd .env ─────────────────────────────────────────────────────────
echo "[4/8] Sandboxd .env"
SBX_ENV="/mnt/apps/Softwares2/sandboxd/.env"
if [[ -f "$SBX_ENV" ]]; then
  cp "$SBX_ENV" "$DEST/env/sandboxd.env"
  chmod 600 "$DEST/env/sandboxd.env"
  echo "  → env/sandboxd.env"
else
  echo "  WARN: $SBX_ENV not found, skipping"
fi

# ── 5. SSH keys ───────────────────────────────────────────────────────────────
echo "[5/8] SSH keys"
for k in ~/.ssh/vps_flowmanner_new ~/.ssh/id_rsa ~/.ssh/id_ed25519 ~/.ssh/config ~/.ssh/known_hosts; do
  if [[ -f "$k" ]]; then
    bn=$(basename "$k")
    cp "$k" "$DEST/ssh/$bn"
    chmod 600 "$DEST/ssh/$bn"
    echo "  → ssh/$bn"
  fi
done

# ── 6. Qdrant (semantic memory vectors) ──────────────────────────────────────
if [[ $QUICK_MODE -eq 0 ]]; then
  echo "[6/8] Qdrant named volume (semantic memory)"
  docker run --rm \
    -v flowmanner_qdrant_data:/from:ro \
    -v "$DEST/qdrant":/to \
    alpine sh -c "tar czf /to/qdrant-${TS}.tgz -C /from ."
  echo "  → qdrant/qdrant-${TS}.tgz"
else
  echo "[6/8] Qdrant SKIPPED (--quick)"
fi

# ── 7. Redis (sessions, cache) ───────────────────────────────────────────────
if [[ $QUICK_MODE -eq 0 ]]; then
  echo "[7/8] Redis named volume"
  docker run --rm \
    -v flowmanner_redis_data:/from:ro \
    -v "$DEST/redis":/to \
    alpine sh -c "tar czf /to/redis-${TS}.tgz -C /from ."
  echo "  → redis/redis-${TS}.tgz"
else
  echo "[7/8] Redis SKIPPED (--quick)"
fi

# ── 8. RabbitMQ (task queue state) ───────────────────────────────────────────
if [[ $QUICK_MODE -eq 0 ]]; then
  echo "[8/8] RabbitMQ named volume"
  docker run --rm \
    -v flowmanner_rabbitmq_data:/from:ro \
    -v "$DEST/rabbitmq":/to \
    alpine sh -c "tar czf /to/rabbitmq-${TS}.tgz -C /from ."
  echo "  → rabbitmq/rabbitmq-${TS}.tgz"
else
  echo "[8/8] RabbitMQ SKIPPED (--quick)"
fi

# ── Manifest (for restore reference) ─────────────────────────────────────────
echo
echo "Writing manifest..."
cat > "$DEST/manifest/info.txt" <<EOF
FlowManner Backup Manifest
==========================
Timestamp:        $TS
Mode:             $([ $QUICK_MODE -eq 1 ] && echo 'quick' || echo 'full')
Source host:      $(hostname 2>/dev/null || echo "unknown")
Docker compose:   $COMPOSE_DIR
Git HEAD (backend):  $(git -C "$COMPOSE_DIR" rev-parse HEAD 2>/dev/null || echo 'unknown')
Git HEAD (frontend): $(git -C /home/glenn/FlowmannerV2-frontend rev-parse HEAD 2>/dev/null || echo 'unknown')
Alembic head:     $(docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T backend alembic current 2>/dev/null | grep -oE '[a-f0-9]{12}' | head -1 || echo 'unknown')

Files in this backup:
$(find "$DEST" -type f -printf '  %P (%s bytes)\n' | sort)

To RESTORE, see:
  cat /opt/flowmanner/RESTORE.md
  or the bottom of /opt/flowmanner/backup-flowmanner.sh
EOF

# Update latest symlink
rm -f "$LATEST_LINK"
ln -s "$DEST" "$LATEST_LINK"

# ── Summary ──────────────────────────────────────────────────────────────────
echo
echo "=== Backup complete ==="
echo "Location: $DEST"
echo "Size:     $(du -sh "$DEST" | cut -f1)"
echo "Latest:   $LATEST_LINK -> $DEST"
echo
echo "To restore from this backup, see: /opt/flowmanner/RESTORE.md"
