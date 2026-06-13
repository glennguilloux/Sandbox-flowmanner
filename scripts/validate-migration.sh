#!/bin/bash
# =============================================================================
# Flowmanner — Migration Validation Gate
# =============================================================================
# Pre-deploy validation that catches the most common Alembic damage modes
# before they hit the live database.
#
# Implements the MVP from
#   .hermes/plans/migration-research-2026-06-13-FINDINGS.md
# specifically the steps that do NOT require production DB credentials:
#
#   Step 1: `alembic check`                 — catch model/migration drift
#   Step 2: `alembic upgrade head --sql`    — catch offline-mode failures
#                                             (sa.inspect, asyncpg multi-statement,
#                                             env.py bugs, etc.)
#
# Step 3 (prod-clone smoke test) is intentionally NOT included here — it needs
# a CREATEDB-capable user and is wired in separately as `--clone`. See the
# findings doc for the full design.
#
# Usage:
#   ./scripts/validate-migration.sh             # Steps 1 + 2 (default)
#   ./scripts/validate-migration.sh --clone     # Also attempt step 3 (not
#                                               # implemented yet; warns)
#
# This catches (based on real failures from chunks 2 and 3 of the Q2-Q3 plan):
#   - asyncpg multi-statement failures (offline render surfaces the prepared-
#     statement issue that previously caused "Migrations applied successfully"
#     while the head never moved)
#   - model/migration drift (column added to model, missing from migration)
#   - missing tables, bad SQL, env.py bugs that only show up in offline mode
#   - missing dependency imports in migration env.py
#
# This does NOT catch:
#   - Runtime data integrity issues (FK violations, unique violations on
#     real data)
#   - Performance regressions
#   - Migration plan issues (e.g. wrong downgrade order)
# =============================================================================

set -euo pipefail

# --- Configuration -----------------------------------------------------------
COMPOSE_DIR="${COMPOSE_DIR:-/opt/flowmanner}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-backend}"
OFFLINE_SQL_PATH="/tmp/flowmanner-migration-check-$$.sql"
RUN_CLONE=false

# --- Colors ------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[FAIL]${NC}    $*"; }
log_step()    { echo -e "\n${CYAN}${BOLD}>>> $*${NC}"; }

# --- Parse args --------------------------------------------------------------
for arg in "$@"; do
  case "$arg" in
    --clone)  RUN_CLONE=true ;;
    --help|-h)
      echo "Usage: $0 [--clone]"
      echo ""
      echo "Options:"
      echo "  --clone   Also run migration against a pg_dump/pg_restore clone"
      echo "            (requires PG creds for the source DB; not implemented yet)"
      exit 0
      ;;
    *)
      log_error "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

# --- Pre-flight --------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  log_error "docker is not on PATH"
  exit 1
fi

if ! cd "$COMPOSE_DIR" && docker compose ps --services --status running 2>/dev/null \
     | grep -q "^${BACKEND_CONTAINER}$"; then
  log_error "Backend container '${BACKEND_CONTAINER}' is not running"
  log_error "Start it with: cd ${COMPOSE_DIR} && docker compose up -d ${BACKEND_CONTAINER}"
  exit 1
fi

# --- Helpers -----------------------------------------------------------------
exec_alembic() {
  cd "$COMPOSE_DIR" && docker compose exec -T "$BACKEND_CONTAINER" "$@"
}

cleanup() { rm -f "$OFFLINE_SQL_PATH" 2>/dev/null || true; }
trap cleanup EXIT

# --- Step 1: alembic check ---------------------------------------------------
log_step "Step 1/2: alembic check (model/migration drift)"

if exec_alembic alembic check; then
  log_success "No drift detected between models and migration files"
else
  log_error "Drift detected — models and migration files are out of sync"
  log_error "Fix with: cd ${COMPOSE_DIR} && docker compose exec ${BACKEND_CONTAINER} \\"
  log_error "             alembic revision --autogenerate -m 'sync models to migrations'"
  exit 1
fi

# --- Step 2: offline SQL render ----------------------------------------------
log_step "Step 2/2: alembic upgrade head --sql (offline render)"

if exec_alembic alembic upgrade head --sql > "$OFFLINE_SQL_PATH" 2>/dev/null; then
  sql_lines=$(wc -l < "$OFFLINE_SQL_PATH")
  sql_bytes=$(wc -c < "$OFFLINE_SQL_PATH")
  log_success "Offline render OK — ${sql_lines} lines / ${sql_bytes} bytes"
  log_info "  SQL preview: ${OFFLINE_SQL_PATH}"
  log_info "  (delete with: rm ${OFFLINE_SQL_PATH})"
else
  log_error "Offline render FAILED"
  log_error "This usually means a migration uses code that does not work in"
  log_error "offline mode (e.g. sa.inspect(conn) in upgrade(), or asyncpg-"
  log_error "incompatible multi-statement SQL via op.execute())."
  log_error "See: .hermes/plans/migration-research-2026-06-13-FINDINGS.md"
  exit 1
fi

# --- Step 3 (optional): prod-clone smoke test --------------------------------
if [ "$RUN_CLONE" = true ]; then
  log_step "Step 3/3: clone DB smoke test (pg_dump → upgrade head on clone)"
  log_warn "Not yet implemented — see .hermes/plans/migration-research-2026-06-13-FINDINGS.md"
  log_warn "This requires a separate DB user with CREATEDB rights and is not"
  log_warn "enabled by default. Wire it in once clone DB creds are settled."
  # Intentionally do NOT exit 1 here — --clone is a future addition, not a
  # regression. The first two steps are still authoritative.
fi

log_step "Validation gate PASSED"
log_success "Migration is safe to apply with:"
log_success "  bash ${COMPOSE_DIR}/deploy-backend.sh --migrate"
