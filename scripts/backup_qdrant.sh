#!/bin/bash
# Flowmanner Qdrant Daily Backup (QW3-qdrant)
# Snapshots every collection in the running Qdrant instance, downloads the
# snapshots to a local backup directory, and enforces 7-day retention.
# Designed to run from cron at 03:30 UTC (30 min after pg_dump so the two
# backups don't fight for I/O).
#
# Crontab entry (install with `crontab -e`):
#   30 3 * * * /opt/flowmanner/scripts/backup_qdrant.sh
#
# Manual run:    bash /opt/flowmanner/scripts/backup_qdrant.sh
# Restore:       Stop Qdrant, replace its storage with the unzipped snapshot,
#                or use Qdrant's /collections/{name}/snapshots/upload to
#                restore into a running cluster.
#
# Configuration via env:
#   QDRANT_URL     default: http://localhost:6333
#                   (the workflow-qdrant container is reachable from cron on
#                    this homelab via localhost because the host port
#                    6333 is published; in a docker-only network use
#                    http://workflow-qdrant:6333)
#   QDRANT_API_KEY default: empty (no auth). If set, sent as `api-key` header.
#   BACKUP_DIR     default: /var/backups/flowmanner/qdrant
#                   (falls back to /opt/flowmanner/backups/qdrant if the
#                    canonical path is not writable by the current user —
#                    common on homelabs where /var/backups/ requires root
#                    to create, same pattern as backup_pg.sh)
#   LOG_FILE       default: $BACKUP_DIR/backup.log
#   RETAIN_DAYS    default: 7
#
# Qdrant API used:
#   GET    /collections                                 → list collections
#   POST   /collections/{name}/snapshots                → create snapshot
#   GET    /collections/{name}/snapshots                → list snapshots
#   GET    /collections/{name}/snapshots/{snap_name}    → download
#   DELETE /collections/{name}/snapshots/{snap_name}    → free Qdrant disk

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_API_KEY="${QDRANT_API_KEY:-}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"

# ─── Resolve BACKUP_DIR (try canonical, fall back if not writable) ────────
CANONICAL_BACKUP_DIR="/var/backups/flowmanner/qdrant"
FALLBACK_BACKUP_DIR="/opt/flowmanner/backups/qdrant"
if [[ -z "${BACKUP_DIR:-}" ]]; then
    if mkdir -p "$CANONICAL_BACKUP_DIR" 2>/dev/null \
        && [[ -w "$CANONICAL_BACKUP_DIR" ]]; then
        BACKUP_DIR="$CANONICAL_BACKUP_DIR"
    else
        # Canonical path not creatable / not writable. Fall back so the
        # cron entry actually produces snapshots on boxes where
        # /var/backups/ is root-owned (e.g. this homelab). Log a clear
        # warning.
        BACKUP_DIR="$FALLBACK_BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [backup_qdrant] [warn] Canonical dir $CANONICAL_BACKUP_DIR not writable; falling back to $BACKUP_DIR" >&2
    fi
fi
LOG_FILE="${LOG_FILE:-${BACKUP_DIR}/backup.log}"

mkdir -p "$(dirname "$LOG_FILE")"

# Tee everything to the log file (append).
log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [backup_qdrant] $*" | tee -a "$LOG_FILE" ; }
err()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [backup_qdrant] [error] $*" | tee -a "$LOG_FILE" >&2 ; }

log "Backup dir: $BACKUP_DIR"
log "Qdrant URL: $QDRANT_URL"

# ─── Build curl auth args (empty if no key) ──────────────────────────────
CURL_AUTH_ARGS=()
if [[ -n "$QDRANT_API_KEY" ]]; then
    CURL_AUTH_ARGS=(-H "api-key: $QDRANT_API_KEY")
fi

# ─── Pre-flight: Qdrant reachable ────────────────────────────────────────
if ! curl -fsS "${CURL_AUTH_ARGS[@]}" "$QDRANT_URL/collections" \
        > "$BACKUP_DIR/.collections.json.tmp" 2>>"$LOG_FILE"; then
    err "Qdrant not reachable at $QDRANT_URL/collections. Aborting."
    rm -f "$BACKUP_DIR/.collections.json.tmp"
    exit 1
fi

