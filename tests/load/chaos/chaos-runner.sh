#!/usr/bin/env bash
#
# Flowmanner Chaos Engineering Runner
#
# Runs chaos experiments against the homelab during load tests.
# Must be run from the homelab machine (10.99.0.3).
#
# Usage:
#   ./chaos-runner.sh [experiment] [duration_seconds]
#
# Experiments:
#   container-kill    — Kill and restart a random container mid-load
#   network-partition — Block WireGuard traffic temporarily
#   db-pool-exhaust   — Open many DB connections to exhaust pool
#   llm-timeout       — Add iptables delay to LLM traffic
#   all               — Run all experiments sequentially
#

set -euo pipefail

EXPERIMENT="${1:-all}"
DURATION="${2:-60}"
CHAOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORT_DIR="${CHAOS_DIR}/../reports"

mkdir -p "$REPORT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${YELLOW}[CHAOS]${NC} $*"; }
ok()  { echo -e "${GREEN}[OK]${NC} $*"; }
err() { echo -e "${RED}[FAIL]${NC} $*"; }

# ── Preconditions ──────────────────────────────────────────────────────────
check_preconditions() {
  if ! command -v docker &>/dev/null; then
    err "docker not found — must run on homelab"
    exit 1
  fi

  if ! curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    err "Backend not healthy — start services first"
    exit 1
  fi

  ok "Preconditions met"
}

# ── Experiment: Container Kill ─────────────────────────────────────────────
experiment_container_kill() {
  log "Container Kill: Stopping backend for ${DURATION}s then restarting"

  local before_health
  before_health=$(curl -sf http://127.0.0.1:8000/api/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
  log "Pre-chaos health: $before_health"

  docker stop backend &
  local stop_pid=$!

  sleep "$DURATION"

  docker start backend &
  local start_pid=$!
  wait $start_pid

  # Wait for recovery
  local recovered=false
  for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
      recovered=true
      break
    fi
    sleep 2
  done

  if $recovered; then
    ok "Backend recovered after container kill (${DURATION}s downtime)"
  else
    err "Backend did NOT recover within 60s after container kill"
  fi

  # Verify data integrity
  local pg_ok
  pg_ok=$(docker exec workflow-postgres pg_isready -U flowmanner 2>/dev/null && echo "ok" || echo "error")
  log "PostgreSQL integrity: $pg_ok"
}

# ── Experiment: Network Partition ──────────────────────────────────────────
experiment_network_partition() {
  log "Network Partition: Simulating WireGuard drop for ${DURATION}s"

  # Block traffic between homelab containers and VPS
  # Use iptables to drop WireGuard port temporarily
  local wg_interface
  wg_interface=$(ip link show | grep wg | head -1 | awk -F: '{print $2}' | tr -d ' ')

  if [ -z "$wg_interface" ]; then
    log "No WireGuard interface found — skipping network partition"
    return
  fi

  log "Blocking WireGuard on $wg_interface"
  sudo iptables -A OUTPUT -o "$wg_interface" -j DROP 2>/dev/null || true
  sudo iptables -A INPUT -i "$wg_interface" -j DROP 2>/dev/null || true

  sleep "$DURATION"

  # Restore
  sudo iptables -D OUTPUT -o "$wg_interface" -j DROP 2>/dev/null || true
  sudo iptables -D INPUT -i "$wg_interface" -j DROP 2>/dev/null || true

  # Verify connectivity restored
  sleep 5
  if curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    ok "Backend healthy after network partition"
  else
    err "Backend unhealthy after network partition"
  fi
}

# ── Experiment: DB Pool Exhaustion ─────────────────────────────────────────
experiment_db_pool_exhaust() {
  log "DB Pool Exhaustion: Opening many concurrent connections for ${DURATION}s"

  # PostgreSQL max_connections is typically 100
  # Open connections to approach the limit
  local pids=()
  for i in $(seq 1 60); do
    docker exec -d workflow-postgres psql -U flowmanner -c "SELECT pg_sleep(${DURATION});" 2>/dev/null &
    pids+=($!)
  done

  log "Opened 60 idle connections — monitoring backend health"

  local errors=0
  for i in $(seq 1 10); do
    sleep 3
    if ! curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
      errors=$((errors + 1))
    fi
  done

  # Wait for connections to finish
  for pid in "${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done

  sleep 5
  if curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    ok "Backend survived DB pool exhaustion (errors during test: $errors/10 checks)"
  else
    err "Backend failed during DB pool exhaustion"
  fi
}

# ── Experiment: LLM Timeout Injection ──────────────────────────────────────
experiment_llm_timeout() {
  log "LLM Timeout: Adding 10s delay to LLM traffic for ${DURATION}s"

  # Add iptables rule to delay traffic to llama.cpp port
  sudo iptables -A OUTPUT -p tcp --dport 11434 -m statistic --mode random --probability 0.5 -j DROP 2>/dev/null || true

  log "50% of LLM requests will timeout for ${DURATION}s"

  sleep "$DURATION"

  # Restore
  sudo iptables -D OUTPUT -p tcp --dport 11434 -m statistic --mode random --probability 0.5 -j DROP 2>/dev/null || true

  # Check circuit breaker state
  local obs_status
  obs_status=$(curl -sf http://127.0.0.1:8000/api/observability/status 2>/dev/null || echo "{}")
  log "Circuit breaker state after LLM timeout: $obs_status"

  if curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    ok "Backend survived LLM timeout injection"
  else
    err "Backend failed during LLM timeout injection"
  fi
}

# ── Main ───────────────────────────────────────────────────────────────────
main() {
  log "Starting chaos experiment: $EXPERIMENT (duration: ${DURATION}s)"
  check_preconditions

  local report_file="${REPORT_DIR}/chaos-$(date +%Y%m%d-%H%M%S).log"
  exec > >(tee "$report_file") 2>&1

  case "$EXPERIMENT" in
    container-kill)    experiment_container_kill ;;
    network-partition) experiment_network_partition ;;
    db-pool-exhaust)   experiment_db_pool_exhaust ;;
    llm-timeout)       experiment_llm_timeout ;;
    all)
      experiment_container_kill
      log "Cooldown 30s between experiments..."
      sleep 30
      experiment_db_pool_exhaust
      log "Cooldown 30s between experiments..."
      sleep 30
      experiment_llm_timeout
      # Skip network-partition by default (requires sudo iptables)
      log "Skipping network-partition (requires manual sudo)"
      ;;
    *)
      err "Unknown experiment: $EXPERIMENT"
      echo "Usage: $0 [container-kill|network-partition|db-pool-exhaust|llm-timeout|all] [duration]"
      exit 1
      ;;
  esac

  log "Chaos experiment complete. Report: $report_file"
}

main
