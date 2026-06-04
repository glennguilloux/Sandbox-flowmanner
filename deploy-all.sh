#!/bin/bash
# =============================================================================
# Flowmanner Full Stack Deployment Script
# =============================================================================
# Deploys backend first (with optional migrations), then frontend.
# Rolls back both on failure.
#
# Usage:
#   ./deploy-all.sh                  # Deploy backend + frontend
#   ./deploy-all.sh --migrate        # With alembic migrations
#   ./deploy-all.sh --dry-run        # Preview without executing
#   ./deploy-all.sh --rollback       # Rollback both services
#   ./deploy-all.sh --skip-backend   # Deploy frontend only
#   ./deploy-all.sh --skip-frontend  # Deploy backend only
#
# Environment:
#   Runs on: Homelab (local machine)
#   Backend: local docker build + compose
#   Frontend: rsync to VPS + compose build + deploy
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_BACKEND="${SCRIPT_DIR}/deploy-backend.sh"
DEPLOY_FRONTEND="${SCRIPT_DIR}/deploy-frontend.sh"

VPS_HOST="root@74.208.115.142"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/vps_flowmanner_new}"
SSH_CMD="ssh -i ${SSH_KEY} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 ${VPS_HOST}"
VPS_PROJECT_DIR="/opt/flowmanner"

BACKEND_HEALTH_URL="http://localhost:8000/health"
FRONTEND_HEALTH_URL="https://flowmanner.com"

# VPS health from homelab (through WireGuard)
VPS_BACKEND_HEALTH_URL="http://10.99.0.3:8000/health"

# ---------------------------------------------------------------------------
# Colors & Output Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
log_step()    { echo -e "\n${MAGENTA}${BOLD}=== $* ===${NC}"; }
log_substep() { echo -e "\n${CYAN}${BOLD}>>> $*${NC}"; }

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
DRY_RUN=false
ROLLBACK=false
MIGRATE=false
SKIP_BACKEND=false
SKIP_FRONTEND=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)       DRY_RUN=true ;;
    --rollback)      ROLLBACK=true ;;
    --migrate)       MIGRATE=true ;;
    --skip-backend)  SKIP_BACKEND=true ;;
    --skip-frontend) SKIP_FRONTEND=true ;;
    --help|-h)
      echo "Usage: $0 [--migrate] [--dry-run] [--rollback] [--skip-backend] [--skip-frontend]"
      echo ""
      echo "Options:"
      echo "  --migrate        Run alembic migrations before backend deploy"
      echo "  --dry-run        Preview actions without executing"
      echo "  --rollback       Rollback both backend and frontend"
      echo "  --skip-backend   Deploy frontend only"
      echo "  --skip-frontend  Deploy backend only"
      exit 0
      ;;
    *)
      log_error "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

# Track what we deployed for rollback
BACKEND_DEPLOYED=false
FRONTEND_DEPLOYED=false

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

# Run command on VPS
vps_exec() {
  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN]${NC} ssh → $*"
    return 0
  fi
  eval "${SSH_CMD} '$*'"
}

