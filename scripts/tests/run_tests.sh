#!/usr/bin/env bash
# =============================================================================
# run_tests.sh — FlowManner Deploy Tooling Test Runner
# =============================================================================
# Runs the Bats test suite for deploy_flowmanner.sh and smoke_flowmanner.sh.
#
# Usage:
#   ./run_tests.sh             # Run all tests
#   ./run_tests.sh --verbose   # Run with verbose output
#   ./run_tests.sh --filter <pattern>  # Run tests matching pattern
#
# Exit codes:
#   0 — All tests passed
#   1 — One or more tests failed
#   2 — Bats not installed
#   3 — Test files not found
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Array of Bats test files. pre_deploy_check.bats is a Wave 2 deliverable and
# may be missing on first run — the loop below skips absent files gracefully.
BATS_FILES=(
  "${SCRIPT_DIR}/deploy_flowmanner.bats"
  "${SCRIPT_DIR}/pre_deploy_check.bats"
)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

# ── Flags ─────────────────────────────────────────────────────────────────────

VERBOSE=false
FILTER=""

for arg in "$@"; do
  case "$arg" in
    --verbose|-v) VERBOSE=true ;;
    --filter=*)   FILTER="${arg#--filter=}" ;;
    --filter)     FILTER="$2"; shift ;;
    --help|-h)
      echo "Usage: run_tests.sh [--verbose] [--filter <pattern>]"
      echo ""
      echo "Runs Bats tests for FlowManner deploy tooling."
      echo ""
      echo "Options:"
      echo "  --verbose, -v     Show full test output"
      echo "  --filter <pat>    Run only tests matching pattern"
      echo "  --help, -h        Show this message"
      exit 0
      ;;
    *) echo "Unknown argument: $arg (use --help)" >&2; exit 2 ;;
  esac
done

# ── Check Bats availability ──────────────────────────────────────────────────

BATS_BIN=""
for candidate in bats bats-core /usr/bin/bats /usr/local/bin/bats; do
  if command -v "$candidate" &>/dev/null; then
    BATS_BIN="$candidate"
    break
  fi
done

if [ -z "$BATS_BIN" ]; then
  echo -e "${RED}Bats not found. Install with:${NC}"
  echo "  npm install -g bats        # via npm"
  echo "  sudo apt install bats      # Debian/Ubuntu"
  echo "  brew install bats-core     # macOS"
  exit 2
fi

echo -e "${BOLD}Bats binary:${NC} $BATS_BIN ($($BATS_BIN --version 2>&1 | head -1))"

# ── Check test files exist ────────────────────────────────────────────────────

# Pre-flight: at least one test file must exist (otherwise nothing to run).
# Files in BATS_FILES that don't yet exist are skipped inside the run loop.
found_any=false
for f in "${BATS_FILES[@]}"; do
  if [[ -f "$f" ]]; then
    found_any=true
    break
  fi
done
if ! $found_any; then
  echo -e "${RED}No test files found. Expected at least one of:${NC}"
  for f in "${BATS_FILES[@]}"; do
    echo "  $f"
  done
  exit 3
fi

HELPERS="${SCRIPT_DIR}/helpers.bash"
if [ ! -f "$HELPERS" ]; then
  echo -e "${RED}Helper file not found:${NC} $HELPERS"
  exit 3
fi

# ── Run tests ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  FlowManner Deploy Tooling Tests${NC}"
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
echo ""

BATS_ARGS=()
if $VERBOSE; then
  BATS_ARGS+=(--verbose-run)
fi
if [ -n "$FILTER" ]; then
  BATS_ARGS+=(--filter "$FILTER")
fi

# Run each Bats file, skipping any that don't exist (e.g. Wave 2 placeholder).
# BATS_ARGS carries --verbose-run and/or --filter, preserved from flag parsing.
BATS_RC=0
for f in "${BATS_FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "SKIP: $f (not present yet — Wave 2 deliverable)"
    continue
  fi
  set +e
  "$BATS_BIN" "${BATS_ARGS[@]}" "$f"
  _rc=$?
  set -e
  if [[ $_rc -ne 0 ]]; then
    BATS_RC=$_rc
  fi
done

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"

if [ "$BATS_RC" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}ALL TESTS PASSED${NC}"
  echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}TESTS FAILED (exit code: $BATS_RC)${NC}"
  echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
  exit 1
fi
