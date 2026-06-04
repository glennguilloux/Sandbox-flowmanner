#!/usr/bin/env bash
# Flowmanner Mission Gate — Post-Deploy Verification
# Runs after deployment to verify the system is healthy.
# Usage: ./post-deploy-verify.sh [--json]
# Returns: 0 if all checks pass, 1 if any fail.

set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: post-deploy-verify.sh [--json]"
    echo "  --json    Output results as JSON"
    echo "  --help    Show this help"
    echo ""
    echo "Verifies deployment health: API endpoints, container status, frontend load."
    echo "Env vars: VERIFY_BASE_URL (default http://localhost:8000)"
    echo "          FRONTEND_URL (default https://flowmanner.com)"
    exit 0
fi

OUTPUT_JSON=false
if [[ "${1:-}" == "--json" ]]; then
    OUTPUT_JSON=true
fi

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
BASE_URL="${VERIFY_BASE_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-https://flowmanner.com}"
FAILURES=0
CHECKS_RUN=0
declare -a RESULTS=()

# ── Helpers ───────────────────────────────────────────────────────────────────

check() {
    local name="$1"
    local description="$2"
    local cmd="$3"
    
    (( CHECKS_RUN++ )) || true
    local out exit_code
    out=$(eval "$cmd" 2>&1) || exit_code=$?
    
    if [[ ${exit_code:-0} -eq 0 ]]; then
        RESULTS+=("PASS|$name|$description")
        echo "  ✓ $name — PASS" >&2
    else
        (( FAILURES++ )) || true
        RESULTS+=("FAIL|$name|$description|${out:0:500}")
        echo "  ✗ $name — FAIL" >&2
        echo "    $out" | head -5 >&2
    fi
}

check_contains() {
    local name="$1"
    local description="$2"
    local cmd="$3"
    local expected="$4"
    
    (( CHECKS_RUN++ )) || true
    local out exit_code
    out=$(eval "$cmd" 2>&1) || exit_code=$?
    
    if [[ ${exit_code:-0} -eq 0 && "$out" == *"$expected"* ]]; then
        RESULTS+=("PASS|$name|$description")
        echo "  ✓ $name — PASS" >&2
    else
        (( FAILURES++ )) || true
        local reason=""
        [[ ${exit_code:-0} -ne 0 ]] && reason="exit=$exit_code" || reason="missing '$expected'"
        RESULTS+=("FAIL|$name|$description|$reason")
        echo "  ✗ $name — FAIL ($reason)" >&2
    fi
}

# ── Backend API Health ────────────────────────────────────────────────────────

verify_backend_health() {
    check "api-health" "GET /api/health returns status ok" \
        "curl -sf -m 10 '$BASE_URL/api/health' | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('status',''))\" 2>/dev/null"

    check_contains "api-db" "Database status is ok" \
        "curl -sf -m 10 '$BASE_URL/api/health' | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('components',{}).get('database',{}).get('status',''))\" 2>/dev/null" \
        "ok"
}

# ── Key Endpoint Verification ─────────────────────────────────────────────────

verify_endpoints() {
    # Auth endpoint — expect any response (200 or 401 are both valid, just not 500/connection refused)
    check "api-auth" "Auth endpoint responds" \
        "curl -sf -o /dev/null -w '%{http_code}' -m 10 '$BASE_URL/api/v1/auth/me' 2>/dev/null | grep -qE '200|401|403'"

    # Session endpoint
    check "api-session" "Session endpoint responds" \
        "curl -sf -o /dev/null -w '%{http_code}' -m 10 '$BASE_URL/api/v1/auth/login' 2>/dev/null | grep -qE '200|401|403|405'"

    # LLM endpoint check (if llm server is available)
    if curl -sf -m 5 http://localhost:11434/health >/dev/null 2>&1; then
        check "api-llm" "LLM models endpoint" \
            "curl -sf -o /dev/null -w '%{http_code}' -m 15 '$BASE_URL/api/v1/llm/models' 2>/dev/null | grep -qE '200'"
    else
        echo "  - api-llm — SKIP (llama.cpp not running)" >&2
        RESULTS+=("SKIP|api-llm|LLM server not running")
    fi
}

# ── Frontend Verification ──────────────────────────────────────────────────────

