#!/usr/bin/env bash
# Flowmanner Mission Gate — Pre-Flight Baseline Check
# Captures current state and runs baseline validations.
# Usage: ./pre-flight.sh [--json]
# Outputs a baseline report to stdout.

set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: pre-flight.sh [--json]"
    echo "  --json    Output report as JSON"
    echo "  --help    Show this help"
    echo ""
    echo "Captures git state, runs TypeScript typecheck, Python syntax check,"
    echo "backend tests, and service health checks. Use before making any edits."
    exit 0
fi

OUTPUT_JSON=false
if [[ "${1:-}" == "--json" ]]; then
    OUTPUT_JSON=true
fi

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_ROOT="/home/glenn/FlowmannerV2-frontend"
REPORT_DIR="$PROJECT_ROOT/.mission-gate"
REPORT_FILE="$REPORT_DIR/pre-flight-report.json"

# Accumulate results as simple key|value|status lines for safe JSON construction
declare -a RESULT_LINES=()
FAILURES=0
CHECKS_RUN=0

# ── Helpers ───────────────────────────────────────────────────────────────────

record() {
    local key="$1" value="$2" status="${3:-info}"
    RESULT_LINES+=("${key}|${value}|${status}")
    (( CHECKS_RUN++ )) || true
    [[ "$status" == "fail" ]] && { (( FAILURES++ )) || true; } || true
    echo "${key}=${value}"
}

# ── State capture ─────────────────────────────────────────────────────────────

capture_git_state() {
    pushd "$PROJECT_ROOT" >/dev/null
    local git_commit git_branch git_diff_count git_untracked
    git_commit=$(git rev-parse HEAD 2>/dev/null || echo "no-git")
    git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "no-git")
    git_diff_count=$(git diff --stat 2>/dev/null | tail -1 | awk '{print $1}' || echo "0")
    git_untracked=$(git ls-files --others --exclude-standard 2>/dev/null | wc -l || echo "0")
    popd >/dev/null

    record "git_commit" "$git_commit"
    record "git_branch" "$git_branch"
    record "git_diff_count" "$git_diff_count"
    record "git_untracked" "$git_untracked"
}

# ── Container status ──────────────────────────────────────────────────────────

check_containers() {
    local containers
    containers=$(docker ps --format '{{.Names}}:{{.Status}}' 2>/dev/null || echo "")
    if [[ -z "$containers" ]]; then
        record "containers" "none" "warn"
        return 0
    fi
    local -a statuses
    while IFS= read -r line; do
        local name="${line%%:*}"
        local status="${line#*:}"
        if [[ "$status" != *"Up"* ]] && [[ "$status" != *"healthy"* ]]; then
            statuses+=("$name=DOWN")
        else
            statuses+=("$name=UP")
        fi
    done <<< "$containers"
    record "containers" "${statuses[*]}"
}

# ── Service health ────────────────────────────────────────────────────────────

