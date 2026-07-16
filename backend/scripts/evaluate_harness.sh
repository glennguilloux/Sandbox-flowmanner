#!/usr/bin/env bash
# evaluate_harness.sh — real evaluator shim for the harness-evolution meta-optimizer.
#
# Usage (exactly as the prototype invokes it):
#   evaluate_harness.sh <candidate.json> <split>
#
# Emits ONE JSON line on stdout:
#   {"accuracy": <float>, "cost_usd": <float>, "latency_ms": <float>, "safety_pass": <bool>}
#
# Environment (optional):
#   DATABASE_URL   backend Postgres (required for a REAL run; the evaluator
#                 executes through UnifiedExecutor). If unset, the script exits
#                 non-zero with a clear message instead of fabricating metrics.
#   EVAL_DATA_DIR directory holding <split>.jsonl golden sets for accuracy.
#   PYTHON        interpreter to use (defaults to the backend venv python).
#
# The prototype (harness_meta_optimizer.py) sets HARNESS_EVAL_COMMAND to this
# script and parses the LAST non-empty stdout line.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# backend/ is the parent of scripts/.
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PYTHON:-${BACKEND_DIR}/.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3 || true)"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set. A real evaluation runs through UnifiedExecutor" >&2
  echo "       against the live backend database. Refusing to emit fabricated metrics." >&2
  exit 2
fi

export PYTHONPATH="${BACKEND_DIR}:${PYTHONPATH:-}"

exec "${PYTHON}" -m app.services.substrate.evaluate_harness "$@"
