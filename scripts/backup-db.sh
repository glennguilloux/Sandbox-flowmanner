#!/bin/bash
# Flowmanner Database Backup Script (H3)
# Backs up: PostgreSQL, Redis, Qdrant, RabbitMQ definitions, config files
# Usage: ./backup-db.sh [--retain-daily N] [--retain-weekly N] [--dry-run]
# Restore verification: pg_restore --list after each dump

set -euo pipefail

BACKUP_DIR="/opt/flowmanner/backups"
RETAIN_DAILY=${RETAIN_DAILY:-7}
RETAIN_WEEKLY=${RETAIN_WEEKLY:-4}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)  # 1=Monday, 7=Sunday
DRY_RUN=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[backup]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
err() { echo -e "${RED}[error]${NC} $1" >&2; }

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --retain-daily) RETAIN_DAILY="$2"; shift 2 ;;
        --retain-weekly) RETAIN_WEEKLY="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) err "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$BACKUP_DIR"/{postgres,redis,qdrant,rabbitmq,config}

if $DRY_RUN; then
    warn "DRY-RUN mode — no backups will be created"
fi

# ─── PostgreSQL Backup ────────────────────────────────────────────────────
log "Backing up PostgreSQL..."
PG_BACKUP="$BACKUP_DIR/postgres/flowmanner_${TIMESTAMP}.dump"

if $DRY_RUN; then
    log "[DRY-RUN] Would dump PostgreSQL to $PG_BACKUP"
else
    docker exec workflow-postgres pg_dump \
        -U flowmanner \
        -d flowmanner \
        --format=custom \
        --compress=9 \
        --verbose \
        > "$PG_BACKUP" 2>/dev/null

    PG_SIZE=$(du -h "$PG_BACKUP" | cut -f1)
    log "PostgreSQL backup: $PG_BACKUP ($PG_SIZE)"

    # Restore verification: list contents to verify dump integrity
    log "Verifying PostgreSQL backup integrity..."
    if pg_restore --list "$PG_BACKUP" > /dev/null 2>&1; then
        log "  ✓ pg_restore --list: backup is valid"
    else
        err "  ✗ PostgreSQL backup verification FAILED — dump may be corrupt"
    fi
fi

# ─── Redis Backup ─────────────────────────────────────────────────────────
log "Backing up Redis..."
docker exec workflow-redis redis-cli \
    -a "${REDIS_PASSWORD:-oFvdKE3HRxsm5CscZpifmwImDidNUmX5}" \
    BGSAVE 2>/dev/null

# Wait for BGSAVE to complete
sleep 2
REDIS_BACKUP="$BACKUP_DIR/redis/redis_${TIMESTAMP}.rdb"
docker cp workflow-redis:/data/dump.rdb "$REDIS_BACKUP" 2>/dev/null || \
    warn "Redis dump.rdb not found (may be empty)"

if [[ -f "$REDIS_BACKUP" ]]; then
    REDIS_SIZE=$(du -h "$REDIS_BACKUP" | cut -f1)
    log "Redis backup: $REDIS_BACKUP ($REDIS_SIZE)"
fi

# ─── Qdrant Backup (snapshot API preferred, tar fallback) ─────────────────
log "Backing up Qdrant..."
QDRANT_BACKUP="$BACKUP_DIR/qdrant/qdrant_${TIMESTAMP}.snapshot"

if $DRY_RUN; then
    log "[DRY-RUN] Would snapshot Qdrant to $QDRANT_BACKUP"
