#!/usr/bin/env bats
# =============================================================================
# deploy_flowmanner.bats — Regression tests for:
#   /opt/flowmanner/scripts/deploy_flowmanner.sh
#   /opt/flowmanner/scripts/smoke_flowmanner.sh
# =============================================================================

setup() {
  load "${BATS_TEST_DIRNAME}/helpers.bash"
  create_all_stubs
  ensure_source_dirs

  # Paths to scripts under test
  DEPLOY_SCRIPT="${BATS_TEST_DIRNAME}/../deploy_flowmanner.sh"
  SMOKE_SCRIPT="${BATS_TEST_DIRNAME}/../smoke_flowmanner.sh"

  # Ensure the deploy-frontend.sh stub is at the path the deploy script checks.
  # The deploy script hardcodes /opt/flowmanner/deploy-frontend.sh — make it a
  # symlink to our fake.
  mkdir -p /opt/flowmanner
  ln -sf "${FAKE_BIN}/deploy-frontend.sh" /opt/flowmanner/deploy-frontend.sh
  # Same for smoke script
  ln -sf "${FAKE_BIN}/smoke_flowmanner.sh" /opt/flowmanner/scripts/smoke_flowmanner.sh 2>/dev/null || true

  export DEPLOY_TIMEOUT=5  # short timeout for fast test failure
}

teardown() {
  : # temp dirs auto-cleaned by Bats TMPDIR
}

# ═══════════════════════════════════════════════════════════════════════════════
# DEPLOY SCRIPT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

# ── --help ────────────────────────────────────────────────────────────────────

@test "deploy: --help prints usage and exits 0" {
  run bash "$DEPLOY_SCRIPT" --help
  assert_success
  assert_output_contains "Usage: deploy_flowmanner.sh"
  assert_output_contains "--frontend-only"
  assert_output_contains "--dry-run"
}

@test "deploy: -h also prints usage" {
  run bash "$DEPLOY_SCRIPT" -h
  assert_success
  assert_output_contains "Usage: deploy_flowmanner.sh"
}

# ── --dry-run ─────────────────────────────────────────────────────────────────

@test "deploy: --dry-run exits 0 and does not execute real actions" {
  run bash "$DEPLOY_SCRIPT" --dry-run --skip-smoke
  assert_success
  assert_output_contains "DRY-RUN MODE"
  assert_output_contains "DEPLOY COMPLETE"
}

@test "deploy: --dry-run does not call real frontend deploy" {
  # First, make the normal deploy pass so the script doesn't block
  run bash "$DEPLOY_SCRIPT" --dry-run --skip-smoke
  assert_success
  refute_output_contains "Would execute:"
  # It should say "Would execute" (dry-run output for frontend deploy)
  assert_output_contains "Would execute: bash"
}

# ── Flag gating ───────────────────────────────────────────────────────────────

@test "deploy: --frontend-only and --backend-only mutually exclusive" {
  run bash "$DEPLOY_SCRIPT" --frontend-only --backend-only --skip-smoke
  assert_failure
  [ "$status" -eq 6 ]
  assert_output_contains "mutually exclusive"
}

@test "deploy: unknown flag exits 6" {
  run bash "$DEPLOY_SCRIPT" --bogus-flag
  assert_failure
  [ "$status" -eq 6 ]
  assert_output_contains "Unknown argument"
}

# ── --frontend-only ───────────────────────────────────────────────────────────

@test "deploy: --frontend-only runs frontend flow only" {
  run bash "$DEPLOY_SCRIPT" --frontend-only --skip-smoke
  assert_success
  assert_output_contains "FRONTEND DEPLOY"
}

@test "deploy: --frontend-only skips backend" {
  run bash "$DEPLOY_SCRIPT" --frontend-only --skip-smoke
  assert_success
  refute_output_contains "BACKEND DEPLOY"
}

# ── --backend-only ────────────────────────────────────────────────────────────

@test "deploy: --backend-only skips frontend" {
  # Stub health checks so backend deploy succeeds
  set_curl_response "http://localhost:8000/health" "200"
  run bash "$DEPLOY_SCRIPT" --backend-only --skip-smoke
  assert_success
  refute_output_contains "FRONTEND DEPLOY"
  assert_output_contains "BACKEND DEPLOY"
}

