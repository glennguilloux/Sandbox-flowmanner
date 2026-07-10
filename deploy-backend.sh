#!/bin/bash
# =============================================================================
# Flowmanner Backend Deployment Script
# =============================================================================
# Usage:
#   ./deploy-backend.sh                  # Normal deploy (no migrations)
#   ./deploy-backend.sh --migrate        # Run alembic migrations before deploy
#   ./deploy-backend.sh --dry-run        # Preview without executing
#   ./deploy-backend.sh --rollback       # Revert to previous backend version
#   ./deploy-backend.sh --skip-precheck  # Skip the pre-deploy gate
#   ./deploy-backend.sh --no-smoke       # Skip pre-promotion boot smoke test
#   ./deploy-backend.sh --migrate --dry-run
#
# Environment:
#   Runs on: Homelab (local machine)
#   Backend container: workflows-backend:restored
#   Health: curl -f http://localhost:8000/health
#   Precheck gate: scripts/pre-deploy-check.sh (Wave 2 wired-in)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_SOURCE="/opt/flowmanner/backend/"
BACKEND_IMAGE="workflows-backend:restored"
BACKEND_CONTAINER="backend"
COMPOSE_DIR="/opt/flowmanner"
HEALTH_URL="http://localhost:8000/health"
# Env-overridable: set DEPLOY_HEALTH_RETRIES / DEPLOY_HEALTH_BACKOFF_S to tune.
# Default 20×5s = 100s window — covers cold-start embedding model load (~19s).
HEALTH_CHECK_RETRIES=${DEPLOY_HEALTH_RETRIES:-20}
HEALTH_CHECK_DELAY=${DEPLOY_HEALTH_BACKOFF_S:-5}

# All three containers share the BACKEND_IMAGE and run code from the
# same /app/ tree baked at build time.  Whenever the image changes, all
# three must be recreated together — otherwise the FastAPI backend can
# be running new code while the celery worker / beat still execute the
# old image, which silently drops task handlers (or worse, runs them
# against a model schema that the task code doesn't know about).
CELERY_SERVICES=("celery-worker" "celery-beat")

# Rollback tags
BACKUP_TAG="workflows-backend:backup-$(date +%Y%m%d-%H%M%S)"
CURRENT_TAG="workflows-backend:backup-current"

# ---------------------------------------------------------------------------
# Colors & Output Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
log_step()    { echo -e "\n${CYAN}${BOLD}>>> $*${NC}"; }

# -------------------------------------------------------------------
# Flags
# -------------------------------------------------------------------
DRY_RUN=false
ROLLBACK=false
MIGRATE=false
VALIDATE=true  # Auto-on when --migrate is set; disable with --no-validate
SKIP_PRECHECK=false
SMOKETEST=true  # Pre-promotion boot smoke test (disable with --no-smoke)

for arg in "$@"; do
  case "$arg" in
    --dry-run)        DRY_RUN=true ;;
    --rollback)       ROLLBACK=true ;;
    --migrate)        MIGRATE=true ;;
    --validate)       VALIDATE=true ;;
    --no-validate)    VALIDATE=false ;;
    --skip-precheck)  SKIP_PRECHECK=true ;;
    --no-smoke)      SMOKETEST=false ;;
    --help|-h)
      echo "Usage: $0 [--migrate] [--dry-run] [--rollback] [--validate|--no-validate] [--skip-precheck]"
      echo ""
      echo "Options:"
      echo "  --migrate         Run alembic migrations before deploying"
      echo "  --dry-run         Preview actions without executing"
      echo "  --rollback        Revert to the previous backend version"
      echo "  --validate        Force-enable pre-migrate validation gate (default when --migrate)"
      echo "  --no-validate     Skip the pre-migrate validation gate (escape hatch)"
      echo "  --skip-precheck   Skip the pre-deploy gate (used by orchestrators"
      echo "                    that have already validated)"
      echo "  --no-smoke       Skip the pre-promotion boot smoke test"
      exit 0
      ;;
    *)
      log_error "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

# Health check with retries
check_health() {
  local url="$1"
  local label="$2"
  local retries="${3:-$HEALTH_CHECK_RETRIES}"
  local delay="${4:-$HEALTH_CHECK_DELAY}"

  log_info "Checking ${label} health at ${url} ..."

  for i in $(seq 1 "$retries"); do
    if curl -fsSL --max-time 10 "$url" > /dev/null 2>&1; then
      log_success "${label} health check passed (attempt ${i}/${retries})"
      return 0
    fi
    if [ "$i" -lt "$retries" ]; then
      log_warn "Health check attempt ${i}/${retries} failed, retrying in ${delay}s ..."
      sleep "$delay"
    fi
  done

  log_error "${label} health check FAILED after ${retries} attempts"
  return 1
}