# Extract collection names with grep -oE — avoid piping into a Python
# interpreter so this script can run in minimal environments. The pattern
# `"name":"..."` is exact: the leading quote ensures we don't match
# `"collections":` or any other wrapper key that happens to end in
# `name`.
COLLECTIONS=$(grep -oE '"name":"[^"]+"' "$BACKUP_DIR/.collections.json.tmp" \
                | sed 's/^"name":"//; s/"$//')
rm -f "$BACKUP_DIR/.collections.json.tmp"

if [[ -z "$COLLECTIONS" ]]; then
    err "No collections found at $QDRANT_URL. Nothing to back up."
    exit 1
fi

COLLECTION_COUNT=$(echo "$COLLECTIONS" | wc -l)
log "Found $COLLECTION_COUNT collection(s): $(echo $COLLECTIONS | tr '\n' ' ')"

# ─── Snapshot each collection ────────────────────────────────────────────
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
DOWNLOADED=0
FAILED=0

for coll in $COLLECTIONS; do
    log "Snapshotting collection: $coll"

    # 1. Create the snapshot inside Qdrant.
    if ! curl -fsS "${CURL_AUTH_ARGS[@]}" -X POST \
            "$QDRANT_URL/collections/$coll/snapshots" \
            > "$BACKUP_DIR/.snap_create_$coll.json" 2>>"$LOG_FILE"; then
        err "  Failed to create snapshot for $coll"
        rm -f "$BACKUP_DIR/.snap_create_$coll.json"
        FAILED=$((FAILED + 1))
        continue
    fi

    SNAP_NAME=$(grep -oE '"name":"[^"]+"' "$BACKUP_DIR/.snap_create_$coll.json" \
                  | head -1 | sed 's/^"name":"//; s/"$//')
    rm -f "$BACKUP_DIR/.snap_create_$coll.json"

    if [[ -z "$SNAP_NAME" ]]; then
        err "  Empty snapshot name for $coll"
        FAILED=$((FAILED + 1))
        continue
    fi

    # 2. Download to <BACKUP_DIR>/<collection>/<timestamp>__<snap_name>.
    #    Including the timestamp makes 7-day retention deterministic (see
    #    the `find -mtime` block below) and lets multiple daily snapshots
    #    coexist if the script is invoked manually more than once.
    COLL_DIR="$BACKUP_DIR/$coll"
    mkdir -p "$COLL_DIR"
    DEST="$COLL_DIR/${TIMESTAMP}__${SNAP_NAME}"

    if ! curl -fsS "${CURL_AUTH_ARGS[@]}" \
            "$QDRANT_URL/collections/$coll/snapshots/$SNAP_NAME" \
            -o "$DEST" 2>>"$LOG_FILE"; then
        err "  Failed to download snapshot for $coll: $SNAP_NAME"
        FAILED=$((FAILED + 1))
        continue
    fi

    SIZE=$(du -h "$DEST" | cut -f1)
    log "  Downloaded: $DEST ($SIZE)"

    # 3. Delete the snapshot from Qdrant to free its disk. Failure here is
    #    not fatal — the next retention pass on Qdrant's own storage will
    #    eventually clean it up, and we still have a local copy.
    if ! curl -fsS "${CURL_AUTH_ARGS[@]}" -X DELETE \
            "$QDRANT_URL/collections/$coll/snapshots/$SNAP_NAME" \
            > /dev/null 2>>"$LOG_FILE"; then
        log "  [warn] Could not delete in-Qdrant snapshot $SNAP_NAME (local copy is safe)"
    fi

    DOWNLOADED=$((DOWNLOADED + 1))
done

log "Snapshot summary: $DOWNLOADED downloaded, $FAILED failed"

# ─── Retention: delete local snapshots older than RETAIN_DAYS ────────────
DELETED=$(find "$BACKUP_DIR" -mindepth 2 -maxdepth 2 -type f -name '*.snapshot' \
            -mtime +"$RETAIN_DAYS" -print -delete | wc -l)
log "Retention: deleted $DELETED snapshot(s) older than ${RETAIN_DAYS} days"

REMAINING=$(find "$BACKUP_DIR" -mindepth 2 -maxdepth 2 -type f -name '*.snapshot' | wc -l)
log "Done. $REMAINING snapshot(s) retained across $COLLECTION_COUNT collection(s) in $BACKUP_DIR"

if [[ "$FAILED" -gt 0 ]]; then
    err "$FAILED collection(s) failed — see log above."
    exit 1
fi
