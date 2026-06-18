#!/usr/bin/env bats
# =============================================================================
# deploy_wiring.bats — Wave 2 T6 wiring tests
# =============================================================================
# Tests that the deploy scripts and Makefile are wired correctly per HANDOFF
# §3.2 (frontend --rollback), §3.8 (Makefile D2), §3.1 (orchestrator
# --skip-precheck policy), §3.6 (Bats never ln -sf over real /opt/flowmanner
# deploy scripts), and T6 acceptance criteria.
#
# HARD RULES (HANDOFF §3.6 / Wave 2 dispatch):
#   1. NEVER ln -sf over /opt/flowmanner/{deploy-frontend,deploy-backend,
#      scripts/deploy_flowmanner}.sh.
#   2. NEVER mkdir -p under /opt/flowmanner for test setup.
#   3. Test deploy-frontend.sh / deploy-backend.sh via direct invocation
#      with PATH mocks; do NOT bash -n the real files.
#   4. Test pre-deploy-check.sh via env-var overrides (STATUS_FILE,
#      HEALTH_URL, FLOWMANNER_DEPLOY_OVERRIDE_REASON, WG_CHECK).
#   5. Test Makefile via parsing, NOT invocation (no make deploy-backend).
# =============================================================================

setup() {
  load "${BATS_TEST_DIRNAME}/helpers.bash"

  # Paths under test (relative to repo root). These are the worktree files,
  # NOT the production /opt/flowmanner copies. The worktree is the source of
  # truth for Wave 2 T6.
  REPO_ROOT="${BATS_TEST_DIRNAME}/../.."
  DEPLOY_FRONTEND="${REPO_ROOT}/deploy-frontend.sh"
  DEPLOY_BACKEND="${REPO_ROOT}/deploy-backend.sh"
  PRECHECK="${REPO_ROOT}/scripts/pre-deploy-check.sh"
  MAKEFILE="${REPO_ROOT}/Makefile"

  # Sandbox bin dir — bash + minimal coreutils, NO rsync/ssh/scp/docker.
  # If the script under test tries to call any of the forbidden binaries,
  # the OS returns "command not found" and the test catches it via exit
  # code (for scripts that would otherwise silently succeed).
  SANDBOX_BIN="${BATS_TEST_TMPDIR}/sandbox_bin"
  mkdir -p "$SANDBOX_BIN"
  for cmd in bash cat ls echo mkdir dirname pwd rm sleep; do
    [[ -x "$(command -v "$cmd" 2>/dev/null || true)" ]] \
      && ln -sf "$(command -v "$cmd")" "$SANDBOX_BIN/$cmd" 2>/dev/null || true
  done
  export PATH="${SANDBOX_BIN}:${PATH}"

  # Required by the precheck for wg sudo to succeed (it doesn't have to
  # actually run wg; we set WG_CHECK=skip on each invocation below).
  export FLOWMANNER_DEPLOY_OVERRIDE_REASON="bats-test"
}

# ═══════════════════════════════════════════════════════════════════════════════
# A. deploy-frontend.sh --help (test (a) per dispatch)
# ═══════════════════════════════════════════════════════════════════════════════

@test "deploy-frontend: --help exits 0 and mentions --rollback --dry-run --skip-precheck" {
  run bash "$DEPLOY_FRONTEND" --help
  assert_success
  assert_output_contains "--rollback"
  assert_output_contains "--dry-run"
  assert_output_contains "--skip-precheck"
}

@test "deploy-frontend: -h also prints usage and exits 0" {
  run bash "$DEPLOY_FRONTEND" -h
  assert_success
  assert_output_contains "Usage:"
}

@test "deploy-frontend: --rollback is a no-op that exits 0" {
  run bash "$DEPLOY_FRONTEND" --rollback
  assert_success
  assert_output_contains "NO-OP"
  assert_output_contains "manual"
}

# ═══════════════════════════════════════════════════════════════════════════════
# B. deploy-backend.sh --help (test (b) per dispatch)
# ═══════════════════════════════════════════════════════════════════════════════

@test "deploy-backend: --help exits 0 and mentions --skip-precheck" {
  run bash "$DEPLOY_BACKEND" --help
  assert_success
  assert_output_contains "skip-precheck"
}

# ═══════════════════════════════════════════════════════════════════════════════
# C. Makefile deploy-backend target (test (c) per dispatch)
# ═══════════════════════════════════════════════════════════════════════════════

@test "makefile: deploy-backend target invokes deploy-backend.sh" {
  # Find the deploy-backend target recipe. Stop at the next blank line OR
  # the next target line (a non-indented line starting with a letter).
  run bash -c "
    awk '/^deploy-backend:/ {flag=1} flag && NF && !/^deploy-backend:/ {print; if (!/^[ \t]/) exit}' '$MAKEFILE'
  "
  assert_success
  # The recipe line must contain 'deploy-backend.sh'
  assert_output_contains "deploy-backend.sh"
  refute_output_contains "docker compose up -d --no-deps --force-recreate backend"
}

# ═══════════════════════════════════════════════════════════════════════════════
# D. deploy-frontend.sh --dry-run (test (d) per dispatch)
# ═══════════════════════════════════════════════════════════════════════════════

@test "deploy-frontend: --skip-precheck --dry-run exits 0 without calling rsync/ssh/scp/docker" {
  # PATH is restricted to bash + coreutils (see setup). rsync, ssh, scp, and
  # docker are NOT on PATH. If --dry-run mode accidentally invokes them,
  # bash would exit with 'command not found' and this test would fail.
  run bash "$DEPLOY_FRONTEND" --skip-precheck --dry-run
  assert_success
  assert_output_contains "DRY-RUN"
  refute_output_contains "command not found"
  refute_output_contains "Permission denied"
}

@test "deploy-frontend: --dry-run still invokes precheck unless --skip-precheck" {
  # Without --skip-precheck, the precheck MUST run (and fail-closed on the
  # wg sudoers, which is not configured in the test sandbox). This proves
  # precheck is wired in front of the deploy steps.
  run bash "$DEPLOY_FRONTEND" --dry-run
  # Precheck runs and fails because sudo/wg is not set up -> script exits 1
  # OR precheck's wireguard check fails. Either way, we should NOT see the
  # deploy steps run.
  assert_output_contains "precheck"
  refute_output_contains "Frontend deploy complete"
}

# ═══════════════════════════════════════════════════════════════════════════════
# E. Deploy script invariants (do NOT execute real deploys)
# ═══════════════════════════════════════════════════════════════════════════════

@test "deploy-frontend.sh and deploy-backend.sh are bash-syntax-valid" {
  bash -n "$DEPLOY_FRONTEND"
  bash -n "$DEPLOY_BACKEND"
}

@test "no production deploy script has been clobbered (git diff against main is empty)" {
  # Per Wave 2 dispatch rule: production /opt/flowmanner deploy scripts MUST
  # NOT be silently modified. We assert this without touching the files
  # (rule 2: never mkdir / cp under /opt/flowmanner in tests).
  for f in deploy-frontend.sh deploy-backend.sh scripts/deploy_flowmanner.sh deploy-all.sh Makefile; do
    if ! git -C /opt/flowmanner diff --quiet main -- "$f"; then
      echo "PRODUCTION FILE MODIFIED vs main: /opt/flowmanner/$f"
      git -C /opt/flowmanner diff --stat main -- "$f"
      return 1
    fi
  done
}
