#!/bin/bash
# Flowmanner PostgreSQL Daily Backup (QW2-pgdump)
# Dumps the flowmanner database from the workflow-postgres container to
# /var/backups/flowmanner/pg/ with a date-stamped filename, verifies the
# dump, and enforces 7-day retention. Designed to run from cron at 03:00 UTC.
#
# Crontab entry (already installed by QW2-pgdump):
#   0 3 * * * /opt/flowmanner/scripts/backup_pg.sh
#
# Manual run:    bash /opt/flowmanner/scripts/backup_pg.sh
# Restore:       pg_restore -U flowmanner -d flowmanner --clean --if-exists \
#                /var/backups/flowmanner/pg/flowmanner_YYYYMMDD_HHMMSS.dump
#
# Configuration via env:
#   PG_CONTAINER   default: workflow-postgres
#   PG_USER         default: flowmanner
#   PG_DB           default: flowmanner
#   BACKUP_DIR      default: /var/backups/flowmanner/pg
#                   (falls back to /opt/flowmanner/backups/pg if the canonical
#                    path is not writable by the current user — common on
#                    homelabs where /var/backups/ requires root to create)
#   LOG_FILE        default: $BACKUP_DIR/backup.log
#   RETAIN_DAYS     default: 7
#
# NOTE: The existing /opt/flowmanner/scripts/backup-db.sh also dumps Postgres
# (to /opt/flowmanner/backups/postgres/). This script is a separate, dedicated
# daily dump to /var/backups/flowmanner/pg/ with simpler retention and a
# location that survives FlowManner repo wipes.

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────
PG_CONTAINER="${PG_CONTAINER:-workflow-postgres}"
PG_USER="${PG_USER:-flowmanner}"
PG_DB="${PG_DB:-flowmanner}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"

# ─── Resolve BACKUP_DIR (try canonical, fall back if not writable) ────────
CANONICAL_BACKUP_DIR="/var/backups/flowmanner/pg"
FALLBACK_BACKUP_DIR="/opt/flowmanner/backups/pg"
if [[ -z "${BACKUP_DIR:-}" ]]; then
    if mkdir -p "$CANONICAL_BACKUP_DIR" 2>/dev/null \
        && [[ -w "$CANONICAL_BACKUP_DIR" ]]; then
        BACKUP_DIR="$CANONICAL_BACKUP_DIR"
    else
        # Canonical path not creatable / not writable. Fall back so the
        # cron entry actually produces a dump on boxes where /var/backups/
        # is root-owned (e.g. this homelab). Log a clear warning.
        BACKUP_DIR="$FALLBACK_BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [backup_pg] [warn] Canonical dir $CANONICAL_BACKUP_DIR not writable; falling back to $BACKUP_DIR" >&2
    fi
fi
LOG_FILE="${LOG_FILE:-${BACKUP_DIR}/backup.log}"

mkdir -p "$(dirname "$LOG_FILE")"

log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [backup_pg] $*" | tee -a "$LOG_FILE" ; }
err()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [backup_pg] [error] $*" | tee -a "$LOG_FILE" >&2 ; }

log "Backup dir: $BACKUP_DIR"

# ─── Pre-flight: container reachable ──────────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    err "Postgres container '$PG_CONTAINER' is not running. Aborting."
    exit 1
fi

# ─── Dump ─────────────────────────────────────────────────────────────────
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
DUMP_FILE="${BACKUP_DIR}/flowmanner_${TIMESTAMP}.dump"

log "Starting pg_dump of '${PG_DB}' from container '${PG_CONTAINER}'"
log "Output: ${DUMP_FILE}"

if ! docker exec "$PG_CONTAINER" \
        pg_dump \
            -U "$PG_USER" \
            -d "$PG_DB" \
            --format=custom \
            --compress=9 \
            --no-owner \
            --no-acl \
        > "$DUMP_FILE" 2>>"$LOG_FILE"; then
    err "pg_dump failed. Removing partial dump: $DUMP_FILE"
    rm -f "$DUMP_FILE"
    exit 1
fi

DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
log "Dump created: $DUMP_FILE ($DUMP_SIZE)"

# ─── Integrity check: pg_restore --list ───────────────────────────────────
if pg_restore --list "$DUMP_FILE" > /dev/null 2>>"$LOG_FILE"; then
    log "Integrity check: pg_restore --list OK"
else
    err "Integrity check FAILED — dump may be corrupt. File left in place for inspection."
    exit 1
fi

# ─── Retention: delete dumps older than RETAIN_DAYS ───────────────────────
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'flowmanner_*.dump' \
            -mtime +"$RETAIN_DAYS" -print -delete | wc -l)
log "Retention: deleted $DELETED dump(s) older than ${RETAIN_DAYS} days"

REMAINING=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'flowmanner_*.dump' | wc -l)
log "Done. $REMAINING dump(s) retained in $BACKUP_DIR"
