#!/bin/bash
cp /etc/letsencrypt/live/flowmanner.com/fullchain.pem /opt/flowmanner/certs/
cp /etc/letsencrypt/live/flowmanner.com/privkey.pem /opt/flowmanner/certs/
docker restart flowmanner-nginx 2>/dev/null || true
