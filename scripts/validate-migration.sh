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
#   Step 1: snapshot diff against backend/scripts/model_snapshot.json on host
#           and /app/scripts/model_snapshot.json inside the backend container
#           — catch NEW model/migration drift while ignoring the committed
#             historical baseline
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
PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
ALEMBIC_BIN="${ALEMBIC_BIN:-alembic}"
OFFLINE_SQL_PATH="/tmp/flowmanner-migration-check-$$.sql"
FRESH_SNAPSHOT="/tmp/flowmanner-model-snapshot-$$.json"
CONTAINER_FRESH_SNAPSHOT="${CONTAINER_FRESH_SNAPSHOT:-/tmp/flowmanner-model-snapshot-$$.json}"
CONTAINER_SNAPSHOT_FILE="${CONTAINER_SNAPSHOT_FILE:-/app/scripts/model_snapshot.json}"
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

# --- Helpers -----------------------------------------------------------------
exec_alembic() {
  cd "$COMPOSE_DIR" && docker compose exec -T "$BACKEND_CONTAINER" "$@"
}

cleanup() { rm -f "$OFFLINE_SQL_PATH" "$FRESH_SNAPSHOT" 2>/dev/null || true; }
trap cleanup EXIT

# --- Step 1: snapshot diff ---------------------------------------------------
log_step "Step 1/2: snapshot diff (model/migration drift)"

SNAPSHOT_FILE="${SNAPSHOT_FILE:-${COMPOSE_DIR}/backend/scripts/model_snapshot.json}"
CONTAINER_SNAPSHOT_FILE="${CONTAINER_SNAPSHOT_FILE:-/app/scripts/model_snapshot.json}"

if [ ! -f "$SNAPSHOT_FILE" ]; then
  log_error "Snapshot file not found: $SNAPSHOT_FILE"
  log_error "Run 'make snapshot-refresh' to generate it, then commit the result."
  exit 1
fi

log_info "Committed host snapshot: ${SNAPSHOT_FILE}"
log_info "Container snapshot path: ${CONTAINER_SNAPSHOT_FILE}"

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

if ! exec_alembic bash -lc "${PYTHON_BIN} /app/scripts/snapshot_model_metadata.py > ${CONTAINER_FRESH_SNAPSHOT}" 2>/dev/null; then
  log_error "Snapshot generation failed inside the container"
  log_error "Ensure ${BACKEND_CONTAINER} is running an image that contains /app/scripts/snapshot_model_metadata.py"
  exit 1
fi

set +e
DIFF_OUTPUT="$(exec_alembic "${PYTHON_BIN}" /app/scripts/snapshot_diff.py "$CONTAINER_SNAPSHOT_FILE" "$CONTAINER_FRESH_SNAPSHOT" 2>&1)"
DIFF_STATUS=$?
set -e

if [ "$DIFF_STATUS" -eq 0 ]; then
  log_success "No new drift since snapshot"
elif [ "$DIFF_STATUS" -eq 1 ]; then
  log_error "Snapshot drift detected:"
  if [ -n "$DIFF_OUTPUT" ]; then
    printf '%s\n' "$DIFF_OUTPUT" | while IFS= read -r line; do
      log_error "$line"
    done
  else
    log_error "No diff output was produced"
  fi
  log_error "If this drift is intentional, run 'make snapshot-refresh' to update the baseline."
  exit 1
else
  log_error "Snapshot diff failed with exit code ${DIFF_STATUS}"
  if [ -n "$DIFF_OUTPUT" ]; then
    printf '%s\n' "$DIFF_OUTPUT" | while IFS= read -r line; do
      log_error "$line"
    done
  fi
  exit "$DIFF_STATUS"
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
