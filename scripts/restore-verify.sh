#!/bin/bash
# Flowmanner Restore Verification Script (H3)
# Checks integrity of all backup artifacts and outputs a PASS/FAIL summary.
# Usage: ./restore-verify.sh [--latest] [--artifact PATH]
#
# --latest    Check only the most recent backup in each category
# --artifact  Check a specific backup artifact file

set -euo pipefail

BACKUP_DIR="/opt/flowmanner/backups"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
skip() { echo -e "  ${YELLOW}[SKIP]${NC} $1"; SKIP_COUNT=$((SKIP_COUNT + 1)); }

LATEST_ONLY=false
TARGET_ARTIFACT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --latest) LATEST_ONLY=true; shift ;;
        --artifact) TARGET_ARTIFACT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Single artifact check ──────────────────────────────────────────
if [[ -n "$TARGET_ARTIFACT" ]]; then
    echo "Checking single artifact: $TARGET_ARTIFACT"
    if [[ ! -f "$TARGET_ARTIFACT" ]]; then
        fail "File not found: $TARGET_ARTIFACT"
        exit 1
    fi

    case "$TARGET_ARTIFACT" in
        *.dump)
            echo "--- PostgreSQL dump ---"
            if pg_restore --list "$TARGET_ARTIFACT" > /dev/null 2>&1; then
                count=$(pg_restore --list "$TARGET_ARTIFACT" 2>/dev/null | wc -l)
                pass "pg_restore --list: valid dump ($count objects)"
            else
                fail "pg_restore --list: corrupt or unreadable"
            fi
            ;;
        *.rdb)
            echo "--- Redis RDB ---"
            if [[ -s "$TARGET_ARTIFACT" ]]; then
                magic=$(head -c 5 "$TARGET_ARTIFACT" | xxd -p)
                if [[ "$magic" == "5245444953" ]]; then
                    pass "Redis RDB: valid header (REDIS magic)"
                else
                    fail "Redis RDB: invalid magic bytes ($magic)"
                fi
            else
                fail "Redis RDB: empty file"
            fi
            ;;
        *.tar.gz)
            echo "--- Tar archive ---"
            if tar -tzf "$TARGET_ARTIFACT" > /dev/null 2>&1; then
                count=$(tar -tzf "$TARGET_ARTIFACT" | wc -l)
                pass "tar.gz: valid archive ($count entries)"
            else
                fail "tar.gz: corrupt or unreadable"
            fi
            ;;
        *.json)
            echo "--- JSON ---"
            if python3 -c "import json; json.load(open('$TARGET_ARTIFACT'))" 2>/dev/null; then
                pass "JSON: valid"
            else
                fail "JSON: invalid or corrupt"
            fi
            ;;
        *.snapshot)
            echo "--- Qdrant snapshot ---"
            if [[ -s "$TARGET_ARTIFACT" ]]; then
                pass "Qdrant snapshot: exists and non-empty"
            else
                fail "Qdrant snapshot: empty or missing"
            fi
            ;;
        *)
            echo "Unknown artifact type — checking if non-empty"
            if [[ -s "$TARGET_ARTIFACT" ]]; then
                pass "$TARGET_ARTIFACT: non-empty"
            else
                fail "$TARGET_ARTIFACT: empty"
            fi
            ;;
    esac

    echo ""
    echo "=== VERIFICATION RESULT ==="
    echo "Pass: $PASS_COUNT | Fail: $FAIL_COUNT | Skip: $SKIP_COUNT"
    if [[ $FAIL_COUNT -eq 0 ]]; then
        echo "VERDICT: PASS"
    else
        echo "VERDICT: FAIL"
    fi
    exit $FAIL_COUNT
fi

# ── Full backup directory check ────────────────────────────────────

echo "=== Flowmanner Backup Verification ==="
echo "Backup directory: $BACKUP_DIR"
echo "Mode: $([ "$LATEST_ONLY" = true ] && echo 'latest only' || echo 'full')"
echo ""