# Record current image for rollback
save_current_image() {
  log_step "Saving current backend image for rollback"

  # In DRY_RUN mode, NEVER overwrite the saved-image slot. Otherwise
  # repeated dry-runs (e.g. for safety before a real deploy) would lose
  # the original backup tag — a silent state corruption that defeats
  # the rollback path entirely.
  if [ "$DRY_RUN" = true ]; then
    log_info "[DRY-RUN] would tag ${BACKEND_IMAGE} -> ${BACKUP_TAG} + ${CURRENT_TAG}"
    log_info "[DRY-RUN] no actual image tags modified"
    return 0
  fi

  # Check if image exists
  if ! docker image inspect "$BACKEND_IMAGE" > /dev/null 2>&1; then
    log_warn "No existing backend image found — nothing to back up"
    return 0
  fi

  # Tag with both timestamped and "current" backup
  docker tag "$BACKEND_IMAGE" "$BACKUP_TAG"
  docker tag "$BACKEND_IMAGE" "$CURRENT_TAG"
  log_success "Current image tagged as ${CURRENT_TAG}"
}

# Recreate every container that pins BACKEND_IMAGE so all three stay in
# sync with the current image tag.  Used by both build_and_deploy (after
# a fresh build) and perform_rollback (after retagging the old image).
recreate_backend_services() {
  cd "$COMPOSE_DIR" && docker compose up -d --no-deps --force-recreate \
    "$BACKEND_CONTAINER" "${CELERY_SERVICES[@]}"
}

# ---------------------------------------------------------------------------
# Boot Smoke Test (pre-promotion guard)
# ---------------------------------------------------------------------------
# Run the freshly-built image in a THROWAWAY container with the live
# backend's environment. If the app fails to boot (e.g. a SQLAlchemy
# mapper-resolution import error like the 2026-07-09 T1 outage, where a
# TYPE_CHECKING-only `datetime` import crashed `uvicorn app.main_fastapi:app`
# at startup), /health never returns 200 and we ABORT before recreating the
# live container — preventing a crash loop on production.
#
# This catches failures that ruff/mypy cannot: runtime import-time errors
# that only surface when the ASGI app object is constructed. The existing
# post-recreate health check fires AFTER the live container is already
# swapped, so it can only detect (not prevent) a bad image. This test runs
# BEFORE the swap.
boot_smoke_test() {
  if [ "$SMOKETEST" = false ]; then
    log_info "Boot smoke test SKIPPED (--no-smoke)"
    return 0
  fi
  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN]${NC} boot smoke test: run new image, curl /health, abort if not 200"
    return 0
  fi

  log_step "Boot smoke test (pre-promotion) — verify new image starts"

  # We need a running backend to borrow a representative production env +
  # network from. If none is up yet (first-ever deploy), skip — the
  # post-recreate health check remains the only guard in that case.
  if ! docker ps --format '{{.Names}}' | grep -q "$BACKEND_CONTAINER"; then
    log_warn "No running backend to borrow env from — skipping boot smoke test"
    return 0
  fi

  local env_file
  env_file=$(mktemp /tmp/flowmanner-boot-smoke-env.XXXXXX.txt)
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$BACKEND_CONTAINER" > "$env_file"

  local net
  net=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$BACKEND_CONTAINER" | head -1)
  [ -z "$net" ] && net="bridge"

  # Internal app port: derive from HEALTH_URL (e.g. http://localhost:8000/health -> 8000)
  local app_port
  app_port=$(echo "$HEALTH_URL" | sed -E 's#.*:([0-9]+)/.*#\1#')
  [ -z "$app_port" ] && app_port=8000

  local smoke_port=8099
  local smoke_name="flowmanner-boot-smoke-$$"
  local smoke_url="http://127.0.0.1:${smoke_port}/health"

  docker rm -f "$smoke_name" >/dev/null 2>&1 || true
  log_info "Running $BACKEND_IMAGE in throwaway container (network=$net, app_port=$app_port)"
  docker run -d --name "$smoke_name" --network "$net" --env-file "$env_file" \
    -p "${smoke_port}:${app_port}" "$BACKEND_IMAGE" \
    sh -c "cd /app && uvicorn app.main_fastapi:app --host 0.0.0.0 --port ${app_port}" >/dev/null 2>&1

  local result=1  # 0=ok, 1=timeout, 2=container-died
  for i in $(seq 1 12); do
    if curl -fsSL --max-time 4 "$smoke_url" >/dev/null 2>&1; then
      result=0
      break
    fi
    if ! docker ps --format '{{.Names}}' | grep -q "$smoke_name"; then
      result=2
      break
    fi
    sleep 3
  done

  # Always clean up the throwaway container + env file.
  docker rm -f "$smoke_name" >/dev/null 2>&1 || true
  rm -f "$env_file"

  if [ "$result" -eq 0 ]; then
    log_success "Boot smoke test passed — new image starts and serves /health"
    return 0
  fi
  if [ "$result" -eq 2 ]; then
    log_error "Boot smoke test FAILED — new image crashed on startup (container exited)."
  else
    log_error "Boot smoke test FAILED — /health did not return 200 within timeout."
  fi
  log_error "Aborting deploy. The live (old) backend is UNTOUCHED."
  log_error "Inspect the boot error: docker run --rm --network ${net} --env-file <live-env> ${BACKEND_IMAGE}"
  return 1
}

