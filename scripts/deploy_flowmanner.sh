#!/bin/bash
# =============================================================================
# deploy_flowmanner.sh — FlowManner Production Deployment Orchestrator
# =============================================================================
# Usage:
#   ./deploy_flowmanner.sh                           # Full deploy (frontend + backend)
#   ./deploy_flowmanner.sh --frontend-only           # Deploy frontend only
#   ./deploy_flowmanner.sh --backend-only            # Deploy backend only
#   ./deploy_flowmanner.sh --skip-smoke              # Skip post-deploy smoke tests
#   ./deploy_flowmanner.sh --dry-run                 # Preview without executing
#   ./deploy_flowmanner.sh --frontend-only --skip-smoke --dry-run
#
# Exit codes:
#   0  — All checks passed, deploy succeeded
#   1  — Preflight failed
#   2  — Frontend deploy failed
#   3  — Backend deploy failed
#   4  — Smoke check failed
#   5  — Timeout
#   6  — Missing dependency
# =============================================================================

set -Eeuo pipefail

# ── Timestamped logging ───────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

_ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log_start()  { echo -e "${CYAN}[$(_ts)] START${NC} $*"; }
log_pass()   { echo -e "${GREEN}[$(_ts)] PASS${NC}  $*"; }
log_fail()   { echo -e "${RED}[$(_ts)] FAIL${NC}  $*"; }
log_info()   { echo -e "         ${BOLD}$*${NC}"; }
log_step()   { echo -e "\n${CYAN}${BOLD}>>> $*${NC}"; }

die() { local msg="$1"; local code="${2:-1}"; log_fail "$msg"; exit "$code"; }

# ── Configuration ─────────────────────────────────────────────────────────────

FRONTEND_SOURCE="/home/glenn/FlowmannerV2-frontend"
BACKEND_SOURCE="/opt/flowmanner/backend"
PROJECT_ROOT="/opt/flowmanner"
FRONTEND_DEPLOY_SCRIPT="${PROJECT_ROOT}/deploy-frontend.sh"
BACKEND_DEPLOY_CMD="docker build -t workflows-backend:restored ${BACKEND_SOURCE}/ && cd ${PROJECT_ROOT} && docker compose up -d --no-deps --force-recreate backend"
SMOKE_SCRIPT="${PROJECT_ROOT}/scripts/smoke_flowmanner.sh"
VPS_SSH=(ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 root@74.208.115.142)
DEPLOY_TIMEOUT=300

# ── Flags ─────────────────────────────────────────────────────────────────────

FRONTEND_ONLY=false
BACKEND_ONLY=false
SKIP_SMOKE=false
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: deploy_flowmanner.sh [FLAGS]

Flags:
  --frontend-only      Deploy frontend only (skip backend)
  --backend-only       Deploy backend only (skip frontend)
  --skip-smoke         Skip post-deploy smoke tests
  --dry-run            Preview actions without executing
  --help               Show this message

Examples:
  ./deploy_flowmanner.sh                            # Full deploy
  ./deploy_flowmanner.sh --frontend-only            # Frontend only
  ./deploy_flowmanner.sh --backend-only --skip-smoke # Backend only, no smoke
  ./deploy_flowmanner.sh --dry-run                  # Preview everything

Exit codes: 0=success, 1=preflight, 2=frontend, 3=backend, 4=smoke, 5=timeout, 6=dependency
EOF
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --frontend-only) FRONTEND_ONLY=true ;;
    --backend-only)  BACKEND_ONLY=true ;;
    --skip-smoke)    SKIP_SMOKE=true ;;
    --dry-run)       DRY_RUN=true ;;
    --help|-h)       usage ;;
    *) die "Unknown argument: $arg (use --help)" 6 ;;
  esac
done

if $FRONTEND_ONLY && $BACKEND_ONLY; then
  die "--frontend-only and --backend-only are mutually exclusive" 6
fi

# ── Command existence checks ──────────────────────────────────────────────────

_require() {
  local cmd="$1"
  if ! command -v "$cmd" &>/dev/null; then
    die "Missing required command: '$cmd' — please install it" 6
  fi
}