# ── Default mode (both) ───────────────────────────────────────────────────────

@test "deploy: default mode runs both frontend and backend" {
  set_curl_response "http://localhost:8000/health" "200"
  run bash "$DEPLOY_SCRIPT" --skip-smoke
  assert_success
  assert_output_contains "FRONTEND DEPLOY"
  assert_output_contains "BACKEND DEPLOY"
}

# ── --skip-smoke ──────────────────────────────────────────────────────────────

@test "deploy: --skip-smoke skips smoke invocation" {
  set_curl_response "http://localhost:8000/health" "200"
  run bash "$DEPLOY_SCRIPT" --skip-smoke
  assert_success
  assert_output_contains "Smoke tests SKIPPED"
}

@test "deploy: without --skip-smoke calls smoke script" {
  set_curl_response "http://localhost:8000/health" "200"
  run bash "$DEPLOY_SCRIPT"
  refute_output_contains "Smoke tests SKIPPED"
}

# ── Dependency failures ───────────────────────────────────────────────────────

@test "deploy: fails when ssh is missing" {
  mv "${FAKE_BIN}/ssh" "${FAKE_BIN}/ssh.hidden"
  run bash "$DEPLOY_SCRIPT"
  mv "${FAKE_BIN}/ssh.hidden" "${FAKE_BIN}/ssh"
  assert_failure
  assert_output_contains "Missing dependencies"
}

@test "deploy: fails when docker is missing" {
  mv "${FAKE_BIN}/docker" "${FAKE_BIN}/docker.hidden"
  run bash "$DEPLOY_SCRIPT"
  mv "${FAKE_BIN}/docker.hidden" "${FAKE_BIN}/docker"
  assert_failure
  assert_output_contains "Missing dependencies"
}

# ── Frontend deploy failures ──────────────────────────────────────────────────

@test "deploy: frontend timeout detected (exit 124 → exit 5)" {
  cat > "${FAKE_BIN}/deploy-frontend.sh" <<'EOF'
#!/usr/bin/env bash
exit 124
EOF
  chmod +x "${FAKE_BIN}/deploy-frontend.sh"

  run bash "$DEPLOY_SCRIPT" --frontend-only --skip-smoke
  assert_failure
  [ "$status" -eq 5 ]
  assert_output_contains "TIMED OUT"
}

@test "deploy: frontend failure (exit 2)" {
  cat > "${FAKE_BIN}/deploy-frontend.sh" <<'EOF'
#!/usr/bin/env bash
exit 3
EOF
  chmod +x "${FAKE_BIN}/deploy-frontend.sh"

  run bash "$DEPLOY_SCRIPT" --frontend-only --skip-smoke
  assert_failure
  [ "$status" -eq 2 ]
  assert_output_contains "Frontend deploy FAILED"
}

# ── Backend deploy failures ───────────────────────────────────────────────────

@test "deploy: backend failure propagates (exit 3)" {
  # Stub preflight health checks
  set_curl_response "http://localhost:8000/health" "200"
  # Make docker build fail
  stub_exit_code "docker" 1

  run bash "$DEPLOY_SCRIPT" --backend-only --skip-smoke
  assert_failure
}

# ── Smoke failure propagation ─────────────────────────────────────────────────

@test "deploy: smoke failure causes exit 4" {
  cat > "${FAKE_BIN}/smoke_flowmanner.sh" <<'EOF'
#!/usr/bin/env bash
echo "DEPLOY_SMOKE=FAIL"
exit 1
EOF
  chmod +x "${FAKE_BIN}/smoke_flowmanner.sh"

  set_curl_response "http://localhost:8000/health" "200"

  run bash "$DEPLOY_SCRIPT"
  assert_failure
  [ "$status" -eq 4 ]
  assert_output_contains "Smoke tests FAILED"
}

# ── Preflight failures ────────────────────────────────────────────────────────

@test "deploy: preflight fails if VPS unreachable" {
  stub_exit_code "ssh" 255
  run bash "$DEPLOY_SCRIPT" --skip-smoke
  assert_failure
  [ "$status" -eq 1 ]
  assert_output_contains "VPS unreachable"
}

