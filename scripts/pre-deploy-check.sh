#!/usr/bin/env bash
# pre-deploy-check.sh — fail-closed gate invoked by deploy scripts
# Env vars:
#   HEALTH_URL          default: http://127.0.0.1:8000/api/health
#   WG_CHECK=skip       bypasses WireGuard check (audit-logged)
#   FLOWMANNER_DEPLOY_OVERRIDE_REASON  required when WG_CHECK=skip
# Exit codes: 0=clean, 1=any check failed, 2=missing sudoers setup
#
# Manual restore paths (RESTORE.md, `make deploy-backend` direct build)
# are operator-initiated escape hatches and bypass this gate by design.
# Out of MVP scope to gate them.
#
# sudoers setup (one-time, operator runs as root):
#   echo "glenn ALL=(root) NOPASSWD: /usr/bin/wg show *" | \
#     sudo tee /etc/sudoers.d/flowmanner-deploy && \
#     sudo chmod 0440 /etc/sudoers.d/flowmanner-deploy
#
# Usage:
#   ./scripts/pre-deploy-check.sh                  # run all checks
#   HEALTH_URL=http://127.0.0.1:9000/health ./scripts/pre-deploy-check.sh
#   WG_CHECK=skip FLOWMANNER_DEPLOY_OVERRIDE_REASON="hotfix 2026-06-18" \
#     ./scripts/pre-deploy-check.sh
#
# This is a Wave 1 skeleton: function names, env vars, exit codes, and
# fail-closed wiring are in place. Wave 2 Tasks 4-5 will flesh out the
# production logic for checks 2-6. Check bodies here are intentionally
# minimal so that the wiring is verifiable now.

set -euo pipefail

# --- Configuration -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_DIR="${COMPOSE_DIR:-$PROJECT_ROOT}"

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health}"
WG_CHECK="${WG_CHECK:-}"
FLOWMANNER_DEPLOY_OVERRIDE_REASON="${FLOWMANNER_DEPLOY_OVERRIDE_REASON:-}"
STATUS_FILE="${STATUS_FILE:-}"

# Counts of check outcomes (for the final summary line)
CHECKS_RUN=0
CHECKS_PASS=0
CHECKS_FAIL=0
CHECKS_SKIP=0
CHECKS_INFO=0
WG_AUTH_MISSING=false

# --- Colors -------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[FAIL]${NC}    $*"; }
log_skip()    { echo -e "${YELLOW}[SKIP]${NC}    $*"; }
log_step()    { echo -e "\n${CYAN}${BOLD}>>> $*${NC}"; }

# --- Parse args --------------------------------------------------------------
for arg in "$@"; do
  case "$arg" in
    --help|-h)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *)
      log_error "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

# --- Outcome helpers ---------------------------------------------------------
# Each check function calls record_pass / record_fail / record_skip /
# record_info exactly once. The aggregated counts feed the exit code.
record_pass() {
  local name="$1" msg="${2:-}"
  CHECKS_RUN=$((CHECKS_RUN + 1))
  CHECKS_PASS=$((CHECKS_PASS + 1))
  if [[ -n "$msg" ]]; then
    log_success "$name — $msg"
  else
    log_success "$name"
  fi
}

record_fail() {
  local name="$1" msg="${2:-}"
  CHECKS_RUN=$((CHECKS_RUN + 1))
  CHECKS_FAIL=$((CHECKS_FAIL + 1))
  if [[ -n "$msg" ]]; then
    log_error "$name — $msg"
  else
    log_error "$name"
  fi
}

record_skip() {
  local name="$1" msg="${2:-}"
  CHECKS_RUN=$((CHECKS_RUN + 1))
  CHECKS_SKIP=$((CHECKS_SKIP + 1))
  if [[ -n "$msg" ]]; then
    log_skip "$name — $msg"
  else
    log_skip "$name"
  fi
}

record_info() {
  local name="$1" msg="${2:-}"
  CHECKS_RUN=$((CHECKS_RUN + 1))
  CHECKS_INFO=$((CHECKS_INFO + 1))
  if [[ -n "$msg" ]]; then
    log_info "$name — $msg"
  else
    log_info "$name"
  fi
}