# Rollback to previous backend version
perform_rollback() {
  log_step "Rolling back backend to previous version"

  # Check if backup image exists
  if ! docker image inspect "$CURRENT_TAG" > /dev/null 2>&1; then
    log_error "No backup image found (${CURRENT_TAG}). Cannot rollback."
    return 1
  fi

  # Retag backup as the active image
  docker tag "$CURRENT_TAG" "$BACKEND_IMAGE"

  # Restart every container that pins BACKEND_IMAGE with the old image,
  # not just the FastAPI backend — otherwise celery would keep running
  # the new (rolled-back-from) code while the API reverts to old.
  cd "$COMPOSE_DIR" && docker compose up -d --no-deps --force-recreate \
    "$BACKEND_CONTAINER" "${CELERY_SERVICES[@]}"

  # Verify rollback health
  if check_health "$HEALTH_URL" "Backend (rollback)" 8 3; then
    log_success "Backend rollback completed successfully"
    return 0
  else
    log_error "Backend rollback health check failed — manual intervention required"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Pre-Deploy Health Check
# ---------------------------------------------------------------------------
pre_deploy_health() {
  log_step "Pre-Deploy Health Check"

  if ! check_health "$HEALTH_URL" "Backend (current)" 3 2; then
    log_warn "Current backend is unhealthy — proceeding with deploy anyway"
  else
    log_success "Current backend is healthy — good baseline"
  fi
}

# ---------------------------------------------------------------------------
# Alembic Migrations
# ---------------------------------------------------------------------------

# Detect uncommitted migration files in backend/alembic/versions/ and warn
# the operator that they will be baked into the image but NOT applied to the
# running DB unless --migrate is passed.
#
# Detects migrations that need --migrate in TWO ways:
#   1. Uncommitted migration files in backend/alembic/versions/ (?? / M).
#   2. Committed migrations in HEAD that are NOT yet applied to the running DB
#      (the case that burned GOV-1.1: a new head was committed but the deploy
#      ran without --migrate, so the schema never changed and the feature's
#      writes failed at runtime).
#
# When any are found and --migrate was NOT passed, print a loud guardrail that
# tells the operator (Glenn) to re-run with --migrate.
check_pending_migrations() {
  local uncommitted applied_heads needed_migrate=0 mig

  # 1) Uncommitted migration files.
  uncommitted=$(git -C "$COMPOSE_DIR" status --porcelain backend/alembic/versions/ 2>/dev/null \
            | grep -E '\.py$' \
            | grep -vE '^.D ' \
            | awk '{print $2}') || uncommitted=""

  # 2) Committed-but-unapplied migrations: compare the DB "current" head(s)
  #    against the repo "heads". If they differ, a committed migration needs
  #    applying. Best-effort: if alembic/container is unavailable, skip (this
  #    is a guardrail, not a hard gate).
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$BACKEND_CONTAINER"; then
    local db_current repo_heads
    db_current=$(docker compose exec -T "$BACKEND_CONTAINER" alembic current 2>/dev/null \
      | awk '/^[A-Za-z0-9_]/ && !/^(INFO|DEBUG|WARNING)/{print $1}')
    repo_heads=$(docker compose exec -T "$BACKEND_CONTAINER" alembic heads 2>/dev/null \
      | awk '/^[A-Za-z0-9_]/ && !/^(INFO|DEBUG|WARNING)/{print $1}')

    if [ -n "$db_current" ] && [ -n "$repo_heads" ]; then
      for h in $db_current; do
        echo "$repo_heads" | grep -qx "$h" || needed_migrate=1
      done
      # Also catch the "multiple heads" situation: if repo has >1 head
      # (unmerged branch), that itself signals migrations were never applied.
      if [ "$(echo "$repo_heads" | wc -l)" -gt 1 ]; then
        needed_migrate=1
      fi
    fi
  fi

  if [ -z "$uncommitted" ] && [ "$needed_migrate" -eq 0 ]; then
    return 0
  fi

  echo ""
  echo -e "${RED}${BOLD}!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!${NC}"
  echo -e "${RED}${BOLD}!! MIGRATIONS NEED APPLYING — TELL GLENN TO RUN --migrate !!${NC}"
  echo -e "${RED}${BOLD}!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!${NC}"
  echo ""
  if [ -n "$uncommitted" ]; then
    local count
    count=$(echo "$uncommitted" | wc -l)
    log_warn "Found ${count} uncommitted migration file(s) in backend/alembic/versions/:"
    while IFS= read -r mig; do
      [ -n "$mig" ] && log_warn "  - ${mig}"
    done <<< "$uncommitted"
    log_warn "These will be baked into the image but NOT applied to the DB."
  fi
  if [ "$needed_migrate" -eq 1 ]; then
    log_warn "Committed migration(s) in HEAD are NOT applied to the running DB"
    log_warn "(e.g. a new alembic head was merged but the last deploy skipped --migrate)."
    log_warn "The schema is STALE relative to the code — new/changed models may fail."
  fi
  local _script="${BASH_SOURCE[0]:-deploy-backend.sh}"
  log_warn ">>> Re-run with: bash ${_script} --migrate"
  log_warn ">>> (or 'git diff --stat' to see which migrations are pending)"
  echo ""
}

# -------------------------------------------------------------------
# Migration Validation Gate
# -------------------------------------------------------------------
# Delegates the real validation work to scripts/validate-migration.sh so the
# Makefile path and deploy path use the same snapshot-diff gate.
#
# This runs AFTER build_and_deploy so the running container has the latest
# migration files baked in — otherwise validation would be checking the OLD image
# against the NEW source, which is a tautology and useless.
#
# On failure: exits non-zero WITHOUT rolling back. The new image is up and
# healthy, only the migration is broken. State is recoverable: fix the migration
# and re-run with --migrate (no rebuild needed).
#
# On success: returns 0 and run_migrations proceeds normally.
run_validation() {
  if [ "$MIGRATE" = false ]; then
    return 0
  fi
  if [ "$VALIDATE" = false ]; then
    log_warn "Validation gate SKIPPED (--no-validate)"
    return 0
  fi

  log_step "Migration validation gate (snapshot diff + offline SQL render)"

  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN]${NC} bash ${COMPOSE_DIR}/scripts/validate-migration.sh"
    echo -e "${YELLOW}[DRY-RUN]${NC}   snapshot diff + offline SQL render"
    return 0
  fi

  bash "${COMPOSE_DIR}/scripts/validate-migration.sh"
}

