#!/bin/bash
# rebuild-sandboxd-base.sh — Rebuild sandboxd-base:1.0.0 and install template deps
#
# Run from the homelab where sandboxd is deployed.
# Usage: bash sandboxd/rebuild-sandboxd-base.sh [TEMPLATE_NAME]
#
# TEMPLATE_NAME defaults to "python.img" (the current SANDBOXD_DEFAULT_TEMPLATE).
# Pass an explicit name to rebuild deps for a different template, e.g.:
#   bash sandboxd/rebuild-sandboxd-base.sh react-standard.img
#
# This script:
#   1. Rebuilds sandboxd-base:1.0.0 with the wrapper fix + node/npm + RUNTIMED_DEV_CMD
#   2. If the named template has a package.json, runs `npm install` inside the image
#   3. Verifies the image works
#
# Notes:
#   - The npm-install step is a no-op for non-Node templates (e.g., python.img has
#     no package.json) and is skipped silently.
#   - The legacy react-standard template name is still supported as an explicit
#     argument for users who keep it as a fallback.
#
# ⚠️  After running this, restart sandboxd to pick up the new image:
#     docker compose -f <sandboxd-compose> restart sandboxd

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

TEMPLATE_NAME="${1:-python.img}"
TEMPLATE_DIR="/var/lib/sandboxed/templates/${TEMPLATE_NAME}/app"

echo ">>> Building sandboxd-base:1.0.0 with fixes..."
docker build -t sandboxd-base:1.0.0 -f "$SCRIPT_DIR/Dockerfile.sandboxd-base" "$PROJECT_ROOT"

echo ">>> Verifying node/npm in image..."
docker run --rm --entrypoint='' sandboxd-base:1.0.0 node --version
docker run --rm --entrypoint='' sandboxd-base:1.0.0 npm --version

echo ">>> Verifying RUNTIMED_DEV_CMD..."
docker run --rm --entrypoint='' sandboxd-base:1.0.0 sh -c 'echo $RUNTIMED_DEV_CMD'

if [ -d "$TEMPLATE_DIR" ]; then
    if [ -f "$TEMPLATE_DIR/package.json" ]; then
        echo ">>> Installing npm dependencies in $TEMPLATE_NAME template..."
        docker run --rm --entrypoint='' \
            -v "$TEMPLATE_DIR:/app" -w /app \
            sandboxd-base:1.0.0 npm install
        echo ">>> Template deps installed."
    else
        echo ">>> No package.json in $TEMPLATE_DIR — skipping npm install (normal for non-Node templates like $TEMPLATE_NAME)."
    fi
else
    echo ">>> WARNING: Template dir not found at $TEMPLATE_DIR"
    echo "    Skipping npm install. Install manually after creating the template."
fi

echo ""
echo ">>> Done. Restart sandboxd to pick up the new image:"
echo "    docker compose -f <sandboxd-compose> restart sandboxd"
