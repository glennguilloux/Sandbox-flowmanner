#!/bin/bash
# rebuild-sandboxd-base.sh — Rebuild sandboxd-base:1.0.0 and install template deps
#
# Run from the homelab where sandboxd is deployed.
# Usage: bash sandboxd/rebuild-sandboxd-base.sh
#
# This script:
#   1. Rebuilds sandboxd-base:1.0.0 with the wrapper fix + node/npm + RUNTIMED_DEV_CMD
#   2. Installs npm dependencies in the react-standard template directory
#   3. Verifies the image works
#
# ⚠️  After running this, restart sandboxd to pick up the new image:
#     docker compose -f <sandboxd-compose> restart sandboxd

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo ">>> Building sandboxd-base:1.0.0 with fixes..."
docker build -t sandboxd-base:1.0.0 -f "$SCRIPT_DIR/Dockerfile.sandboxd-base" "$PROJECT_ROOT"

echo ">>> Verifying node/npm in image..."
docker run --rm --entrypoint='' sandboxd-base:1.0.0 node --version
docker run --rm --entrypoint='' sandboxd-base:1.0.0 npm --version

echo ">>> Verifying RUNTIMED_DEV_CMD..."
docker run --rm --entrypoint='' sandboxd-base:1.0.0 sh -c 'echo $RUNTIMED_DEV_CMD'

TEMPLATE_DIR="/var/lib/sandboxed/templates/react-standard.img/app"
if [ -d "$TEMPLATE_DIR" ]; then
    echo ">>> Installing npm dependencies in react-standard template..."
    docker run --rm --entrypoint='' \
        -v "$TEMPLATE_DIR:/app" -w /app \
        sandboxd-base:1.0.0 npm install
    echo ">>> Template deps installed."
else
    echo ">>> WARNING: Template dir not found at $TEMPLATE_DIR"
    echo "    Skipping npm install. Install manually after creating the template."
fi

echo ""
echo ">>> Done. Restart sandboxd to pick up the new image:"
echo "    docker compose -f <sandboxd-compose> restart sandboxd"
