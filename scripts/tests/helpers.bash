#!/usr/bin/env bash
# =============================================================================
# helpers.bash — Common stubs, mocks, and assertions for FlowManner Bats tests
# =============================================================================
# Source this file in setup() of your .bats test file.
#
# Provides:
#   - PATH override with fake_bin/ stubs
#   - Assertion helpers: assert_success, assert_failure, assert_output_contains
#   - Fake curl, docker, ssh, timeout, md5sum, sudo, wg, date
#   - Temp directory management
#   - Real source directory creation (scripts use hardcoded paths)
# =============================================================================

# ── Path overrides ────────────────────────────────────────────────────────────

setup_fake_bin() {
  FAKE_BIN="$(cd "$(dirname "$BATS_TEST_FILENAME")/fixtures/fake_bin" && pwd)"
  # Prepend so stubs shadow real binaries
  export PATH="${FAKE_BIN}:${PATH}"

  # Directory where stubs store their state/requests
  STUB_DIR="${BATS_TEST_TMPDIR}/stubs"
  mkdir -p "$STUB_DIR"
  export STUB_DIR
}

# ── Real source directories (scripts use hardcoded paths, not env vars) ───────

ensure_source_dirs() {
  # The deploy script checks these hardcoded paths.  We create them
  # as real directories so preflight passes.  They are empty — no
  # real source is needed since deploy steps are stubbed.
  mkdir -p /home/glenn/FlowmannerV2-frontend
  mkdir -p /opt/flowmanner/backend
}

# ── Create stub commands ──────────────────────────────────────────────────────

create_stub() {
  local name="$1"
  local outfile="${FAKE_BIN}/${name}"
  cat > "$outfile" <<'STUB_INNER'
#!/usr/bin/env bash
LOG="${STUB_DIR}/__STUB_NAME__.log"
echo "$(date -u +%s) $*" >> "$LOG"
# Read response from response file if present
RESP="${STUB_DIR}/__STUB_NAME__.resp"
if [ -f "$RESP" ]; then
  # First line may be "EXIT:<code>" to override exit code
  EXIT_LINE=$(head -1 "$RESP")
  if echo "$EXIT_LINE" | grep -q '^EXIT:[0-9]'; then
    EXIT_CODE=$(echo "$EXIT_LINE" | sed 's/^EXIT://')
    tail -n +2 "$RESP"
    exit "$EXIT_CODE"
  fi
  cat "$RESP"
  exit 0
fi
# Default: success, return content from default file
DEF="${STUB_DIR}/__STUB_NAME__.default"
if [ -f "$DEF" ]; then
  cat "$DEF"
fi
exit 0
STUB_INNER
  sed -i "s/__STUB_NAME__/${name}/g" "$outfile"
  chmod +x "$outfile"
}

# ── Stub response helpers ─────────────────────────────────────────────────────

stub_response() {
  local cmd="$1"; shift
  printf '%s\n' "$@" > "${STUB_DIR}/${cmd}.resp"
}

stub_exit_code() {
  local cmd="$1" code="$2"
  echo "EXIT:${code}" > "${STUB_DIR}/${cmd}.resp"
}

stub_default() {
  local cmd="$1"; shift
  printf '%s\n' "$@" > "${STUB_DIR}/${cmd}.default"
}

clear_stub() {
  local cmd="$1"
  rm -f "${STUB_DIR}/${cmd}.resp" "${STUB_DIR}/${cmd}.default" "${STUB_DIR}/${cmd}.log"
}

# ── Fake curl ─────────────────────────────────────────────────────────────────

create_fake_curl() {
  local f="${FAKE_BIN}/curl"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
LOG="${STUB_DIR}/curl.log"
echo "$(date -u +%s) $*" >> "$LOG"

# Find the URL (last non-flag argument)
URL=""
while [ $# -gt 0 ]; do
  case "$1" in
    -*) shift ;;
    *)  URL="$1"; shift ;;
  esac
done
URL="${URL:-unknown}"

# Normalize URL for filename: replace all / and : with _
KEY=$(echo "$URL" | tr '/:' '_')
RESP="${STUB_DIR}/curl.${KEY}.resp"
DEF="${STUB_DIR}/curl.default"

