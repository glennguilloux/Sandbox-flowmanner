#!/bin/bash
set -e

SSH_KEY="${SSH_KEY:-$HOME/.ssh/vps_flowmanner_new}"
VPS_HOST="${VPS_HOST:-74.208.115.142}"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -i $SSH_KEY"

echo "=== Rsyncing frontend to VPS ==="
rsync -avz --progress --delete \
  -e "ssh $SSH_OPTS" \
  --exclude node_modules --exclude .next --exclude .git \
  /home/glenn/FlowmannerV2-frontend/ \
  root@${VPS_HOST}:/opt/flowmanner/frontend/

echo "=== Rebuilding frontend on VPS ==="
ssh $SSH_OPTS root@${VPS_HOST} "cd /opt/flowmanner && docker compose build frontend && docker compose up -d --no-deps frontend"

echo "=== Syncing nginx config ==="
ssh $SSH_OPTS root@${VPS_HOST} "mkdir -p /opt/flowmanner/nginx"
scp $SSH_OPTS /opt/flowmanner/nginx/default.conf root@${VPS_HOST}:/opt/flowmanner/nginx/default.conf

echo "=== Restarting nginx ==="
ssh $SSH_OPTS root@${VPS_HOST} "cd /opt/flowmanner && docker compose restart nginx"

echo "=== Done ==="