# Health check with retries
check_health() {
  local url="$1"
  local label="$2"
  local retries="${3:-10}"
  local delay="${4:-5}"

  log_info "Checking ${label} health at ${url} ..."

  for i in $(seq 1 "$retries"); do
    # Use curl locally for backend, or via VPS for frontend
    local result=0
    if [[ "$url" == "https://"* ]]; then
      # Remote check via VPS
      vps_exec "curl -fsSL --max-time 10 '${url}' > /dev/null 2>&1" || result=$?
    else
      # Local check
      curl -fsSL --max-time 10 "$url" > /dev/null 2>&1 || result=$?
    fi

    if [ "$result" -eq 0 ]; then
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

# Full health check suite
full_health_check() {
  log_substep "Running Full Health Check Suite"

  local all_passed=true

  # Backend health (local)
  if [ "$SKIP_BACKEND" = false ]; then
    if ! check_health "$BACKEND_HEALTH_URL" "Backend (local)" 5 3; then
      all_passed=false
    fi
  fi

  # Frontend health (via VPS)
  if [ "$SKIP_FRONTEND" = false ]; then
    if ! check_health "$FRONTEND_HEALTH_URL" "Frontend (public)" 5 5; then
      all_passed=false
    fi
  fi

  # Cross-check: VPS can reach backend through WireGuard
  if [ "$SKIP_BACKEND" = false ]; then
    log_info "Verifying VPS-to-Homelab connectivity (WireGuard) ..."
    if vps_exec "curl -fsSL --max-time 10 '${VPS_BACKEND_HEALTH_URL}' > /dev/null 2>&1"; then
      log_success "VPS can reach backend through WireGuard"
    else
      log_warn "VPS cannot reach backend through WireGuard — API calls may fail"
      all_passed=false
    fi
  fi

  if [ "$all_passed" = true ]; then
    log_success "All health checks passed"
    return 0
  else
    log_error "Some health checks failed"
    return 1
  fi
}

# Rollback everything that was deployed
rollback_all() {
  log_step "Rolling Back All Deployed Services"
  local any_failed=false

  if [ "$FRONTEND_DEPLOYED" = true ] || [ "$SKIP_FRONTEND" = false ]; then
    log_substep "Rolling back frontend"
    if bash "$DEPLOY_FRONTEND" --rollback; then
      log_success "Frontend rollback complete"
    else
      log_error "Frontend rollback failed"
      any_failed=true
    fi
  fi

  if [ "$BACKEND_DEPLOYED" = true ] || [ "$SKIP_BACKEND" = false ]; then
    log_substep "Rolling back backend"
    if bash "$DEPLOY_BACKEND" --rollback; then
      log_success "Backend rollback complete"
    else
      log_error "Backend rollback failed"
      any_failed=true
    fi
  fi

  if [ "$any_failed" = true ]; then
    log_error "One or more rollbacks failed — manual intervention required"
    return 1
  fi

  log_success "All rollbacks completed successfully"
  return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  echo ""
  echo -e "${BOLD}============================================${NC}"
  echo -e "${BOLD}  Flowmanner Full Stack Deployment${NC}"
  echo -e "${BOLD}============================================${NC}"
  echo ""

  if [ "$DRY_RUN" = true ]; then
    log_warn "DRY-RUN MODE — no changes will be made"
  fi
  if [ "$MIGRATE" = true ]; then
    log_info "Migrations: ENABLED"
  fi
  if [ "$SKIP_BACKEND" = true ]; then
    log_info "Skipping: Backend"
  fi
  if [ "$SKIP_FRONTEND" = true ]; then
    log_info "Skipping: Frontend"
  fi
  echo ""

  # -- Rollback mode --
  if [ "$ROLLBACK" = true ]; then
    rollback_all
    exit $?
  fi

  # -- Pre-deploy baseline --
  log_step "Pre-Deploy Baseline"
  full_health_check || log_warn "Baseline health checks had failures — proceeding"

  # -- Deploy Backend --
  if [ "$SKIP_BACKEND" = false ]; then
    log_step "Phase 1: Backend Deployment"

    local backend_args=""
    if [ "$DRY_RUN" = true ]; then backend_args+=" --dry-run"; fi
    if [ "$MIGRATE" = true ];  then backend_args+=" --migrate"; fi

    if bash "$DEPLOY_BACKEND" $backend_args; then
      BACKEND_DEPLOYED=true
      log_success "Backend deployment complete"
    else
      log_error "Backend deployment failed"
      log_error "Aborting — frontend will not be deployed"
      exit 1
    fi

    # Brief pause for backend to stabilize before frontend deploy
    if [ "$DRY_RUN" = false ]; then
      log_info "Waiting 5s for backend to stabilize ..."
      sleep 5
    fi
  fi

  # -- Deploy Frontend --
  if [ "$SKIP_FRONTEND" = false ]; then
    log_step "Phase 2: Frontend Deployment"

    local frontend_args=""
    if [ "$DRY_RUN" = true ]; then frontend_args+=" --dry-run"; fi

    if bash "$DEPLOY_FRONTEND" $frontend_args; then
      FRONTEND_DEPLOYED=true
      log_success "Frontend deployment complete"
    else
      log_error "Frontend deployment failed"
      log_error "Initiating rollback of all deployed services"
      rollback_all
      exit 1
    fi
  fi

  # -- Post-deploy full health check --
  log_step "Post-Deploy Verification"
  if ! full_health_check; then
    log_error "Post-deploy health checks failed — initiating rollback"
    rollback_all
    exit 1
  fi

  # -- Summary --
  echo ""
  echo -e "${GREEN}${BOLD}============================================${NC}"
  echo -e "${GREEN}${BOLD}  Full Stack Deployment Complete${NC}"
  echo -e "${GREEN}${BOLD}============================================${NC}"
  echo ""

  if [ "$SKIP_BACKEND" = false ]; then
    echo -e "  Backend:  ${GREEN}deployed${NC}  → http://localhost:8000/health"
  fi
  if [ "$SKIP_FRONTEND" = false ]; then
    echo -e "  Frontend: ${GREEN}deployed${NC}  → https://flowmanner.com"
  fi
  echo ""
}

main "$@"
