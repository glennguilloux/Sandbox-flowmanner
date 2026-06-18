#!/bin/bash
# =============================================================================
# deploy-frontend.sh — Flowmanner Frontend Deployment
# =============================================================================
# Usage:
#   ./deploy-frontend.sh                  # Normal deploy (with precheck)
#   ./deploy-frontend.sh --dry-run        # Preview actions without executing
#   ./deploy-frontend.sh --rollback       # No-op + log: manual revert required
#   ./deploy-frontend.sh --skip-precheck  # Skip precheck (used by orchestrators)
#   ./deploy-frontend.sh --help           # Show usage
#
# Environment:
#   Runs on:        Homelab (local machine)
#   Target:         VPS (rsync + docker build on 74.208.115.142)
#   Precheck gate:  scripts/pre-deploy-check.sh (Wave 2 wired-in)
#
# Rollback (HANDOFF §3.2):
#   The frontend has no image-tag flow. --rollback prints a manual-revert
#   message and exits 0. To actually roll back, revert the last commit in
#   /home/glenn/FlowmannerV2-frontend and re-run without --rollback.
#   See DEPLOY-RUNBOOK.md for details.
# =============================================================================

set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/vps_flowmanner_new}"
VPS_HOST="${VPS_HOST:-74.208.115.142}"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -i $SSH_KEY"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
PRECHECK="$PROJECT_ROOT/scripts/pre-deploy-check.sh"

# ---------------------------------------------------------------------------
# Colors & Output Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[FAIL]${NC}    $*"; }
log_step()    { echo -e "\n${CYAN}${BOLD}>>> $*${NC}"; }
log_dry()     { echo -e "${YELLOW}[DRY-RUN]${NC} $*"; }

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
DRY_RUN=false
ROLLBACK=false
SKIP_PRECHECK=false

usage() {
  cat <<EOF
Usage: $0 [--dry-run] [--rollback] [--skip-precheck] [--help]

Options:
  --dry-run         Preview actions without executing (does NOT call rsync,
                    ssh, scp, or docker build)
  --rollback        No-op: log that manual revert is required, then exit 0.
                    Frontend has no image-tag flow (HANDOFF §3.2).
  --skip-precheck   Skip the pre-deploy gate. Used by orchestrators
                    (deploy-all.sh, scripts/deploy_flowmanner.sh) that have
                    already validated.
  --help, -h        Show this message
EOF
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --dry-run)        DRY_RUN=true ;;
    --rollback)       ROLLBACK=true ;;
    --skip-precheck)  SKIP_PRECHECK=true ;;
    --help|-h)        usage ;;
    *)
      log_error "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Wrap a side-effectful command for dry-run. In DRY_RUN mode, just echo what
# would be done. In LIVE mode, execute normally.
maybe_run() {
  if $DRY_RUN; then
    log_dry "$*"
    return 0
  fi
  "$@"
}

# Run the pre-deploy gate unless --skip-precheck was passed. --rollback does
# not run precheck either (it exits before reaching here).
run_precheck() {
  if $SKIP_PRECHECK; then
    log_info "precheck SKIPPED (--skip-precheck)"
    return 0
  fi
  if [[ ! -x "$PRECHECK" ]]; then
    log_error "precheck not found or not executable at $PRECHECK"
    exit 1
  fi
  log_info "Running precheck: $PRECHECK"
  if ! bash "$PRECHECK"; then
    log_error "precheck FAILED — aborting deploy"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if $ROLLBACK; then
  log_warn "Frontend --rollback is a NO-OP in MVP scope (HANDOFF §3.2)."
  log_warn "The frontend has no image-tag flow."
  log_warn "To roll back: revert the last commit in /home/glenn/FlowmannerV2-frontend"
  log_warn "and re-run without --rollback. See DEPLOY-RUNBOOK.md for details."
  log_success "Frontend rollback marker set (manual action required)."
  exit 0
fi

if $DRY_RUN; then
  log_warn "DRY-RUN MODE — no changes will be made"
fi

run_precheck

log_step "Rsyncing frontend to VPS"
maybe_run rsync -avz --progress --delete \
  -e "ssh $SSH_OPTS" \
  --exclude node_modules --exclude .next --exclude .git \
  /home/glenn/FlowmannerV2-frontend/ \
  root@${VPS_HOST}:/opt/flowmanner/frontend/

log_step "Rebuilding frontend on VPS"
maybe_run ssh $SSH_OPTS root@${VPS_HOST} \
  "cd /opt/flowmanner && docker compose build frontend && docker compose up -d --no-deps frontend"

log_step "Syncing nginx config"
maybe_run ssh $SSH_OPTS root@${VPS_HOST} \
  "mkdir -p /opt/flowmanner/nginx"
maybe_run scp $SSH_OPTS \
  /opt/flowmanner/nginx/default.conf \
  root@${VPS_HOST}:/opt/flowmanner/nginx/default.conf

log_step "Restarting nginx"
maybe_run ssh $SSH_OPTS root@${VPS_HOST} \
  "cd /opt/flowmanner && docker compose restart nginx"

log_success "Frontend deploy complete"