check_dependencies() {
  log_start "Checking dependencies"
  local ok=true
  for cmd in ssh curl docker timeout bash grep awk; do
    if command -v "$cmd" &>/dev/null; then
      log_info "✓ $cmd"
    else
      log_fail "✗ $cmd (missing)"
      ok=false
    fi
  done
  if ! $ok; then die "Missing dependencies — cannot continue" 6; fi
  log_pass "All dependencies present"
}

# ── Helper ────────────────────────────────────────────────────────────────────

_vps() {
  if $DRY_RUN; then
    echo -e "${YELLOW}[DRY-RUN]${NC} VPS → $*"
    return 0
  fi
  timeout 60 "${VPS_SSH[@]}" "$@"
}

_homelab_docker() {
  if $DRY_RUN; then
    echo -e "${YELLOW}[DRY-RUN]${NC} docker compose → $*"
    return 0
  fi
  docker compose -f "${PROJECT_ROOT}/docker-compose.yml" "$@"
}

# ── Preflight ─────────────────────────────────────────────────────────────────

preflight() {
  log_step "PREFLIGHT CHECKS"

  # 1. Backend container running
  log_start "Backend container"
  if $DRY_RUN || docker ps --filter name=backend --filter status=running -q | grep -q .; then
    log_pass "Backend container running"
  else
    die "Backend container is DOWN — cannot deploy" 1
  fi

  # 2. Backend health endpoint
  log_start "Backend health"
  if $DRY_RUN || curl -sf --max-time 10 http://localhost:8000/health >/dev/null; then
    log_pass "Backend health OK"
  else
    die "Backend health endpoint unreachable" 1
  fi

  # 3. Infrastructure containers
  for svc in workflow-postgres workflow-redis; do
    log_start "$svc container"
    if $DRY_RUN || docker ps --filter "name=${svc}" --filter status=running -q | grep -q .; then
      log_pass "$svc running"
    else
      die "$svc is DOWN" 1
    fi
  done

  # 4. VPS reachable
  log_start "VPS reachable"
  if $DRY_RUN || "${VPS_SSH[@]}" "echo OK" 2>/dev/null | grep -q OK; then
    log_pass "VPS reachable"
  else
    die "VPS unreachable — check network" 1
  fi

  # 5. WireGuard tunnel
  log_start "WireGuard tunnel"
  if $DRY_RUN || sudo wg show wg0 2>/dev/null | grep -q "latest handshake"; then
    log_pass "WireGuard tunnel active"
  else
    die "WireGuard tunnel DOWN — fix before deploying" 1
  fi

  # 6. Source directories exist
  if ! $BACKEND_ONLY; then
    log_start "Frontend source"
    if [ -d "$FRONTEND_SOURCE" ]; then
      log_pass "Frontend source present"
    else
      die "Frontend source missing at $FRONTEND_SOURCE" 1
    fi
  fi
  if ! $FRONTEND_ONLY; then
    log_start "Backend source"
    if [ -d "$BACKEND_SOURCE" ]; then
      log_pass "Backend source present"
    else
      die "Backend source missing at $BACKEND_SOURCE" 1
    fi
  fi

  # 7. Deploy script / smoke script exist
  if ! $BACKEND_ONLY; then
    log_start "Frontend deploy script"
    if [ -x "$FRONTEND_DEPLOY_SCRIPT" ]; then
      log_pass "Frontend deploy script ready"
    else
      log_fail "Frontend deploy script not found or not executable at $FRONTEND_DEPLOY_SCRIPT"
      log_fail "Manual path available — see DEPLOY-RUNBOOK.md Section B.4"
      die "Frontend deploy script missing" 1
    fi
  fi

  if ! $SKIP_SMOKE; then
    log_start "Smoke script"
    if [ -x "$SMOKE_SCRIPT" ]; then
      log_pass "Smoke script ready"
    else
      die "Smoke script not found or not executable at $SMOKE_SCRIPT" 1
    fi
  fi

  log_pass "All preflight checks passed"
}

# ── Deploy Frontend ───────────────────────────────────────────────────────────

deploy_frontend() {
  log_step "FRONTEND DEPLOY (timeout=${DEPLOY_TIMEOUT}s)"

  if $DRY_RUN; then
    echo -e "${YELLOW}[DRY-RUN]${NC} Would execute: bash ${FRONTEND_DEPLOY_SCRIPT}"
    return 0
  fi

  if ! timeout "$DEPLOY_TIMEOUT" bash "$FRONTEND_DEPLOY_SCRIPT" --skip-precheck; then
    local rc=$?
    if [ "$rc" -eq 124 ]; then
      die "Frontend deploy TIMED OUT after ${DEPLOY_TIMEOUT}s — check VPS manually" 5
    fi
    die "Frontend deploy FAILED (exit code $rc)" 2
  fi

  log_pass "Frontend deploy complete"
}

