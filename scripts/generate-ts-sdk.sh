#!/usr/bin/env bash
# ============================================================
# generate-ts-sdk.sh — Regenerate TypeScript SDK from live OpenAPI spec
# ============================================================
set -euo pipefail

PROJECT_ROOT="/opt/flowmanner"
VPS_HOST="74.208.115.142"
VPS_USER="root"
SSH_CMD="ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new"
VPS_FRONTEND="/opt/flowmanner/frontend"
OPENAPI_SPEC="${PROJECT_ROOT}/openapi.json"

echo "=== TypeScript SDK Generation ==="

# Step 1: Generate OpenAPI spec from backend container
echo "[1/4] Generating OpenAPI spec from backend container..."
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

# Step 2: Copy spec to VPS
echo "[2/4] Copying spec to VPS..."
${SSH_CMD} scp -o StrictHostKeyChecking=accept-new \
  "${OPENAPI_SPEC}" "${VPS_USER}@${VPS_HOST}:/tmp/openapi.json"
echo "  Spec copied to VPS"

# Step 3: Run openapi-typescript-codegen on VPS
echo "[3/4] Generating TypeScript SDK on VPS..."
${SSH_CMD} "${VPS_USER}@${VPS_HOST}" \
  "cd ${VPS_FRONTEND} && npx openapi-typescript-codegen --input /tmp/openapi.json --output src/lib/sdk/"
echo "  TypeScript SDK generated"

# Step 4: Cleanup temp file on VPS
echo "[4/4] Cleaning up..."
${SSH_CMD} "${VPS_USER}@${VPS_HOST}" \
  "rm -f /tmp/openapi.json"

echo "=== TypeScript SDK generation complete ==="