if [ -f "$RESP" ]; then
  CODE=$(head -1 "$RESP")
  BODY=$(tail -n +2 "$RESP")

  # -w '%{http_code}' → print just the status code
  if echo "$*" | grep -q '%{http_code}'; then
    echo -n "$CODE"
    exit 0
  fi

  # -I → print status line
  if echo "$*" | grep -q '\-I'; then
    echo "HTTP/1.1 $CODE"
    exit 0
  fi

  # -o <file> → write body to file
  OUTFILE=""
  PREV=""
  for a in "$@"; do
    [ "$PREV" = "-o" ] && { OUTFILE="$a"; break; }
    PREV="$a"
  done
  if [ -n "$OUTFILE" ] && [ "$OUTFILE" != "/dev/null" ] && [ "$OUTFILE" != "/dev/stderr" ]; then
    echo "$BODY" > "$OUTFILE"
  fi

  # -f: if code is 4xx/5xx, exit non-zero
  if echo "$*" | grep -q '\-f' && echo "$CODE" | grep -q '^[45]'; then
    exit 22
  fi

  # Print body for normal requests
  [ "$CODE" = "200" ] || [ "$CODE" = "401" ] && echo "$BODY"
  exit 0
fi

# Default response from default file
if [ -f "$DEF" ]; then
  cat "$DEF"
fi
exit 0
EOF
  chmod +x "$f"
}

set_curl_response() {
  local url="$1" code="$2"; shift 2
  local key
  key=$(echo "$url" | tr '/:' '_')
  { echo "$code"; printf '%s\n' "$@"; } > "${STUB_DIR}/curl.${key}.resp"
}

set_curl_default() {
  local code="$1"; shift
  { echo "$code"; printf '%s\n' "$@"; } > "${STUB_DIR}/curl.default"
}

# ── Fake ssh ──────────────────────────────────────────────────────────────────

create_fake_ssh() {
  local f="${FAKE_BIN}/ssh"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
LOG="${STUB_DIR}/ssh.log"
echo "$(date -u +%s) $*" >> "$LOG"
RESP="${STUB_DIR}/ssh.resp"
if [ -f "$RESP" ]; then
  EXIT_LINE=$(head -1 "$RESP")
  if echo "$EXIT_LINE" | grep -q '^EXIT:'; then
    EXIT_CODE=$(echo "$EXIT_LINE" | sed 's/^EXIT://')
    tail -n +2 "$RESP"
    exit "$EXIT_CODE"
  fi
  cat "$RESP"
  exit 0
fi
# Default: echo OK (VPS reachable)
echo "OK"
exit 0
EOF
  chmod +x "$f"
}

# ── Fake docker ───────────────────────────────────────────────────────────────

create_fake_docker() {
  local f="${FAKE_BIN}/docker"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
LOG="${STUB_DIR}/docker.log"
echo "$(date -u +%s) $*" >> "$LOG"
RESP="${STUB_DIR}/docker.resp"
if [ -f "$RESP" ]; then
  EXIT_LINE=$(head -1 "$RESP")
  if echo "$EXIT_LINE" | grep -q '^EXIT:'; then
    EXIT_CODE=$(echo "$EXIT_LINE" | sed 's/^EXIT://')
    tail -n +2 "$RESP"
    exit "$EXIT_CODE"
  fi
  cat "$RESP"
  exit 0
fi
# Default: simulate healthy containers
if echo "$*" | grep -q 'ps --filter'; then
  echo "container-id-fake123"
elif echo "$*" | grep -q 'ps --format json'; then
  echo '[{"Service":"frontend","State":"running"},{"Service":"nginx","State":"running"}]'
elif echo "$*" | grep -q 'tag'; then
  : # docker tag succeeds silently
elif echo "$*" | grep -q 'build'; then
  echo "docker build: success (stubbed)"
fi
exit 0
EOF
  chmod +x "$f"
}

# ── Fake timeout (shift only the timeout value, exec the rest) ────────────────

create_fake_timeout() {
  local f="${FAKE_BIN}/timeout"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
LOG="${STUB_DIR}/timeout.log"
echo "$(date -u +%s) $*" >> "$LOG"
RESP="${STUB_DIR}/timeout.resp"
if [ -f "$RESP" ]; then
  CODE=$(head -1 "$RESP")
  if [ -n "$CODE" ] && [ "$CODE" -eq "$CODE" ] 2>/dev/null; then
    exit "$CODE"
  fi
fi
# Shift past the timeout value only, then exec the rest
TIMEOUT_VAL="$1"; shift
exec "$@" 2>/dev/null || exit $?
EOF
  chmod +x "$f"
}