# ── Deploy Backend ────────────────────────────────────────────────────────────

deploy_backend() {
  log_step "BACKEND DEPLOY (timeout=${DEPLOY_TIMEOUT}s)"

  if $DRY_RUN; then
    echo -e "${YELLOW}[DRY-RUN]${NC} Would execute: $BACKEND_DEPLOY_CMD"
    return 0
  fi

  # Save current image for rollback
  docker tag workflows-backend:restored workflows-backend:backup-current 2>/dev/null || {
    log_info "No existing backend image to tag — first deploy?"
  }

  # Build + deploy with timeout
  if ! timeout "$DEPLOY_TIMEOUT" bash -c "$BACKEND_DEPLOY_CMD"; then
    local rc=$?
    if [ "$rc" -eq 124 ]; then
      die "Backend deploy TIMED OUT after ${DEPLOY_TIMEOUT}s" 5
    fi
    die "Backend deploy FAILED (exit code $rc)" 3
  fi

  # Restart Celery workers (they use the same image tag)
  log_info "Restarting Celery workers (same image, force recreate)..."
  if ! _homelab_docker up -d --no-deps --force-recreate celery-worker celery-beat; then
    log_fail "Celery worker restart failed — tasks may use old code"
  else
    log_pass "Celery workers restarted"
  fi

  # Wait for backend health
  log_start "Waiting for backend health after deploy..."
  for i in $(seq 1 20); do
    if curl -sf --max-time 5 http://localhost:8000/health >/dev/null 2>&1; then
      log_pass "Backend healthy (attempt $i)"
      break
    fi
    if [ "$i" -eq 20 ]; then
      die "Backend health check FAILED after 20 attempts" 3
    fi
    sleep 3
  done

  log_pass "Backend deploy complete"
}

# ── Smoke ─────────────────────────────────────────────────────────────────────

run_smoke() {
  if $SKIP_SMOKE; then
    log_info "Smoke tests SKIPPED (--skip-smoke)"
    return 0
  fi

  log_step "SMOKE TESTS"

  if $DRY_RUN; then
    echo -e "${YELLOW}[DRY-RUN]${NC} Would execute: bash ${SMOKE_SCRIPT}"
    return 0
  fi

  if ! bash "$SMOKE_SCRIPT"; then
    die "Smoke tests FAILED — review output above" 4
  fi
}

# ── Summary ───────────────────────────────────────────────────────────────────

summary() {
  echo ""
  echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}${BOLD}  DEPLOY COMPLETE${NC}"
  echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════════${NC}"
  echo ""
  echo "  Frontend: $($FRONTEND_ONLY && echo 'DEPLOYED' || $BACKEND_ONLY && echo 'SKIPPED' || echo 'DEPLOYED')"
  echo "  Backend:  $($BACKEND_ONLY && echo 'DEPLOYED' || $FRONTEND_ONLY && echo 'SKIPPED' || echo 'DEPLOYED')"
  echo "  Smoke:    $($SKIP_SMOKE && echo 'SKIPPED' || echo 'PASSED')"
  echo "  Mode:     $($DRY_RUN && echo 'DRY-RUN' || echo 'LIVE')"
  echo ""
  echo "  Rollback:  bash ${PROJECT_ROOT}/deploy-backend.sh --rollback"
  echo "             bash ${PROJECT_ROOT}/deploy-frontend.sh --rollback"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
  echo ""
  echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
  echo -e "${BOLD}  FlowManner Production Deploy${NC}"
  echo -e "${BOLD}  Started: $(_ts)${NC}"
  echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
  echo ""

  if $DRY_RUN; then
    echo -e "${YELLOW}${BOLD}⚠ DRY-RUN MODE — no changes will be made${NC}"
    echo ""
  fi

  check_dependencies
  preflight

  if ! $BACKEND_ONLY; then
    deploy_frontend
  fi
  if ! $FRONTEND_ONLY; then
    deploy_backend
  fi

  run_smoke
  summary
}

main "$@"
