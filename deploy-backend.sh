#!/bin/bash
# =============================================================================
# Flowmanner Backend Deployment Script
# =============================================================================
# Usage:
#   ./deploy-backend.sh                  # Normal deploy (no migrations)
#   ./deploy-backend.sh --migrate        # Run alembic migrations before deploy
#   ./deploy-backend.sh --dry-run        # Preview without executing
#   ./deploy-backend.sh --rollback       # Revert to previous backend version
#   ./deploy-backend.sh --migrate --dry-run
#
# Environment:
#   Runs on: Homelab (local machine)
#   Backend container: workflows-backend:restored
#   Health: curl -f http://localhost:8000/health
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
HEALTH_CHECK_RETRIES=15
HEALTH_CHECK_DELAY=3

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

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
DRY_RUN=false
ROLLBACK=false
MIGRATE=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=true ;;
    --rollback) ROLLBACK=true ;;
    --migrate)  MIGRATE=true ;;
    --help|-h)
      echo "Usage: $0 [--migrate] [--dry-run] [--rollback]"
      echo ""
      echo "Options:"
      echo "  --migrate    Run alembic migrations before deploying"
      echo "  --dry-run    Preview actions without executing"
      echo "  --rollback   Revert to the previous backend version"
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

  # Restart container with the old image
  cd "$COMPOSE_DIR" && docker compose up -d --no-deps --force-recreate "$BACKEND_CONTAINER"

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
# Catches: untracked files (??) and modified tracked files (M) ending in .py.
# Misses: migrations in HEAD that were never applied to the DB (would need
# a DB query to detect — out of scope for this patch).
check_pending_migrations() {
  local pending
  pending=$(git -C "$COMPOSE_DIR" status --porcelain backend/alembic/versions/ 2>/dev/null \
            | grep -E '\.py$' \
            | grep -vE '^.D ' \
            | awk '{print $2}') || pending=""

  if [ -z "$pending" ]; then
    return 0
  fi

  local count
  count=$(echo "$pending" | wc -l)
  log_warn "Found ${count} uncommitted migration file(s) in backend/alembic/versions/:"
  while IFS= read -r mig; do
    log_warn "  - ${mig}"
  done <<< "$pending"
  log_warn "These will be baked into the image but NOT applied to the DB."
  log_warn "Apply now with: $0 --migrate"
  echo ""
}

run_migrations() {
  if [ "$MIGRATE" = false ]; then
    check_pending_migrations
    log_info "Skipping migrations (--migrate not specified)"
    return 0
  fi

  log_step "Running Alembic migrations"

  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN]${NC} docker compose exec backend alembic upgrade head"
    return 0
  fi

  # Run migrations against the CURRENT container (before rebuild)
  # This ensures migrations are applied to the persistent volume
  if docker ps --format '{{.Names}}' | grep -q "$BACKEND_CONTAINER"; then
    cd "$COMPOSE_DIR" && docker compose exec -T "$BACKEND_CONTAINER" alembic upgrade head
    log_success "Migrations applied successfully"
  else
    log_warn "Backend container not running — migrations will run on first startup"
  fi
}

# ---------------------------------------------------------------------------
# Build & Deploy
# ---------------------------------------------------------------------------
build_and_deploy() {
  log_step "Building backend image"

  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN]${NC} docker build -t ${BACKEND_IMAGE} ${BACKEND_SOURCE}"
    echo -e "${YELLOW}[DRY-RUN]${NC} cd ${COMPOSE_DIR} && docker compose up -d --no-deps --force-recreate ${BACKEND_CONTAINER}"
    return 0
  fi

  # Build new image (target runtime — test stage is last, not default)
  docker build --target runtime -t "$BACKEND_IMAGE" "$BACKEND_SOURCE"

  log_step "Deploying backend container"

  # Restart container with new image
  cd "$COMPOSE_DIR" && docker compose up -d --no-deps --force-recreate "$BACKEND_CONTAINER"

  log_success "Backend container restarted"
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
  fi
  echo ""

  # -- Rollback mode --
  if [ "$ROLLBACK" = true ]; then
    perform_rollback
    exit $?
  fi

  # -- Normal deploy --
  pre_deploy_health
  save_current_image
  run_migrations
  build_and_deploy

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
