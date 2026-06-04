#!/bin/bash
# ============================================================
# Flowmanner — Dev Entrypoint
# ============================================================
# 1. Wait for PostgreSQL to be ready
# 2. Run Alembic migrations
# 3. Start uvicorn with hot-reload
# ============================================================
set -e

PG_HOST="${POSTGRES_HOST:-dev-postgres}"
PG_USER="${POSTGRES_USER:-flowmanner}"
PG_DB="${POSTGRES_DB:-flowmanner}"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RESET="\033[0m"

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  Flowmanner Dev — Starting Up${RESET}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# ── 1. Wait for PostgreSQL ──────────────────────────────
echo ""
echo -n "Waiting for PostgreSQL (${PG_HOST}:5432) ..."
until pg_isready -h "${PG_HOST}" -U "${PG_USER}" -d "${PG_DB}" -q 2>/dev/null; do
    sleep 1
    echo -n "."
done
echo -e " ${GREEN}ready${RESET}"

# ── 2. Run migrations ──────────────────────────────────
echo ""
echo "Running database migrations..."
cd /app
if alembic upgrade head; then
    echo -e "${GREEN}Migrations complete.${RESET}"
else
    echo -e "${RED}Migration failed! Check the error above.${RESET}"
    echo -e "${YELLOW}Continuing anyway (tables may already exist)...${RESET}"
fi

# ── 3. Start uvicorn ───────────────────────────────────
echo ""
echo -e "${GREEN}Starting uvicorn with hot-reload on :8000${RESET}"
echo -e "${YELLOW}API docs: http://localhost:8000/docs${RESET}"
echo -e "${YELLOW}Health:   http://localhost:8000/health${RESET}"
echo ""

exec uvicorn app.main_fastapi:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --reload-dir /app/app \
    --log-level info
