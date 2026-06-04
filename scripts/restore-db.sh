#!/bin/bash
# Flowmanner Database Restore Script
# Restores from PostgreSQL backup
# Usage: ./restore-db.sh <backup_file>

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[restore]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
err() { echo -e "${RED}[error]${NC} $1" >&2; }

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <backup_file>"
    echo ""
    echo "Available backups:"
    ls -lh /opt/flowmanner/backups/postgres/ 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "$BACKUP_FILE" ]]; then
    err "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Safety confirmation
warn "This will OVERWRITE the current flowmanner database!"
read -p "Are you sure? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    log "Aborted."
    exit 0
fi

# Stop backend to prevent connections
log "Stopping backend..."
docker stop backend 2>/dev/null || true

# Drop and recreate database
log "Recreating database..."
docker exec workflow-postgres psql -U flowmanner -d postgres -c "
    SELECT pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = 'flowmanner' AND pid <> pg_backend_pid();
" 2>/dev/null || true

docker exec workflow-postgres psql -U flowmanner -d postgres -c "
    DROP DATABASE IF EXISTS flowmanner;
    CREATE DATABASE flowmanner OWNER flowmanner;
" 2>/dev/null

# Restore
log "Restoring from $BACKUP_FILE..."
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gunzip -c "$BACKUP_FILE" | docker exec -i workflow-postgres pg_restore \
        -U flowmanner \
        -d flowmanner \
        --verbose \
        --no-owner \
        --no-privileges \
        2>/dev/null || true
else
    cat "$BACKUP_FILE" | docker exec -i workflow-postgres pg_restore \
        -U flowmanner \
        -d flowmanner \
        --verbose \
        --no-owner \
        --no-privileges \
        2>/dev/null || true
fi

# Verify
TABLE_COUNT=$(docker exec workflow-postgres psql -U flowmanner -d flowmanner -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')

log "Restored $TABLE_COUNT tables"

# Restart backend
log "Starting backend..."
docker start backend

# Health check
sleep 5
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    log "Backend health check: PASS"
else
    warn "Backend health check: FAIL (may need time to start)"
fi

log "=== Restore Complete ==="