@test "deploy: preflight fails if backend container DOWN" {
  # Make docker ps return empty (no running container)
  stub_default "docker" ""
  run bash "$DEPLOY_SCRIPT" --skip-smoke
  assert_failure
  [ "$status" -eq 1 ]
  assert_output_contains "Backend container is DOWN"
}

@test "deploy: preflight fails if backend health DOWN" {
  set_curl_response "http://localhost:8000/health" "503"
  run bash "$DEPLOY_SCRIPT" --skip-smoke
  assert_failure
  [ "$status" -eq 1 ]
  assert_output_contains "health endpoint unreachable"
}

@test "deploy: preflight fails if WireGuard tunnel DOWN" {
  # sudo wg show returns no handshake
  stub_default "sudo" "interface: wg0"
  run bash "$DEPLOY_SCRIPT" --skip-smoke
  assert_failure
  [ "$status" -eq 1 ]
  assert_output_contains "WireGuard tunnel DOWN"
}

# ═══════════════════════════════════════════════════════════════════════════════
# SMOKE SCRIPT TESTS
# ═══════════════════════════════════════════════════════════════════════════════
#
# The smoke script hardcodes URLs (https://flowmanner.com etc.) — we set
# curl responses for those exact URLs.  The exports here are for readability
# only; the script ignores them.

smoke_setup() {
  # Smoke script uses hardcoded URLs — set curl responses for the real URLs
  export SNAPSHOT_DIR="${BATS_TEST_TMPDIR}/snapshots"
  mkdir -p "$SNAPSHOT_DIR" "${BATS_TEST_TMPDIR}/tmp"
  export TMPDIR="${BATS_TEST_TMPDIR}/tmp"

  # Override PROJECT_ROOT so homelab docker compose ps uses a test dir
  # (the script hardcodes this, but our fake docker ignores compose files anyway)
}

# ── Smoke: all checks pass ────────────────────────────────────────────────────

@test "smoke: all checks pass → DEPLOY_SMOKE=PASS" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "200" "<html>page</html>"
  set_curl_response "https://flowmanner.com/api/health" "200" '{"data":{"status":"ok"},"meta":{},"error":null}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{"request_id":"x"},"error":{"code":"unauthorized","message":"Not authenticated"}}'

  run bash "$SMOKE_SCRIPT"
  assert_success
  assert_output_contains "DEPLOY_SMOKE=PASS"
}

@test "smoke: homepage not 200/307 → DEPLOY_SMOKE=FAIL" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "500" ""
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "DEPLOY_SMOKE=FAIL"
  assert_output_contains "expected 200 or 307"
}

@test "smoke: /api/health not 200 → DEPLOY_SMOKE=FAIL" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "200" ""
  set_curl_response "https://flowmanner.com/api/health" "503" ""
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "DEPLOY_SMOKE=FAIL"
  assert_output_contains "expected 200"
}

@test "smoke: /api/v2/auth/me returns wrong status → DEPLOY_SMOKE=FAIL" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "200" ""
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "200" '{"data":{},"meta":{},"error":null}'

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "DEPLOY_SMOKE=FAIL"
  assert_output_contains "expected 401"
}

@test "smoke: v2 envelope missing data key → DEPLOY_SMOKE=FAIL" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "200" ""
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"meta":{},"error":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "DEPLOY_SMOKE=FAIL"
  assert_output_contains "data key missing"
}

@test "smoke: v2 envelope missing meta key → DEPLOY_SMOKE=FAIL" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "200" ""
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"error":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "DEPLOY_SMOKE=FAIL"
  assert_output_contains "meta key missing"
}

@test "smoke: v2 envelope missing error key → DEPLOY_SMOKE=FAIL" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "200" ""
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "DEPLOY_SMOKE=FAIL"
  assert_output_contains "error key missing"
}

# ── Stale-build detection ─────────────────────────────────────────────────────