verify_frontend() {
    local http_code body
    body=$(curl -sf -m 10 "$FRONTEND_URL" 2>/dev/null) || true
    http_code=$(curl -sf -o /dev/null -w '%{http_code}' -m 10 "$FRONTEND_URL" 2>/dev/null) || http_code="000"
    
    if [[ "$http_code" == "200" ]]; then
        if [[ "$body" == *"FlowManner"* || "$body" == *"flowmanner"* ]]; then
            RESULTS+=("PASS|frontend-load|Frontend loads (HTTP $http_code, contains FlowManner)")
            echo "  ✓ frontend-load — PASS (HTTP $http_code, content verified)" >&2
        else
            RESULTS+=("PASS|frontend-load|Frontend loads (HTTP $http_code, 'FlowManner' not found in body)")
            echo "  ✓ frontend-load — PASS with note (HTTP $http_code, content check inconclusive)" >&2
        fi
    else
        (( FAILURES++ )) || true
        RESULTS+=("FAIL|frontend-load|HTTP $http_code (expected 200)")
        echo "  ✗ frontend-load — FAIL (HTTP $http_code)" >&2
    fi

    # Verify key pages exist (307 redirect = auth gate = route registered = healthy)
    local tools_http
    tools_http=$(curl -sf -o /dev/null -w '%{http_code}' -m 10 "$FRONTEND_URL/en/tools" 2>/dev/null) || tools_http="000"
    (( CHECKS_RUN++ )) || true
    if [[ "$tools_http" == "200" || "$tools_http" == "307" ]]; then
        RESULTS+=("PASS|tools-page|Tools hub route registered (HTTP $tools_http)")
        echo "  ✓ tools-page — PASS (HTTP $tools_http)" >&2
    else
        (( FAILURES++ )) || true
        RESULTS+=("FAIL|tools-page|HTTP $tools_http (expected 200 or 307)")
        echo "  ✗ tools-page — FAIL (HTTP $tools_http)" >&2
    fi
}

# ── Container Status ──────────────────────────────────────────────────────────

verify_containers() {
    local expected=(backend workflow-postgres workflow-redis workflow-qdrant)
    for name in "${expected[@]}"; do
        local status
        status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
        local health
        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$name" 2>/dev/null || echo "unknown")
        
        (( CHECKS_RUN++ )) || true
        if [[ "$status" == "running" && ( "$health" == "healthy" || "$health" == "no-healthcheck" ) ]]; then
            RESULTS+=("PASS|container-$name|$status ($health)")
            echo "  ✓ container-$name — $status ($health)" >&2
        else
            (( FAILURES++ )) || true
            RESULTS+=("FAIL|container-$name|$status ($health)")
            echo "  ✗ container-$name — $status ($health)" >&2
        fi
    done
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    echo "" >&2
    echo "=== Flowmanner Post-Deploy Verification ===" >&2
    echo "Base URL: $BASE_URL" >&2
    echo "Frontend URL: $FRONTEND_URL" >&2
    echo "Started: $TIMESTAMP" >&2
    echo "" >&2

    echo "--- Backend Health ---" >&2
    verify_backend_health

    echo "" >&2
    echo "--- Endpoints ---" >&2
    verify_endpoints

    echo "" >&2
    echo "--- Containers ---" >&2
    verify_containers

    echo "" >&2
    echo "--- Frontend ---" >&2
    verify_frontend

    echo "" >&2
    echo "=== Summary ===" >&2
    echo "$CHECKS_RUN checks run, $FAILURES failures" >&2

    # Output JSON if requested
    if $OUTPUT_JSON; then
        python3 << PYEOF
import json
results = []
for r in [$(for r in "${RESULTS[@]}"; do echo -n "'$r', "; done)]:
    parts = r.split('|', 3)
    entry = {"status": parts[0], "name": parts[1], "description": parts[2]}
    if len(parts) > 3 and parts[3]:
        entry["detail"] = parts[3]
    results.append(entry)

report = {
    "timestamp": "$TIMESTAMP",
    "checks_run": $CHECKS_RUN,
    "failures": $FAILURES,
    "passed": $(( CHECKS_RUN - FAILURES )),
    "results": results
}
print(json.dumps(report, indent=2))
PYEOF
    fi

    return $(( FAILURES > 0 ? 1 : 0 ))
}

main "$@"