run_migrations() {
  if [ "$MIGRATE" = false ]; then
    check_pending_migrations
    log_info "Skipping migrations (--migrate not specified)"
    return 0
  fi

  log_step "Running Alembic migrations"

  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN]${NC} docker compose exec ${BACKEND_CONTAINER} alembic upgrade head"
    echo -e "${YELLOW}[DRY-RUN]${NC} (post-upgrade head verification also runs in real mode)"
    return 0
  fi

  # CRITICAL: this function MUST run after build_and_deploy so the running
  # container has the latest migration files baked into its image. Otherwise
  # alembic will silently return 0 ("already at head") without applying the
  # new migration — the container's alembic/versions/ is from the OLD image.
  # Bug caught twice (chunks 2 & 3 of Q2-Q3 plan, 2026-06-12/13).

  if ! docker ps --format '{{.Names}}' | grep -q "$BACKEND_CONTAINER"; then
    log_error "Backend container not running — cannot run migrations safely"
    return 1
  fi

  # Extract the alembic revision from an exec'd command. Alembic prints lines
  # like "<rev> (head)" or "<rev>" on its own line, with INFO/DEBUG prefixes
  # on other lines. We take the first word of the first line that looks like
  # a revision and is not a log prefix.
  _alembic_rev() {
    cd "$COMPOSE_DIR" && docker compose exec -T "$BACKEND_CONTAINER" "$@" 2>/dev/null \
      | awk '/^[A-Za-z0-9_]/ && !/^(INFO|DEBUG|WARNING)/{print $1; exit}'
  }

  local before_head after_head expected_head
  before_head=$(_alembic_rev alembic current)
  if [ -z "$before_head" ]; then
    log_warn "Could not parse current alembic head (continuing anyway)"
    before_head="(unknown)"
  else
    log_info "Current alembic head: ${before_head}"
  fi

  # Retry alembic upgrade head once — the DB connection may need a moment
  # to stabilise even after the HTTP health check passes.
  local alembic_ok=false
  cd "$COMPOSE_DIR" && docker compose exec -T "$BACKEND_CONTAINER" alembic upgrade head && alembic_ok=true
  if [ "$alembic_ok" = false ]; then
    log_warn "alembic upgrade head failed on first attempt — retrying in 5s"
    sleep 5
    if ! cd "$COMPOSE_DIR" && docker compose exec -T "$BACKEND_CONTAINER" alembic upgrade head; then
      log_error "alembic upgrade head FAILED after retry"
      return 1
    fi
    log_success "alembic upgrade head succeeded on retry"
  fi

  after_head=$(_alembic_rev alembic current)
  expected_head=$(_alembic_rev alembic heads)

  if [ -z "$expected_head" ] || [ -z "$after_head" ]; then
    log_error "Could not determine alembic head after migration"
    log_error "  after='${after_head}', expected='${expected_head}'"
    return 1
  fi

  if [ "$after_head" != "$expected_head" ]; then
    log_error "MIGRATION VERIFICATION FAILED"
    log_error "  Expected head: ${expected_head}"
    log_error "  Actual head:   ${after_head}"
    log_error "  Was:           ${before_head}"
    log_error "The new migration was NOT applied. Aborting deploy."
    return 1
  fi

  if [ "$before_head" = "$after_head" ]; then
    log_info "Database already at head ${after_head} — no migration needed"
  else
    log_success "Migrated from ${before_head} to ${after_head}"
  fi
}

