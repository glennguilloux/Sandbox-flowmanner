#!/usr/bin/env bash
# Flowmanner Mission Gate — Full Validation Pipeline
# Predict Before You Act: validate at every stage.
#
# Usage: ./mission-gate.sh <phase> [options]
#
# Phases:
#   pre-flight   Run baseline checks, capture state, wait for approval
#   post-edit     Validate a single file after edit (requires --file <path>)
#   pre-deploy    Full build + test gate before deployment
#   post-deploy   Verify endpoints and containers after deployment
#   full          Run all phases in sequence
#
# Options:
#   --file <path>      File path for post-edit check
#   --auto-approve     Skip approval prompts (non-interactive mode)
#   --json             Output JSON where applicable
#   --vps              Run frontend checks against VPS (for pre-deploy/post-deploy)
#   --help             Show this help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/.mission-gate/logs"
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

PHASE=""
FILE_PATH=""
AUTO_APPROVE=false
OUTPUT_JSON=false
RUN_VPS=false

# ── Parse args ────────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        pre-flight|post-edit|pre-deploy|post-deploy|full)
            PHASE="$1"
            shift
            ;;
        --file)
            FILE_PATH="$2"
            shift 2
            ;;
        --auto-approve)
            AUTO_APPROVE=true
            shift
            ;;
        --json)
            OUTPUT_JSON=true
            shift
            ;;
        --vps)
            RUN_VPS=true
            shift
            ;;
        --help|-h)
            head -20 "$0" | grep -A 20 "^# "
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

if [[ -z "$PHASE" ]]; then
    echo "ERROR: No phase specified. Use: pre-flight, post-edit, pre-deploy, post-deploy, or full" >&2
    exit 2
fi

mkdir -p "$LOG_DIR"

# ── Helpers ───────────────────────────────────────────────────────────────────

log() {
    local level="$1" msg="$2"
    echo "[$(date '+%H:%M:%S')] [$level] $msg" | tee -a "$LOG_DIR/mission-gate.log"
}

ask_approve() {
    local prompt="$1"
    if $AUTO_APPROVE; then
        log "INFO" "Auto-approving: $prompt"
        return 0
    fi
    echo ""
    echo "────────────────────────────────────────────"
    echo "⛔ APPROVAL REQUIRED: $prompt"
    echo "────────────────────────────────────────────"
    read -r -p "Proceed? [y/N] " response
    if [[ "${response,,}" == "y" || "${response,,}" == "yes" ]]; then
        return 0
    fi
    return 1
}

run_script() {
    local script="$1"
    shift
    local script_path="$SCRIPT_DIR/$script"
    if [[ ! -x "$script_path" ]]; then
        chmod +x "$script_path"
    fi
    bash "$script_path" "$@"
}

# ── VPS access ────────────────────────────────────────────────────────────────

vps_cmd() {
    ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 "$@"
}

# ── Phase 0: Pre-Flight ──────────────────────────────────────────────────────

phase_preflight() {
    log "PHASE" "╔══════════════════════════════════════════╗"
    log "PHASE" "║  PHASE 0: PRE-FLIGHT (Plan Mode)        ║"
    log "PHASE" "╚══════════════════════════════════════════╝"

    # Run the pre-flight script
    log "INFO" "Running pre-flight baseline checks..."
    local preflight_out preflight_exit
    preflight_out=$(run_script "pre-flight.sh" 2>&1) || preflight_exit=$?
    
    echo "$preflight_out"
    
    # Save report
    echo "$preflight_out" > "$LOG_DIR/pre-flight-${TIMESTAMP//:/-}.log"
    
    # Extract key results for summary
    local tsc_result py_result api_result tests_result
    tsc_result=$(echo "$preflight_out" | grep "FRONTEND_TSC=" | head -1 || echo "FRONTEND_TSC=unknown")
    py_result=$(echo "$preflight_out" | grep "BACKEND_COMPILE=" | head -1 || echo "BACKEND_COMPILE=unknown")
    api_result=$(echo "$preflight_out" | grep "API_HEALTH=" | head -1 || echo "API_HEALTH=unknown")
    tests_result=$(echo "$preflight_out" | grep "BACKEND_TESTS=" | head -1 || echo "BACKEND_TESTS=unknown")
    
    echo ""
    echo "── Baseline Summary ──"
    echo "  $tsc_result"
    echo "  $py_result"
    echo "  $api_result"
    echo "  $tests_result"
    echo ""
    
    # Stop and wait for approval
    log "GATE" "Pre-flight complete. Awaiting approval to enter EDIT phase."
    if ask_approve "Pre-flight baseline captured. Proceed with edits?"; then
        log "GATE" "✓ Pre-flight approved. Entering EDIT phase."
        return 0
    else
        log "GATE" "✗ Pre-flight rejected. Aborting mission."
        return 1
    fi
}

# ── Phase 1: Post-Edit ────────────────────────────────────────────────────────