# --- Check 1: STATUS.md presence + [BLOCKED] markers -------------------------
# Per §4.5 of the handoff: if STATUS.md is absent, emit an info-level note
# and DO NOT fail. Only a present file containing [BLOCKED] markers fails.
#
# STATUS_FILE env var overrides the default path (default: $PROJECT_ROOT/STATUS.md).
# Per-agent session state is gitignored (.gitignore), so a missing file is the
# normal pre-initialization state, not an error.
check_status_file() {
  log_step "Check 1/6: STATUS.md [BLOCKED] markers"
  local status_file="${STATUS_FILE:-$PROJECT_ROOT/STATUS.md}"
  if [[ ! -f "$status_file" ]]; then
    record_info "status_file" "STATUS.md not present at $status_file (info-level, not a failure)"
    return 0
  fi
  # Parse for [BLOCKED] markers (literal text — no regex). Multiple occurrences
  # are listed individually so the operator can act on each.
  local blocked_lines
  blocked_lines=$(grep -nF '[BLOCKED]' "$status_file" 2>/dev/null || true)
  if [[ -z "$blocked_lines" ]]; then
    record_pass "status_file" "present, no [BLOCKED] markers ($status_file)"
    return 0
  fi
  local count
  count=$(echo "$blocked_lines" | wc -l)
  record_fail "status_file" "$count [BLOCKED] marker(s) in $status_file — clear before deploy"
  echo "$blocked_lines" | sed 's/^/    /'
  return 0
}

# --- Check 2: working tree cleanliness (excluding STATUS.md) ------------------
# Per HANDOFF §3.3 (D3) + §4.5: STATUS.md is intentionally mutable per-agent
# session state and is .gitignore'd. STATUS.example.md is the committed
# template. Both are excluded from this check.
#
# Policy: any untracked or modified entry that is NOT gitignored and NOT in
# the STATUS exclusion list hard-fails the deploy. Operators must commit,
# stash, or add to .gitignore before retrying.
check_working_tree() {
  log_step "Check 2/6: working tree cleanliness"
  # porcelain format: XY<space>path (XY are 2 status chars)
  local dirty_entries=""
  local line path
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    # Strip the 2-char status prefix to get the path.
    path="${line:3}"
    # Skip STATUS files (intentionally mutable per-agent session state).
    [[ "$path" == "STATUS.md" || "$path" == "STATUS.example.md" ]] && continue
    # Skip paths that gitignore would ignore. check-ignore returns 0 (ignored)
    # for untracked + gitignored, and 1 (not ignored) for tracked files even
    # if a .gitignore pattern matches them — which is the semantic we want.
    if git -C "$PROJECT_ROOT" check-ignore -q "$path" 2>/dev/null; then
      continue
    fi
    dirty_entries+="$line"$'\n'
  done < <(git -C "$PROJECT_ROOT" status --porcelain 2>/dev/null || true)
  if [[ -z "$dirty_entries" ]]; then
    record_pass "working_tree" "clean (excluding STATUS.md / STATUS.example.md / gitignored)"
    return 0
  fi
  local count
  count=$(printf '%s' "$dirty_entries" | grep -c . || true)
  record_fail "working_tree" "$count uncommitted non-ignored entry(ies) — commit or stash before deploy"
  printf '%s' "$dirty_entries" | sed 's/^/    /'
  return 0
}

# --- Check 3: WireGuard tunnel up (fail-closed on missing sudoers) ------------
# Per D1: `sudo -n wg show wg0` is the canonical check. If sudo asks for a
# password (`sudo -n` exits non-zero), we fail-closed with the sudoers setup
# recipe in the error message. `WG_CHECK=skip` is an audit-logged escape hatch.
check_wireguard() {
  log_step "Check 3/6: WireGuard tunnel (wg0)"
  if [[ "$WG_CHECK" == "skip" ]]; then
    if [[ -z "$FLOWMANNER_DEPLOY_OVERRIDE_REASON" ]]; then
      record_fail "wireguard" "WG_CHECK=skip requires FLOWMANNER_DEPLOY_OVERRIDE_REASON"
      return 0
    fi
    log_warn "AUDIT: WG_CHECK=skip bypass invoked — reason: $FLOWMANNER_DEPLOY_OVERRIDE_REASON"
    local _host="${HOSTNAME:-}"
    if [[ -z "$_host" ]]; then _host="$(hostname 2>/dev/null || echo unknown)"; fi
    log_warn "AUDIT: bypass user=$(whoami) host=${_host} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    record_skip "wireguard" "WG_CHECK=skip (audit-logged)"
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    log_error "sudo binary not found on PATH. Install sudo or wire this check differently."
    record_fail "wireguard" "sudo missing on PATH"
    return 0
  fi
  # `sudo -n` fails non-interactively if sudoers isn't set up.
  local wg_out
  if wg_out=$(sudo -n /usr/bin/wg show wg0 2>&1); then
    # Surface the listening port line for the operator log.
    local listening
    listening=$(echo "$wg_out" | awk -F': ' '/listening port/ {print $2}' | head -1)
    if [[ -n "$listening" ]]; then
      record_pass "wireguard" "wg0 up (listening port ${listening})"
    else
      record_pass "wireguard" "wg0 up"
    fi
    return 0
  fi
  # Auth failure path: emit the canonical setup recipe so the operator can
  # unblock themselves. Exit code 2 reserved for "missing sudoers setup"
  # so callers can distinguish from a regular check failure.
  WG_AUTH_MISSING=true
  log_error "sudo -n /usr/bin/wg show wg0 failed (sudoers not configured)."
  log_error "Run as root, ONE TIME:"
  log_error "  echo \"\$(whoami) ALL=(root) NOPASSWD: /usr/bin/wg show *\" | \\"
  log_error "    sudo tee /etc/sudoers.d/flowmanner-deploy && \\"
  log_error "    sudo chmod 0440 /etc/sudoers.d/flowmanner-deploy"
  return 0
}