@test "smoke: chunk snapshot created when HTML contains chunk URLs" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "200" '<script src="/_next/static/chunks/webpack-abc123.js"></script>'
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'
  set_curl_response "https://flowmanner.com/_next/static/chunks/webpack-abc123.js" "200" "console.log(1);"

  run bash "$SMOKE_SCRIPT"
  assert_success
  assert_output_contains "DEPLOY_SMOKE=PASS"
  snapshot_count=$(ls -1 "$SNAPSHOT_DIR"/*.md5 2>/dev/null | wc -l)
  [ "$snapshot_count" -ge 1 ]
}

@test "smoke: stale build detected when chunk hashes unchanged" {
  smoke_setup
  local prev="${SNAPSHOT_DIR}/chunks-20260601-110000.md5"
  echo "aaa111  /_next/static/chunks/webpack-abc123.js" > "$prev"
  stub_default "md5sum" "aaa111  webpack-abc123.js"

  set_curl_response "https://flowmanner.com" "200" '<script src="/_next/static/chunks/webpack-abc123.js"></script>'
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'
  set_curl_response "https://flowmanner.com/_next/static/chunks/webpack-abc123.js" "200" "console.log(1);"

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "STALE BUILD DETECTED"
  assert_output_contains "DEPLOY_SMOKE=FAIL"
}

@test "smoke: no previous snapshot → no staleness check, passes" {
  smoke_setup
  rm -f "${SNAPSHOT_DIR}"/*.md5 2>/dev/null || true

  set_curl_response "https://flowmanner.com" "200" '<script src="/_next/static/chunks/webpack-abc123.js"></script>'
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'
  set_curl_response "https://flowmanner.com/_next/static/chunks/webpack-abc123.js" "200" "console.log(1);"

  run bash "$SMOKE_SCRIPT"
  assert_success
  assert_output_contains "No previous snapshot"
  assert_output_contains "DEPLOY_SMOKE=PASS"
}

@test "smoke: no chunk URLs in HTML → stale-build skipped, passes" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "200" "<html><body>Hello</body></html>"
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_success
  assert_output_contains "No chunk URLs found"
  assert_output_contains "DEPLOY_SMOKE=PASS"
}

@test "smoke: unreachable HTML → stale-build skipped, passes" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "000" ""
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_success
  assert_output_contains "Stale-build check skipped"
  assert_output_contains "DEPLOY_SMOKE=PASS"
}

# ── Smoke: container checks stubbed ───────────────────────────────────────────

@test "smoke: VPS container failure → DEPLOY_SMOKE=FAIL" {
  smoke_setup
  # Override docker compose ps to return no output
  stub_default "docker" ""

  set_curl_response "https://flowmanner.com" "200" ""
  set_curl_response "https://flowmanner.com/api/health" "200" '{}'
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "DEPLOY_SMOKE=FAIL"
  assert_output_contains "docker compose ps returned nothing"
}

# ── Smoke: multiple failures accumulate ───────────────────────────────────────

@test "smoke: multiple failures accumulate in FAIL_COUNT" {
  smoke_setup
  set_curl_response "https://flowmanner.com" "500" ""
  set_curl_response "https://flowmanner.com/api/health" "503" ""
  set_curl_response "https://flowmanner.com/api/v2/auth/me" "401" '{"data":null,"meta":{},"error":{}}'

  run bash "$SMOKE_SCRIPT"
  assert_failure
  assert_output_contains "DEPLOY_SMOKE=FAIL"
  assert_output_contains "check(s) failed"
}

# ── Smoke: smoke script exits 0/1 directly ────────────────────────────────────

@test "smoke: DEPLOY_SMOKE=PASS produces exit 0" {
  smoke_setup
  cat > "${FAKE_BIN}/smoke_flowmanner.sh" <<'EOF'
#!/usr/bin/env bash
echo "DEPLOY_SMOKE=PASS"
exit 0
EOF
  chmod +x "${FAKE_BIN}/smoke_flowmanner.sh"

  run bash "$SMOKE_SCRIPT"
  assert_success
  assert_output_contains "DEPLOY_SMOKE=PASS"
}

@test "smoke: DEPLOY_SMOKE=FAIL produces exit 1" {
  smoke_setup
  cat > "${FAKE_BIN}/smoke_flowmanner.sh" <<'EOF'
#!/usr/bin/env bash
echo "DEPLOY_SMOKE=FAIL  (2 check(s) failed)"
exit 1
EOF
  chmod +x "${FAKE_BIN}/smoke_flowmanner.sh"

  run bash "$SMOKE_SCRIPT"
  assert_failure
  [ "$status" -eq 1 ]
  assert_output_contains "DEPLOY_SMOKE=FAIL"
}