# ---------------------------------------------------------------------------
# Build & Deploy
# ---------------------------------------------------------------------------
build_and_deploy() {
  log_step "Building backend image"

  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN]${NC} docker build --target runtime -t ${BACKEND_IMAGE} ${BACKEND_SOURCE}"
    echo -e "${YELLOW}[DRY-RUN]${NC} cd ${COMPOSE_DIR} && docker compose up -d --no-deps --force-recreate ${BACKEND_CONTAINER} ${CELERY_SERVICES[*]}"
    return 0
  fi

  # Build new image (target runtime — test stage is last, not default)
  docker build --target runtime -t "$BACKEND_IMAGE" "$BACKEND_SOURCE"

  # Pre-promotion guard: boot the new image in a throwaway container and
  # verify /health returns 200 BEFORE swapping the live container. This
  # catches startup-crash bugs (e.g. runtime import errors ruff/mypy miss)
  # so a bad image can never reach production. The live backend is only
  # recreated if this passes.
  if ! boot_smoke_test; then
    exit 1
  fi

  log_step "Deploying backend + celery containers"
  log_info "Recreating: ${BACKEND_CONTAINER} ${CELERY_SERVICES[*]}"

  # Restart every container that pins BACKEND_IMAGE so all three run the
  # freshly-built code.  Doing it here (after the build, before the
  # health check) means the health-checked backend is the new code and
  # any celery task that fires after deploy also runs the new code.
  recreate_backend_services

  # Wait for the backend to be healthy before returning.  This prevents
  # the --migrate race condition: without this gate, run_migrations()
  # fires alembic against a container that Docker reports as "up" but
  # whose DB connection isn't established yet, causing alembic to
  # silently no-op and the head verification to fail.
  check_health "$HEALTH_URL" "Backend (post-recreate readiness)" "$HEALTH_CHECK_RETRIES" "$HEALTH_CHECK_DELAY"

  log_success "Backend + celery containers recreated"
}