# --- Check 4: backend health URL reachable ------------------------------------
# Default URL matches pre-flight.sh; both `/health` and `/api/health` work
# because of the dual router mount in main_fastapi.py:359-360.
#
# Per §4.2 + §6 YAGNI: live-only — no "last deploy healthy" artifact file.
# HTTP 200 = pass; any non-2xx response, connection refused, or timeout
# (curl --max-time 5) = fail.
check_health_url() {
  log_step "Check 4/6: backend health URL ($HEALTH_URL)"
  # -w '%{http_code}': always emits the code (curl prints "000" when no HTTP
  # transaction occurred, e.g. connection refused). -S surfaces error detail
  # on stderr (we capture stdout only).
  local http_code
  http_code=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' \
              "$HEALTH_URL" 2>/dev/null || true)
  # If curl exits before producing output (very rare), http_code is empty.
  : "${http_code:=000}"
  if [[ "$http_code" == "200" ]]; then
    record_pass "health_url" "HTTP $http_code"
    return 0
  fi
  record_fail "health_url" "expected HTTP 200, got HTTP $http_code from $HEALTH_URL"
  return 0
}

# --- Check 5: no uncommitted alembic migration files --------------------------
# Reference: existing check_pending_migrations() at deploy-backend.sh:179-199.
# Path is pinned explicitly per §4.3 — no globs that miss new subdirectories.
check_pending_migrations() {
  log_step "Check 5/6: uncommitted alembic migrations (backend/alembic/versions/)"
  local pending
  pending=$(git -C "$PROJECT_ROOT" status --porcelain \
            backend/alembic/versions/ 2>/dev/null \
            | grep -E '\.py$' \
            | grep -vE '^.D ' \
            | awk '{print $2}') || pending=""
  if [[ -z "$pending" ]]; then
    record_pass "pending_migrations" "no uncommitted files"
    return 0
  fi
  local count
  count=$(echo "$pending" | wc -l)
  record_fail "pending_migrations" "$count uncommitted migration file(s) — commit before deploy"
  echo "$pending" | sed 's/^/    /'
  return 0
}

# --- Check 6: no uncommitted model files (backend/app/models/) --------
# Per §4.3: pin the path explicitly. Do NOT hardcode globs that miss new
# subdirectories under backend/app/models/.
check_model_path() {
  log_step "Check 6/6: uncommitted model files (backend/app/models/)"
  local pending
  pending=$(git -C "$PROJECT_ROOT" status --porcelain \
            backend/app/models/ 2>/dev/null \
            | grep -E '\.py$' \
            | grep -vE '^.D ' \
            | awk '{print $2}') || pending=""
  if [[ -z "$pending" ]]; then
    record_pass "model_path" "no uncommitted files"
    return 0
  fi
  local count
  count=$(echo "$pending" | wc -l)
  record_fail "model_path" "$count uncommitted model file(s) — commit before deploy"
  echo "$pending" | sed 's/^/    /'
  return 0
}