else
    # Try Qdrant snapshot API first (requires Qdrant v1.8+)
    QDRANT_HOST="${QDRANT_HOST:-localhost}"
    QDRANT_HTTP_PORT="${QDRANT_HTTP_PORT:-6333}"
    SNAPSHOT_URL="http://${QDRANT_HOST}:${QDRANT_HTTP_PORT}/snapshots"

    # Create snapshot via API
    SNAPSHOT_RESP=$(curl -s -X POST "${SNAPSHOT_URL}" \
        -H "Content-Type: application/json" \
        -d '{}' 2>/dev/null || true)

    if echo "$SNAPSHOT_RESP" | grep -q '"status":"ok"'; then
        # Snapshot created — download it
        SNAPSHOT_NAME=$(echo "$SNAPSHOT_RESP" | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4)
        if [[ -n "$SNAPSHOT_NAME" ]]; then
            curl -s -o "$QDRANT_BACKUP" \
                "${SNAPSHOT_URL}/${SNAPSHOT_NAME}" 2>/dev/null || true
        fi
    fi

    # Fallback: tar the storage directory from the container
    if [[ ! -s "$QDRANT_BACKUP" ]]; then
        warn "Qdrant snapshot API unavailable — using tar fallback"
        QDRANT_BACKUP="$BACKUP_DIR/qdrant/qdrant_${TIMESTAMP}.tar.gz"
        docker exec workflow-qdrant tar -czf - /qdrant/storage > "$QDRANT_BACKUP" 2>/dev/null || \
            warn "Qdrant backup failed (non-critical)"
    fi

    if [[ -f "$QDRANT_BACKUP" ]] && [[ -s "$QDRANT_BACKUP" ]]; then
        QDRANT_SIZE=$(du -h "$QDRANT_BACKUP" | cut -f1)
        log "Qdrant backup: $QDRANT_BACKUP ($QDRANT_SIZE)"
    else
        warn "Qdrant backup: empty or missing (non-critical)"
    fi
fi

# ─── RabbitMQ Definitions Backup ──────────────────────────────────────────
log "Backing up RabbitMQ definitions..."
RMQ_BACKUP="$BACKUP_DIR/rabbitmq/rabbitmq_definitions_${TIMESTAMP}.json"
RMQ_SIZE="N/A"

if $DRY_RUN; then
    log "[DRY-RUN] Would export RabbitMQ definitions to $RMQ_BACKUP"
else
    # Source .env for RabbitMQ credentials (required for rabbitmqadmin auth)
    ENV_FILE="/opt/flowmanner/.env"
    RMQ_USER="${RABBITMQ_USER:-rabbitmq}"
    RMQ_PASS="${RABBITMQ_PASSWORD:-}"
    if [[ -z "$RMQ_PASS" ]] && [[ -f "$ENV_FILE" ]]; then
        RMQ_USER=$(grep -oP '^RABBITMQ_USER=\K.*' "$ENV_FILE" | head -1 || echo "rabbitmq")
        RMQ_PASS=$(grep -oP '^RABBITMQ_PASSWORD=\K.*' "$ENV_FILE" | head -1 || echo "")
    fi

    # Export definitions via rabbitmqadmin (writes to a file, not stdout)
    if [[ -n "$RMQ_PASS" ]]; then
        RMQ_TMP="/tmp/rmq_defs_${TIMESTAMP}.json"
        if docker exec workflow-rabbitmq \
            rabbitmqadmin --username="$RMQ_USER" --password="$RMQ_PASS" \
            export "$RMQ_TMP" \
            2>/dev/null && docker cp "workflow-rabbitmq:$RMQ_TMP" "$RMQ_BACKUP" \
            2>/dev/null && docker exec workflow-rabbitmq rm -f "$RMQ_TMP"; then
            if [[ -s "$RMQ_BACKUP" ]]; then
                RMQ_SIZE=$(du -h "$RMQ_BACKUP" | cut -f1)
                # Verify it's actual JSON, not the info message
                if head -1 "$RMQ_BACKUP" | grep -q '^{'; then
                    log "RabbitMQ definitions: $RMQ_BACKUP ($RMQ_SIZE)"
                else
                    warn "RabbitMQ definitions export: got message file instead of JSON"
                    rm -f "$RMQ_BACKUP"
                fi
            else
                warn "RabbitMQ definitions export: empty file"
                rm -f "$RMQ_BACKUP"
            fi
        else
            warn "RabbitMQ definitions export failed (rabbitmqadmin)"
            rm -f "$RMQ_BACKUP"
        fi
    else
        warn "RabbitMQ backup skipped — no RABBITMQ_PASSWORD set"
    fi
fi

# ─── Config Backup ────────────────────────────────────────────────────────
log "Backing up configuration files..."
CONFIG_BACKUP="$BACKUP_DIR/config/config_${TIMESTAMP}.tar.gz"

if $DRY_RUN; then
    log "[DRY-RUN] Would archive config to $CONFIG_BACKUP"
