#!/usr/bin/env bash
#
# Flowmanner Load Test Runner
#
# Runs k6 load tests against the local backend.
# Must be run from the homelab machine.
#
# Usage:
#   ./run-tests.sh [script] [extra-k6-args...]
#
# Scripts:
#   health         — Health endpoint smoke + load + stress
#   login          — Auth endpoint (rate-limit aware)
#   missions       — Mission CRUD
#   chat           — Chat thread + message
#   search         — Search endpoint
#   full           — Combined realistic workload
#   all            — Run all scripts sequentially
#
# Environment:
#   BASE_URL       — Backend URL (default: http://127.0.0.1:8000)
#   TEST_EMAIL     — Test user email (default: loadtest@example.com)
#   TEST_PASSWORD  — Test user password (default: LoadTest123!)
#

set -euo pipefail

SCRIPT="${1:-full}"
shift 2>/dev/null || true
EXTRA_ARGS=("$@")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
K6="${HOME}/.local/bin/k6"
REPORT_DIR="${SCRIPT_DIR}/reports"

mkdir -p "$REPORT_DIR"

export BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
export TEST_EMAIL="${TEST_EMAIL:-loadtest@example.com}"
export TEST_PASSWORD="${TEST_PASSWORD:-LoadTest123!}"

run_k6() {
  local script="$1"
  local timestamp
  timestamp=$(date +%Y%m%d-%H%M%S)
  local report_file="${REPORT_DIR}/${script}-${timestamp}.json"

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Running: ${script}"
  echo "Target:  ${BASE_URL}"
  echo "Report:  ${report_file}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  $K6 run \
    --out json="${report_file}" \
    --summary-export="${REPORT_DIR}/${script}-${timestamp}-summary.json" \
    "${EXTRA_ARGS[@]}" \
    "${SCRIPT_DIR}/scripts/${script}.js"

  echo ""
}

# Verify backend is reachable
if ! curl -sf "${BASE_URL}/api/health" > /dev/null 2>&1; then
  echo "ERROR: Backend not reachable at ${BASE_URL}"
  echo "Start the backend first: cd /opt/flowmanner && docker compose up -d backend"
  exit 1
fi

# Verify k6 is installed
if [ ! -x "$K6" ]; then
  echo "ERROR: k6 not found at ${K6}"
  echo "Install: curl -sL https://github.com/grafana/k6/releases/download/v0.56.0/k6-v0.56.0-linux-amd64.tar.gz | tar xzf - -C /tmp && cp /tmp/k6-v0.56.0-linux-amd64/k6 ~/.local/bin/"
  exit 1
fi

case "$SCRIPT" in
  health)   run_k6 health ;;
  login)    run_k6 login ;;
  missions) run_k6 missions ;;
  chat)     run_k6 chat ;;
  search)   run_k6 search ;;
  full)     run_k6 full-scenario ;;
  all)
    for s in health login missions search full-scenario; do
      run_k6 "$s"
      echo "Cooldown 10s..."
      sleep 10
    done
    ;;
  *)
    echo "Unknown script: ${SCRIPT}"
    echo "Usage: $0 [health|login|missions|chat|search|full|all]"
    exit 1
    ;;
esac

echo "All load tests complete. Reports in: ${REPORT_DIR}/"
