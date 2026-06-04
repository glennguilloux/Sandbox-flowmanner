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
BATS_FILE="${SCRIPT_DIR}/deploy_flowmanner.bats"

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

if [ ! -f "$BATS_FILE" ]; then
  echo -e "${RED}Test file not found:${NC} $BATS_FILE"
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

# Run bats
set +e
"$BATS_BIN" "${BATS_ARGS[@]}" "$BATS_FILE"
BATS_RC=$?
set -e

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