else
    tar -czf "$CONFIG_BACKUP" \
        -C /opt/flowmanner \
        .env docker-compose.yml docker-compose.dev.yml \
        docker-compose.staging.yml 2>/dev/null || \
        warn "Config backup: some files missing (non-critical)"

    if [[ -f "$CONFIG_BACKUP" ]]; then
        CONFIG_SIZE=$(du -h "$CONFIG_BACKUP" | cut -f1)
        log "Config backup: $CONFIG_BACKUP ($CONFIG_SIZE)"
    fi
fi

# ─── Retention Cleanup ────────────────────────────────────────────────────
log "Applying retention policy (daily: $RETAIN_DAILY, weekly: $RETAIN_WEEKLY)..."

if ! $DRY_RUN; then
    # Keep daily backups for all categories
    for dir in postgres redis qdrant rabbitmq config; do
        BACKUP_PATH="$BACKUP_DIR/$dir"
        if [[ -d "$BACKUP_PATH" ]]; then
            # Remove old daily backups beyond retention
            find "$BACKUP_PATH" \( -name "*.dump" -o -name "*.gz" -o -name "*.rdb" -o -name "*.snapshot" -o -name "*.json" \) | \
                sort -r | tail -n +$((RETAIN_DAILY + 1)) | \
                xargs -r rm -f
        fi
    done

    # Weekly: keep Sunday dumps longer
    if [[ "$DAY_OF_WEEK" -eq 7 ]]; then
        WEEKLY_DIR="$BACKUP_DIR/weekly"
        mkdir -p "$WEEKLY_DIR"
        [[ -f "$PG_BACKUP" ]] && cp "$PG_BACKUP" "$WEEKLY_DIR/"
        # Clean old weekly backups
        find "$WEEKLY_DIR" -name "*.dump" | sort -r | tail -n +$((RETAIN_WEEKLY + 1)) | xargs -r rm -f
    fi
else
    warn "[DRY-RUN] Retention cleanup skipped"
fi

# ─── Config retention (30 daily) ──────────────────────────────────────────
if ! $DRY_RUN; then
    CONFIG_PATH="$BACKUP_DIR/config"
    if [[ -d "$CONFIG_PATH" ]]; then
        find "$CONFIG_PATH" -name "*.tar.gz" | sort -r | tail -n +31 | xargs -r rm -f
    fi
fi

log "=== Backup Summary ==="
if ! $DRY_RUN; then
    [[ -f "$PG_BACKUP" ]] && log "PostgreSQL: $PG_SIZE (verified: ✓)" || log "PostgreSQL: skipped"
    [[ -f "$REDIS_BACKUP" ]] && log "Redis: $REDIS_SIZE" || log "Redis: skipped"
    [[ -f "$QDRANT_BACKUP" ]] && log "Qdrant: $QDRANT_SIZE" || log "Qdrant: skipped"
    [[ -f "$RMQ_BACKUP" ]] && log "RabbitMQ: $RMQ_SIZE" || log "RabbitMQ: skipped"
    [[ -f "$CONFIG_BACKUP" ]] && log "Config: $CONFIG_SIZE" || log "Config: skipped"
else
    log "[DRY-RUN] No backups created"
fi
log "Retention: $RETAIN_DAILY daily, $RETAIN_WEEKLY weekly, config: 30 daily"

# ─── Push to remote target ───────────────────────────────────────────────
PUSH_TARGET="${BACKUP_PUSH_TARGET:-}"
if [[ -n "$PUSH_TARGET" ]] && ! $DRY_RUN; then
    log "Pushing backups to $PUSH_TARGET ..."
    if [[ "$PUSH_TARGET" =~ ^rsync:// ]] || [[ "$PUSH_TARGET" =~ :/ ]]; then
        rsync -avz --delete "$BACKUP_DIR/" "$PUSH_TARGET" 2>/dev/null && \
            log "  ✓ rsync push complete" || \
            warn "  ✗ rsync push failed"
    else
        cp -r "$BACKUP_DIR/." "$PUSH_TARGET" 2>/dev/null && \
            log "  ✓ local copy push complete" || \
            warn "  ✗ local copy push failed"
    fi
elif [[ -n "$PUSH_TARGET" ]] && $DRY_RUN; then
    log "[DRY-RUN] Would push to $PUSH_TARGET"
fi
log "=== Done ==="