# ---------------------------------------------------------------------------
# Post-Deploy Health Check
# ---------------------------------------------------------------------------
post_deploy_health() {
  log_step "Post-Deploy Health Check"

  if ! check_health "$HEALTH_URL" "Backend (new)" "$HEALTH_CHECK_RETRIES" "$HEALTH_CHECK_DELAY"; then
    return 1
  fi

  log_success "Post-deploy health check passed"
  return 0
}

# ---------------------------------------------------------------------------
# Pre-Deploy Gate (Wave 2 — pre-deploy-check.sh)
# ---------------------------------------------------------------------------
# Fail-closed gate invoked up-front unless --skip-precheck is passed.
# Orchestrators (deploy-all.sh, scripts/deploy_flowmanner.sh) pass
# --skip-precheck because they have their own preflight. Manual invocations
# run the full gate. --rollback exits before this point.
PRECHECK_SCRIPT="${COMPOSE_DIR}/scripts/pre-deploy-check.sh"

run_precheck() {
  if [ "$SKIP_PRECHECK" = true ]; then
    log_info "precheck SKIPPED (--skip-precheck)"
    return 0
  fi
  if [ ! -x "$PRECHECK_SCRIPT" ]; then
    log_error "precheck not found or not executable at $PRECHECK_SCRIPT"
    exit 1
  fi
  log_info "Running precheck: $PRECHECK_SCRIPT"
  if ! bash "$PRECHECK_SCRIPT"; then
    log_error "precheck FAILED — aborting deploy"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  echo ""
  echo -e "${BOLD}========================================${NC}"
  echo -e "${BOLD}  Flowmanner Backend Deployment${NC}"
  echo -e "${BOLD}========================================${NC}"
  echo ""

  if [ "$DRY_RUN" = true ]; then
    log_warn "DRY-RUN MODE — no changes will be made"
    echo ""
  fi

  if [ "$MIGRATE" = true ]; then
    log_info "Migrations: ENABLED"
    echo "[ESCALATION REQUIRED: migrate] --migrate flag requires DB write access and may alter schema."
  fi
  echo ""

  # -- Rollback mode --
  if [ "$ROLLBACK" = true ]; then
    perform_rollback
    exit $?
  fi

  # -- Normal deploy --
  run_precheck

  # Emit sudo escalation token when precheck is skipped (--skip-precheck)
  # so the operator/orchestrator still sees the warning.
  if [[ "$SKIP_PRECHECK" == "true" ]] && [[ "${WG_CHECK:-}" != "skip" ]]; then
    if ! sudo -n /usr/bin/wg show wg0 >/dev/null 2>&1; then
      echo '[ESCALATION REQUIRED: sudo] WireGuard sudoers not configured. Run as root: echo "<user> ALL=(root) NOPASSWD: /usr/bin/wg show *" | sudo tee /etc/sudoers.d/flowmanner-deploy && sudo chmod 0440 /etc/sudoers.d/flowmanner-deploy'
    fi
  fi

  pre_deploy_health
  save_current_image

  # CRITICAL: build_and_deploy MUST run before run_migrations so the running
  # container has the latest migration files baked into its image. See
  # run_migrations() for the full explanation.
  build_and_deploy

  if [ "$MIGRATE" = true ]; then
    if ! run_validation; then
      log_error "Validation gate failed — the new image is in place but the"
      log_error "migration is unsafe. Fix the migration, commit, and re-run:"
      log_error "  bash $0 --migrate"
      log_error "No automatic rollback (new image is healthy; only migration is bad)."
      exit 1
    fi
    if ! run_migrations; then
      log_error "Migrations failed — rolling back to previous image"
      perform_rollback
      exit 1
    fi
  else
    # No --migrate flag: just check for uncommitted migration files
    run_migrations
  fi

  if ! post_deploy_health; then
    log_error "Post-deploy health check failed — initiating automatic rollback"
    if perform_rollback; then
      log_warn "Automatic rollback succeeded — deploy aborted"
    else
      log_error "Automatic rollback FAILED — manual intervention required"
    fi
    exit 1
  fi

  echo ""
  echo -e "${GREEN}${BOLD}========================================${NC}"
  echo -e "${GREEN}${BOLD}  Backend Deploy Complete${NC}"
  echo -e "${GREEN}${BOLD}========================================${NC}"
  echo ""
}

main "$@"
