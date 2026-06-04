#!/bin/bash
set -e

ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new root@74.208.115.142 \
  "cd /opt/flowmanner && docker compose restart nginx"