check_service_health() {
    local health_out
    if health_out=$(curl -sf -m 5 http://127.0.0.1:8000/api/health 2>&1); then
        record "api_health" "PASS"
        local db_status
        db_status=$(echo "$health_out" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(d.get('components',{}).get('database',{}).get('status','unknown'))" 2>/dev/null || echo "parse_error")
        record "api_db_status" "$db_status"
    else
        record "api_health" "FAIL" "fail"
    fi
}

check_llm_health() {
    if curl -sf -m 5 http://localhost:11434/health >/dev/null 2>&1; then
        record "llm_health" "PASS"
    else
        record "llm_health" "NOT_RUNNING" "warn"
    fi
}

# ── Frontend checks ───────────────────────────────────────────────────────────

check_frontend_tsc() {
    if [[ ! -d "$FRONTEND_ROOT" ]]; then
        record "frontend_tsc" "skipped (no frontend dir)" "skip"
        return 0
    fi
    if [[ ! -x "$FRONTEND_ROOT/node_modules/.bin/tsc" ]]; then
        record "frontend_tsc" "skipped (tsc not found)" "skip"
        return 0
    fi

    local tsc_out tsc_rc
    pushd "$FRONTEND_ROOT" >/dev/null
    if tsc_out=$(npx tsc --noEmit 2>&1); then
        popd >/dev/null
        record "frontend_tsc" "PASS"
    else
        tsc_rc=$?
        popd >/dev/null
        local err_count
        err_count=$(echo "$tsc_out" | grep -c "error TS" || echo "0")
        record "frontend_tsc" "FAIL ($err_count errors)" "fail"
        record "frontend_tsc_detail" "$(echo "$tsc_out" | tail -20)"
    fi
}

check_frontend_lint() {
    if [[ ! -d "$FRONTEND_ROOT" ]]; then
        record "frontend_lint" "skipped (no frontend dir)" "skip"
        return 0
    fi

    local lint_out
    pushd "$FRONTEND_ROOT" >/dev/null
    if lint_out=$(npx eslint . --max-warnings 999 2>&1); then
        popd >/dev/null
        record "frontend_lint" "PASS"
    else
        popd >/dev/null
        local err_count
        err_count=$(echo "$lint_out" | grep -c "error" || echo "0")
        local warn_count
        warn_count=$(echo "$lint_out" | grep -c "warning" || echo "0")
        if [[ $err_count -eq 0 ]]; then
            record "frontend_lint" "PASS ($warn_count warnings)"
        else
            record "frontend_lint" "FAIL ($err_count errors, $warn_count warnings)" "fail"
        fi
    fi
}

# ── Backend checks ────────────────────────────────────────────────────────────

check_backend_py_compile() {
    local backend_dir="$PROJECT_ROOT/backend"
    if [[ ! -d "$backend_dir/app" ]]; then
        record "backend_compile" "skipped (no backend dir)" "skip"
        return 0
    fi

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^backend$'; then
        if docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T backend \
            python -m compileall -q /app/app 2>&1; then
            record "backend_compile" "PASS (container)"
        else
            record "backend_compile" "FAIL" "fail"
        fi
    else
        if python3 -m compileall -q "$backend_dir/app" 2>&1; then
            record "backend_compile" "PASS (local)"
        else
            record "backend_compile" "FAIL" "fail"
        fi
    fi
}

check_backend_tests() {
    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^backend$'; then
        record "backend_tests" "skipped (backend container not running)" "skip"
        return 0
    fi
    local test_out
    if test_out=$(docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T backend \
        python -m pytest --tb=short -x -q 2>&1); then
        record "backend_tests" "PASS"
    else
        local fail_count
        fail_count=$(echo "$test_out" | grep -c "FAILED\|ERROR" || echo "0")
        record "backend_tests" "FAIL ($fail_count failures)" "fail"
        record "backend_tests_detail" "$(echo "$test_out" | tail -20)"
    fi
}

# ── Output ────────────────────────────────────────────────────────────────────

output_json() {
    mkdir -p "$REPORT_DIR"

    # Build JSON safely: pipe key|value|status lines to Python via stdin
    # Pass metadata as argv to avoid shell injection into Python code
    local py_script
    py_script=$(cat << 'PYEOF'
import sys, json

results = {}
for line in sys.stdin:
    line = line.strip()
    if '|' not in line:
        continue
    parts = line.split('|', 2)
    key = parts[0]
    value = parts[1]
    status = parts[2] if len(parts) > 2 else "info"
    results[key] = {"value": value, "status": status}

report = {
    "timestamp": sys.argv[1],
    "hostname": sys.argv[2],
    "checks_run": int(sys.argv[3]),
    "failures": int(sys.argv[4]),
    "passed": int(sys.argv[3]) - int(sys.argv[4]),
    "results": results
}
print(json.dumps(report, indent=2))
PYEOF
)
    printf '%s\n' "${RESULT_LINES[@]}" | python3 -c "$py_script" "$TIMESTAMP" "$(cat /etc/hostname 2>/dev/null || uname -n 2>/dev/null || echo 'unknown')" "$CHECKS_RUN" "$FAILURES"
}

output_text() {
    echo "=== Flowmanner Pre-Flight Report ==="
    echo "timestamp=$TIMESTAMP"
    echo "hostname=$(cat /etc/hostname 2>/dev/null || uname -n 2>/dev/null || echo 'unknown')"
    echo "checks_run=$CHECKS_RUN"
    echo "failures=$FAILURES"
    echo "passed=$(( CHECKS_RUN - FAILURES ))"
    echo "---"
    for line in "${RESULT_LINES[@]}"; do
        local key="${line%%|*}"
        local rest="${line#*|}"
        local value="${rest%|*}"
        echo "${key}=${value}"
    done
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    echo "Running pre-flight checks..." >&2

    capture_git_state
    check_containers
    check_service_health
    check_llm_health
    check_frontend_tsc
    check_frontend_lint
    check_backend_py_compile
    check_backend_tests

    if $OUTPUT_JSON; then
        output_json | tee "$REPORT_FILE"
    else
        output_text
    fi

    echo "" >&2
    echo "Pre-flight complete: $CHECKS_RUN checks, $FAILURES failures" >&2
    return $FAILURES
}

main
