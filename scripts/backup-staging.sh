#!/bin/bash
# Flowmanner Staging Backup Script (H3)
# Creates a backup suitable for restoring into staging environment
# Includes: PostgreSQL (plain SQL), config snapshot
# Usage: ./backup-staging.sh [--dry-run]

set -euo pipefail

BACKUP_DIR="/opt/flowmanner/backups/staging"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DRY_RUN=false

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
log() { echo -e "${GREEN}[staging-backup]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$BACKUP_DIR"

if $DRY_RUN; then
    warn "DRY-RUN mode — no backups will be created"
fi

log "Creating staging-ready PostgreSQL dump..."
if $DRY_RUN; then
    log "[DRY-RUN] Would dump PostgreSQL to $BACKUP_DIR/staging_${TIMESTAMP}.sql.gz"
else
    docker exec workflow-postgres pg_dump \
        -U flowmanner \
        -d flowmanner \
        --format=plain \
        --no-owner \
        --no-privileges \
        --clean \
        --if-exists \
        2>/dev/null | gzip > "$BACKUP_DIR/staging_${TIMESTAMP}.sql.gz"

    SIZE=$(du -h "$BACKUP_DIR/staging_${TIMESTAMP}.sql.gz" | cut -f1)
    log "Staging backup: $BACKUP_DIR/staging_${TIMESTAMP}.sql.gz ($SIZE)"

    # Verify the dump is valid SQL
    if zcat "$BACKUP_DIR/staging_${TIMESTAMP}.sql.gz" | head -5 | grep -q "PostgreSQL"; then
        log "  ✓ SQL dump verified (valid PostgreSQL header)"
    else
        warn "  ⚠ SQL header check inconclusive"
    fi
fi

# Keep only last 3 staging backups
if ! $DRY_RUN; then
    find "$BACKUP_DIR" -name "staging_*.sql.gz" | sort -r | tail -n +4 | xargs -r rm -f
fi

log "Done"