# ── Fake sudo ─────────────────────────────────────────────────────────────────

create_fake_sudo() {
  local f="${FAKE_BIN}/sudo"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
LOG="${STUB_DIR}/sudo.log"
echo "$(date -u +%s) $*" >> "$LOG"
RESP="${STUB_DIR}/sudo.resp"
if [ -f "$RESP" ]; then
  cat "$RESP"
  exit 0
fi
# wg show: return a fake handshake line
if echo "$*" | grep -q 'wg show'; then
  echo "  latest handshake: 30 seconds ago"
fi
"$@" 2>/dev/null || true
exit 0
EOF
  chmod +x "$f"
}

# ── Fake md5sum ───────────────────────────────────────────────────────────────

create_fake_md5sum() {
  local f="${FAKE_BIN}/md5sum"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
LOG="${STUB_DIR}/md5sum.log"
echo "$(date -u +%s) $*" >> "$LOG"
RESP="${STUB_DIR}/md5sum.resp"
if [ -f "$RESP" ]; then
  cat "$RESP"
  exit 0
fi
# Default: deterministic hash based on content length + filename
for f in "$@"; do
  if [ -f "$f" ] && [ "$f" != "-" ]; then
    SIZE=$(stat -c%s "$f" 2>/dev/null || echo 0)
    printf "deadbeef%08x  %s\n" "$SIZE" "$(basename "$f")"
  fi
done
exit 0
EOF
  chmod +x "$f"
}

# ── Fake date (fully deterministic, never calls real date) ────────────────────

create_fake_date() {
  local f="${FAKE_BIN}/date"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
LOG="${STUB_DIR}/date.log"
echo "$(date -u +%s) $*" >> "$LOG"
# Return fixed timestamps for any format request
if echo "$*" | grep -q '+%Y%m%d-%H%M%S'; then
  echo "20260602-120000"
elif echo "$*" | grep -q '+%Y-%m-%dT%H:%M:%SZ'; then
  echo "2026-06-02T12:00:00Z"
elif echo "$*" | grep -q '\-u'; then
  echo "2026-06-02T12:00:00Z"
else
  echo "2026-06-02T12:00:00Z"
fi
exit 0
EOF
  chmod +x "$f"
}

# ── Fake deploy-frontend.sh (success by default) ──────────────────────────────

create_fake_frontend_deploy() {
  local f="${FAKE_BIN}/deploy-frontend.sh"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
echo "frontend deploy stubbed: success" >&2
exit 0
EOF
  chmod +x "$f"
}

# ── Fake smoke script (exit 0 by default) ─────────────────────────────────────

create_fake_smoke() {
  local f="${FAKE_BIN}/smoke_flowmanner.sh"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
echo "DEPLOY_SMOKE=PASS"
exit 0
EOF
  chmod +x "$f"
}

# ── Fake sleep (no-op to speed up tests) ──────────────────────────────────────

create_fake_sleep() {
  local f="${FAKE_BIN}/sleep"
  cat > "$f" <<'EOF'
#!/usr/bin/env bash
# no-op — tests should never wait for real time
exit 0
EOF
  chmod +x "$f"
}

# ── Create all stubs ──────────────────────────────────────────────────────────

create_all_stubs() {
  setup_fake_bin
  create_fake_curl
  create_fake_ssh
  create_fake_docker
  create_fake_timeout
  create_fake_sudo
  create_fake_md5sum
  create_fake_date
  create_fake_sleep
  create_fake_frontend_deploy
  create_fake_smoke
}

# ── Bats-style assertions (polyfill) ──────────────────────────────────────────

assert_success() {
  if [ "$status" -ne 0 ]; then
    { echo "Expected success (0), got $status"; echo "Output: $output"; } >&2
    return 1
  fi
}

assert_failure() {
  if [ "$status" -eq 0 ]; then
    { echo "Expected failure, got success"; echo "Output: $output"; } >&2
    return 1
  fi
}

assert_output_contains() {
  if ! echo "$output" | grep -qFe "$1"; then
    { echo "Expected output to contain: '$1'"; echo "Actual: $output"; } >&2
    return 1
  fi
}

refute_output_contains() {
  if echo "$output" | grep -qFe "$1"; then
    { echo "Expected output NOT to contain: '$1'"; echo "Actual: $output"; } >&2
    return 1
  fi
}