phase_postedit() {
    log "PHASE" "╔══════════════════════════════════════════╗"
    log "PHASE" "║  PHASE 1: POST-EDIT VALIDATION           ║"
    log "PHASE" "╚══════════════════════════════════════════╝"

    if [[ -z "$FILE_PATH" ]]; then
        log "ERROR" "No file specified. Use --file <path>"
        return 2
    fi

    log "INFO" "Validating: $FILE_PATH"
    local check_out check_exit
    check_out=$(run_script "post-edit-check.sh" "$FILE_PATH" 2>&1) || check_exit=$?

    echo "$check_out" >> "$LOG_DIR/post-edit-${TIMESTAMP//:/-}.log"
    echo "$check_out"

    if [[ ${check_exit:-0} -ne 0 ]]; then
        log "FAIL" "Post-edit validation FAILED for $FILE_PATH"
        log "ACTION" "Fix errors before continuing."
        return 1
    fi

    log "PASS" "Post-edit validation passed for $FILE_PATH"
    return 0
}

# ── Phase 2: Pre-Deploy Gate ─────────────────────────────────────────────────

phase_predeploy() {
    log "PHASE" "╔══════════════════════════════════════════╗"
    log "PHASE" "║  PHASE 2: PRE-DEPLOY GATE               ║"
    log "PHASE" "╚══════════════════════════════════════════╝"

    local overall=0

    # 1. Full pre-flight re-run
    log "INFO" "Re-running full baseline checks..."
    run_script "pre-flight.sh" || {
        log "FAIL" "Pre-flight checks failed"
        overall=1
    }

    # 2. Backend Docker build (dry run / check)
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^backend$'; then
        log "INFO" "Checking backend image build..."
        echo "  NOTE: Full docker build skipped in pre-deploy gate."
        echo "  Run manually: docker build -t workflows-backend:restored /opt/flowmanner/backend/"
        echo "  Then: cd /opt/flowmanner && docker compose up -d --no-deps --force-recreate backend"
    fi

    # 3. Frontend build check (if VPS accessible)
    if $RUN_VPS; then
        log "INFO" "Checking frontend build on VPS..."
        if vps_cmd "cd /opt/flowmanner && docker compose ps frontend 2>/dev/null | grep -q frontend" 2>/dev/null; then
            log "INFO" "Frontend container running on VPS"
        else
            log "WARN" "Frontend container not found on VPS"
        fi
    fi

    # 4. API health check
    log "INFO" "Verifying API health..."
    if curl -sf -m 5 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        log "PASS" "API health OK"
    else
        log "FAIL" "API health check failed"
        overall=1
    fi

    echo ""
    log "GATE" "Pre-deploy gate complete."
    
    if [[ $overall -eq 0 ]]; then
        if ask_approve "All pre-deploy checks passed. Proceed with deployment?"; then
            log "GATE" "✓ Deploy approved."
            return 0
        else
            log "GATE" "✗ Deploy rejected. Aborting."
            return 1
        fi
    else
        log "GATE" "✗ Pre-deploy checks have failures. Fix before deploying."
        return 1
    fi
}

# ── Phase 3: Post-Deploy Verification ────────────────────────────────────────

phase_postdeploy() {
    log "PHASE" "╔══════════════════════════════════════════╗"
    log "PHASE" "║  PHASE 3: POST-DEPLOY VERIFICATION      ║"
    log "PHASE" "╚══════════════════════════════════════════╝"

    local json_flag=""
    $OUTPUT_JSON && json_flag="--json"

    log "INFO" "Running post-deploy verification..."
    local verify_out verify_exit
    verify_out=$(run_script "post-deploy-verify.sh" "$json_flag" 2>&1) || verify_exit=$?

    echo "$verify_out" | tee -a "$LOG_DIR/post-deploy-${TIMESTAMP//:/-}.log"

    if [[ ${verify_exit:-0} -ne 0 ]]; then
        log "FAIL" "Post-deploy verification found $verify_exit failures"
        return 1
    fi

    log "PASS" "Post-deploy verification complete — all checks passed."
    return 0
}

# ── Full pipeline ─────────────────────────────────────────────────────────────

phase_full() {
    log "PHASE" "╔══════════════════════════════════════════╗"
    log "PHASE" "║  FULL MISSION GATE PIPELINE             ║"
    log "PHASE" "╚══════════════════════════════════════════╝"

    local gates=("pre-flight" "pre-deploy" "post-deploy")
    local strict=true

    for gate in "${gates[@]}"; do
        echo ""
        echo "════════════════════════════════════════════"
        echo "  RUNNING: $gate"
        echo "════════════════════════════════════════════"

        case "$gate" in
            pre-flight)
                phase_preflight || {
                    log "ABORT" "Pre-flight failed. Stopping pipeline."
                    return 1
                }
                ;;
            pre-deploy)
                phase_predeploy || {
                    log "ABORT" "Pre-deploy gate failed. Stopping pipeline."
                    return 1
                }
                ;;
            post-deploy)
                phase_postdeploy || {
                    log "WARN" "Post-deploy verification found issues."
                    return 1
                }
                ;;
        esac
    done

    echo ""
    log "PASS" "════════════════════════════════════════════"
    log "PASS" "  MISSION GATE PIPELINE COMPLETE — ALL CLEAR"
    log "PASS" "════════════════════════════════════════════"
    return 0
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "$PHASE" in
    pre-flight)   phase_preflight ;;
    post-edit)    phase_postedit ;;
    pre-deploy)   phase_predeploy ;;
    post-deploy)  phase_postdeploy ;;
    full)         phase_full ;;
    *)            echo "Unknown phase: $PHASE"; exit 2 ;;
esac
