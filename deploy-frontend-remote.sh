#!/bin/bash
# =============================================================================
# Flowmanner Frontend Remote Deploy Trigger
# =============================================================================
# Runs on:    172.16.1.2 (ops/dev machine)
# Triggers:   /opt/flowmanner/deploy-frontend.sh on 172.16.1.1 (homelab)
#             which in turn deploys the frontend to the VPS (74.208.115.142)
#
# Usage:
#   ./deploy-frontend-remote.sh              # Normal deploy (~4 min)
#   ./deploy-frontend-remote.sh --dry-run    # Preview without executing
#   ./deploy-frontend-remote.sh --rollback   # Revert to previous version
#
# Prerequisites:
#   SSH key auth from this machine to homelab (passwordless)
#   ssh glenn@172.16.1.1 must work without password
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HOMELAB_HOST="${HOMELAB_HOST:-172.16.1.1}"
HOMELAB_USER="${HOMELAB_USER:-glenn}"
DEPLOY_SCRIPT="/opt/flowmanner/deploy-frontend.sh"

SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ServerAliveInterval=30"

# ---------------------------------------------------------------------------
# Colors & Output
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------
check_connection() {
    if ! ssh -q $SSH_OPTS -o ConnectTimeout=5 "${HOMELAB_USER}@${HOMELAB_HOST}" "echo ok" 2>/dev/null; then
        echo -e "${RED}[ERROR]${NC} Cannot reach homelab at ${HOMELAB_USER}@${HOMELAB_HOST}"
        echo "Check: ssh ${HOMELAB_USER}@${HOMELAB_HOST}"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║     Flowmanner Frontend Remote Deploy               ║${NC}"
echo -e "${CYAN}${BOLD}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}${BOLD}║  This machine  →  Homelab  →  VPS (flowmanner.com)  ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

check_connection
echo -e "${GREEN}[OK]${NC} Homelab reachable at ${HOMELAB_USER}@${HOMELAB_HOST}"
echo ""

echo -e "${YELLOW}⏳ Deploy starting — this will take ~4 minutes...${NC}"
echo -e "${YELLOW}   Watch the output below for progress.${NC}"
echo ""
echo -e "${BOLD}───────────────────────────────────────────────────────${NC}"
echo ""

# Build remote command with proper argument escaping
local remote_cmd="bash ${DEPLOY_SCRIPT}"
for arg in "$@"; do
    printf -v quoted '%q' "$arg"
    remote_cmd="${remote_cmd} ${quoted}"
done

# Run the deploy script on the homelab, streaming output in real-time
# Use ssh -t to allocate a PTY so colors and progress bars work
# Temporarily disable set -e so we can capture the exit code and show the banner
set +e
ssh -t $SSH_OPTS "${HOMELAB_USER}@${HOMELAB_HOST}" "$remote_cmd" 2>&1
DEPLOY_EXIT=$?
set -e

echo ""
echo -e "${BOLD}───────────────────────────────────────────────────────${NC}"
echo ""

if [ "$DEPLOY_EXIT" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║  ✅  DEPLOY SUCCEEDED                               ║${NC}"
    echo -e "${GREEN}${BOLD}║  flowmanner.com is now running the new frontend      ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${RED}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}${BOLD}║  ❌  DEPLOY FAILED (exit: ${DEPLOY_EXIT})                        ║${NC}"
    echo -e "${RED}${BOLD}║  Check output above for details.                     ║${NC}"
    echo -e "${RED}${BOLD}║  Auto-rollback may have run — verify on homelab.     ║${NC}"
    echo -e "${RED}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
fi

echo ""
exit $DEPLOY_EXIT
