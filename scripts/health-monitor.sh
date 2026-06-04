#!/usr/bin/env bash
# Flowmanner Health Monitor — cron-based container & service health checks
# Usage: ./health-monitor.sh [--alert-only]
# Cron:  */5 * * * * /opt/flowmanner/scripts/health-monitor.sh --alert-only >> /var/log/flowmanner-health.log 2>&1

set -euo pipefail

ALERT_ONLY="${1:-}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
ALERTS=()

# ── Container health ──────────────────────────────────────────────────────────
check_containers() {
    local expected=("backend" "workflow-postgres" "workflow-redis" "workflow-qdrant")
    for name in "${expected[@]}"; do
        status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$name" 2>/dev/null || echo "unknown")
        if [[ "$status" != "running" ]]; then
            ALERTS+=("CRITICAL: Container $name is $status")
        elif [[ "$health" == "unhealthy" ]]; then
            ALERTS+=("WARNING: Container $name is unhealthy")
        fi
    done
}

# ── Backend API ───────────────────────────────────────────────────────────────
check_backend() {
    local response
    response=$(curl -sf -m 5 http://127.0.0.1:8000/api/health 2>/dev/null) || {
        ALERTS+=("CRITICAL: Backend API unreachable")
        return
    }
    local db_status
    db_status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['components']['database']['status'])" 2>/dev/null || echo "parse_error")
    if [[ "$db_status" != "ok" ]]; then
        ALERTS+=("CRITICAL: Database status is $db_status")
    fi
}

# ── LLM server ───────────────────────────────────────────────────────────────
check_llm() {
    if ! curl -sf -m 5 http://localhost:11434/health >/dev/null 2>&1; then
        ALERTS+=("WARNING: llama.cpp server unreachable")
    fi
}

# ── Disk space ────────────────────────────────────────────────────────────────
check_disk() {
    local usage
    usage=$(df / --output=pcent | tail -1 | tr -d ' %')
    if (( usage >= 90 )); then
        ALERTS+=("CRITICAL: Root disk usage at ${usage}%")
    elif (( usage >= 80 )); then
        ALERTS+=("WARNING: Root disk usage at ${usage}%")
    fi
}

# ── Docker log errors (last 5 min) ───────────────────────────────────────────
check_recent_errors() {
    local error_count
    error_count=$(docker logs --since 5m backend 2>&1 | grep -ci "error\|exception\|traceback" || true)
    if (( error_count >= 10 )); then
        ALERTS+=("WARNING: $error_count errors in backend logs (last 5m)")
    fi
}

# ── Run all checks ───────────────────────────────────────────────────────────
check_containers
check_backend
check_llm
check_disk
check_recent_errors

# ── Output ────────────────────────────────────────────────────────────────────
if (( ${#ALERTS[@]} == 0 )); then
    if [[ "$ALERT_ONLY" != "--alert-only" ]]; then
        echo "[$TIMESTAMP] All health checks passed"
    fi
else
    echo "[$TIMESTAMP] ${#ALERTS[@]} alert(s):"
    for alert in "${ALERTS[@]}"; do
        echo "  - $alert"
    done
    # Optional: send to webhook
    if [[ -n "${HEALTH_WEBHOOK_URL:-}" ]]; then
        payload=$(printf '{"text":"Flowmanner Health Alert\\n%s"}' "${ALERTS[*]}")
        curl -sf -X POST -H "Content-Type: application/json" -d "$payload" "$HEALTH_WEBHOOK_URL" >/dev/null 2>&1 || true
    fi
fi