# --- Check 7 (F-3, P3): frontend lint + typecheck gate ----------------
# The frontend lives in a SEPARATE repo (/home/glenn/FlowmannerV2-frontend).
# This check runs THAT repo's own lint/typecheck when present so a broken
# but compiling frontend cannot ship.
#
# SCOPE: this gate is scope-aware via PRECHECK_SCOPE (set by the caller):
#   - frontend  -> FAIL-CLOSED (blocks a frontend deploy on lint/tsc errors)
#   - backend   -> INFO-ONLY   (never blocks a backend deploy on unrelated
#                                frontend lint debt in a separate repo)
#   - all       -> FAIL-CLOSED (default)
# Rationale: a backend P0 security fix must NOT be blocked because the
# frontend repo has pre-existing lint errors it does not own.
#
# It is also SKIPPABLE via FRONTEND_CHECK=skip (audit-logged) for operator
# escape hatches. We deliberately do NOT run `npm run build` here — the
# deploy script does the docker build on the VPS. Lint + tsc --noEmit catch
# the "compiles but is broken" class the audit called out.
FRONTEND_DIR="${FRONTEND_DIR:-/home/glenn/FlowmannerV2-frontend}"
PRECHECK_SCOPE="${PRECHECK_SCOPE:-all}"
check_frontend_quality() {
  log_step "Check 7/7: frontend lint + typecheck (F-3) [scope=$PRECHECK_SCOPE]"
  if [[ "${FRONTEND_CHECK:-}" == "skip" ]]; then
    log_warn "AUDIT: FRONTEND_CHECK=skip bypass invoked"
    record_skip "frontend_quality" "FRONTEND_CHECK=skip (audit-logged)"
    return 0
  fi
  if [[ ! -d "$FRONTEND_DIR" ]]; then
    record_info "frontend_quality" "frontend dir not found at $FRONTEND_DIR (info-level)"
    return 0
  fi
  if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    record_info "frontend_quality" "no package.json in $FRONTEND_DIR (info-level)"
    return 0
  fi
  log_info "Running frontend checks in $FRONTEND_DIR"
  local rc=0
  ( cd "$FRONTEND_DIR" && npm run lint --silent ) || rc=1
  if [[ $rc -ne 0 ]]; then
    if [[ "$PRECHECK_SCOPE" == "backend" ]]; then
      record_info "frontend_quality" "npm run lint FAILED in $FRONTEND_DIR — INFO-ONLY (backend scope, does not block backend deploy)"
      return 0
    fi
    record_fail "frontend_quality" "npm run lint FAILED in $FRONTEND_DIR — fix before deploy"
    return 0
  fi
  ( cd "$FRONTEND_DIR" && npx tsc --noEmit --skipLibCheck ) || rc=1
  if [[ $rc -ne 0 ]]; then
    if [[ "$PRECHECK_SCOPE" == "backend" ]]; then
      record_info "frontend_quality" "tsc --noEmit FAILED in $FRONTEND_DIR — INFO-ONLY (backend scope, does not block backend deploy)"
      return 0
    fi
    record_fail "frontend_quality" "tsc --noEmit FAILED in $FRONTEND_DIR — fix before deploy"
    return 0
  fi
  record_pass "frontend_quality" "lint + tsc --noEmit passed"
  return 0
}

# --- main -------------------------------------------------------------------
main() {
  log_step "pre-deploy-check.sh — Wave 1 skeleton + P3 F-3 gate"
  log_info "PROJECT_ROOT=$PROJECT_ROOT"
  log_info "HEALTH_URL=$HEALTH_URL"
  log_info "WG_CHECK=${WG_CHECK:-(unset, fail-closed on missing sudoers)}"
  log_info "FRONTEND_DIR=$FRONTEND_DIR"

  check_status_file
  check_working_tree
  check_wireguard
  check_health_url
  check_pending_migrations
  check_model_path
  check_frontend_quality

  # ── Summary ──────────────────────────────────────────────────────────
  log_step "summary"
  echo "  checks run:   $CHECKS_RUN"
  echo "  passed:       $CHECKS_PASS"
  echo "  failed:       $CHECKS_FAIL"
  echo "  skipped:      $CHECKS_SKIP"
  echo "  info-only:    $CHECKS_INFO"

  if [[ "$WG_AUTH_MISSING" == "true" ]]; then
    log_error "WireGuard sudoers not configured — see recipe above."
    exit 2
  fi

  if [[ "$CHECKS_FAIL" -gt 0 ]]; then
    log_error "pre-deploy-check FAILED — $CHECKS_FAIL check(s) failed."
    echo "[PREFLIGHT: BLOCKED] $CHECKS_FAIL check(s) failed, $CHECKS_PASS passed. Review [FAIL] lines above for remediation steps."
    exit 1
  fi

  log_success "pre-deploy-check PASSED."
  echo "[PREFLIGHT: READY] $CHECKS_PASS/$CHECKS_RUN checks passed."
  exit 0
}

main "$@"