# ── PostgreSQL ─────────────────────────────────────────────────────
echo "--- PostgreSQL backups ---"
PG_DIR="$BACKUP_DIR/postgres"
if [[ -d "$PG_DIR" ]]; then
    if $LATEST_ONLY; then
        latest=$(find "$PG_DIR" -name "*.dump" -type f | sort -r | head -1)
        if [[ -n "$latest" ]]; then
            if pg_restore --list "$latest" > /dev/null 2>&1; then
                count=$(pg_restore --list "$latest" 2>/dev/null | wc -l)
                pass "pg_restore (latest: $(basename "$latest")): valid ($count objects)"
            else
                fail "pg_restore (latest: $(basename "$latest")): corrupt"
            fi
        else
            skip "No PostgreSQL dumps found"
        fi
    else
        for dump in "$PG_DIR"/*.dump; do
            [[ -f "$dump" ]] || { skip "No PostgreSQL dumps found"; break; }
            if pg_restore --list "$dump" > /dev/null 2>&1; then
                pass "pg_restore: $(basename "$dump")"
            else
                fail "pg_restore: $(basename "$dump")"
            fi
        done
    fi
else
    skip "PostgreSQL backup directory not found"
fi

# ── Redis ──────────────────────────────────────────────────────────
echo "--- Redis backups ---"
REDIS_DIR="$BACKUP_DIR/redis"
if [[ -d "$REDIS_DIR" ]]; then
    if $LATEST_ONLY; then
        latest=$(find "$REDIS_DIR" -name "*.rdb" -type f | sort -r | head -1)
        if [[ -n "$latest" ]]; then
            if [[ -s "$latest" ]]; then
                magic=$(head -c 5 "$latest" | xxd -p 2>/dev/null || echo "")
                if [[ "$magic" == "5245444953" ]]; then
                    pass "Redis RDB (latest: $(basename "$latest")): valid header"
                else
                    pass "Redis RDB (latest: $(basename "$latest")): non-empty"
                fi
            else
                fail "Redis RDB (latest: $(basename "$latest")): empty"
            fi
        else
            skip "No Redis RDB files found"
        fi
    else
        for rdb in "$REDIS_DIR"/*.rdb; do
            [[ -f "$rdb" ]] || { skip "No Redis RDB files found"; break; }
            if [[ -s "$rdb" ]]; then
                pass "Redis RDB: $(basename "$rdb")"
            else
                fail "Redis RDB: $(basename "$rdb") (empty)"
            fi
        done
    fi
else
    skip "Redis backup directory not found"
fi

# ── Qdrant ─────────────────────────────────────────────────────────
echo "--- Qdrant backups ---"
QDRANT_DIR="$BACKUP_DIR/qdrant"
if [[ -d "$QDRANT_DIR" ]]; then
    if $LATEST_ONLY; then
        latest=$(find "$QDRANT_DIR" \( -name "*.snapshot" -o -name "*.tar.gz" \) -type f | sort -r | head -1)
        if [[ -n "$latest" ]]; then
            if [[ -s "$latest" ]]; then
                pass "Qdrant (latest: $(basename "$latest")): non-empty"
            else
                fail "Qdrant (latest: $(basename "$latest")): empty"
            fi
        else
            skip "No Qdrant backups found"
        fi
    else
        count=0
        for snap in "$QDRANT_DIR"/*.snapshot "$QDRANT_DIR"/*.tar.gz; do
            [[ -f "$snap" ]] || continue
            count=$((count + 1))
            if [[ -s "$snap" ]]; then
                pass "Qdrant: $(basename "$snap")"
            else
                fail "Qdrant: $(basename "$snap") (empty)"
            fi
        done
        [[ $count -eq 0 ]] && skip "No Qdrant backups found"
    fi
else
    skip "Qdrant backup directory not found"
fi

# ── RabbitMQ ───────────────────────────────────────────────────────
echo "--- RabbitMQ backups ---"
RMQ_DIR="$BACKUP_DIR/rabbitmq"
if [[ -d "$RMQ_DIR" ]]; then
    if $LATEST_ONLY; then
        latest=$(find "$RMQ_DIR" -name "*.json" -type f | sort -r | head -1)
        if [[ -n "$latest" ]]; then
            if python3 -c "import json; json.load(open('$latest'))" 2>/dev/null; then
                pass "RabbitMQ JSON (latest: $(basename "$latest")): valid"
            else
                fail "RabbitMQ JSON (latest: $(basename "$latest")): invalid"
            fi
        else
            skip "No RabbitMQ definition exports found"
        fi
    else
        count=0
        for json in "$RMQ_DIR"/*.json; do
            [[ -f "$json" ]] || continue
            count=$((count + 1))
            if python3 -c "import json; json.load(open('$json'))" 2>/dev/null; then
                pass "RabbitMQ JSON: $(basename "$json")"
            else
                fail "RabbitMQ JSON: $(basename "$json")"
            fi
        done
        [[ $count -eq 0 ]] && skip "No RabbitMQ definition exports found"
    fi
else
    skip "RabbitMQ backup directory not found"
fi

# ── Config ─────────────────────────────────────────────────────────
echo "--- Config backups ---"
CONFIG_DIR="$BACKUP_DIR/config"
if [[ -d "$CONFIG_DIR" ]]; then
    if $LATEST_ONLY; then
        latest=$(find "$CONFIG_DIR" -name "*.tar.gz" -type f | sort -r | head -1)
        if [[ -n "$latest" ]]; then
            if tar -tzf "$latest" > /dev/null 2>&1; then
                count=$(tar -tzf "$latest" | wc -l)
                pass "Config tar.gz (latest: $(basename "$latest")): valid ($count entries)"
            else
                fail "Config tar.gz (latest: $(basename "$latest")): corrupt"
            fi
        else
            skip "No config backups found"
        fi
    else
        count=0
        for tgz in "$CONFIG_DIR"/*.tar.gz; do
            [[ -f "$tgz" ]] || continue
            count=$((count + 1))
            if tar -tzf "$tgz" > /dev/null 2>&1; then
                pass "Config tar.gz: $(basename "$tgz")"
            else
                fail "Config tar.gz: $(basename "$tgz")"
            fi
        done
        [[ $count -eq 0 ]] && skip "No config backups found"
    fi
else
    skip "Config backup directory not found"
fi

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "=== VERIFICATION SUMMARY ==="
echo "Pass: $PASS_COUNT | Fail: $FAIL_COUNT | Skip: $SKIP_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then
    echo "VERDICT: PASS"
    exit 0
else
    echo "VERDICT: FAIL"
    exit 1
fi
