#!/usr/bin/env bash
# ============================================================
# generate-python-sdk.sh — Regenerate Python SDK from live OpenAPI spec
# ============================================================
set -euo pipefail

PROJECT_ROOT="/opt/flowmanner"
OPENAPI_SPEC="${PROJECT_ROOT}/openapi.json"
SDK_DIR="${PROJECT_ROOT}/sdk-python"
VENV="${PROJECT_ROOT}/backend/.venv"

echo "=== Python SDK Generation ==="

# Step 1: Generate OpenAPI spec from backend container
echo "[1/3] Generating OpenAPI spec from backend container..."
docker exec backend python -c "
import json, sys, warnings, logging
sys.path.insert(0, '/app')
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
from app.main_fastapi import app
spec = app.openapi()
json.dump(spec, sys.stdout, indent=2)
" > "${OPENAPI_SPEC}" 2>/dev/null
echo "  Spec generated: $(wc -c < "${OPENAPI_SPEC}") bytes"

# Step 2: Ensure openapi-python-client is installed
echo "[2/3] Checking openapi-python-client..."
"${VENV}/bin/pip" install -q openapi-python-client 2>/dev/null || {
  echo "  Installing openapi-python-client..."
  "${VENV}/bin/pip" install openapi-python-client
}
echo "  openapi-python-client ready"

# Step 3: Generate Python SDK
echo "[3/3] Generating Python SDK..."
cd "${SDK_DIR}"
"${VENV}/bin/openapi-python-client" generate --path "${OPENAPI_SPEC}" --output-path . --overwrite
echo "  Python SDK generated"

echo "=== Python SDK generation complete ==="
