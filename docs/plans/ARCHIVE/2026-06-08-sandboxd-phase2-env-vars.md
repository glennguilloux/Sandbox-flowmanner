# sandboxd Phase 2 — Environment Variable Changes
#
# Generated: 2026-06-08
# Token: 37fb6669393046712d2b68be235c082ee4d3a82160f5d18450a15205d5ad3046
#
# ═══════════════════════════════════════════════════════════════════════
# STEP 1: FlowManner .env (/opt/flowmanner/.env)
# ═══════════════════════════════════════════════════════════════════════
# Add these entries (currently ZERO SANDBOXD_* entries exist):
#
SANDBOXD_API_URL=http://10.0.4.1:9090
SANDBOXD_AUTH_TOKEN=37fb6669393046712d2b68be235c082ee4d3a82160f5d18450a15205d5ad3046
SANDBOXD_PREVIEW_DOMAIN=preview.flowmanner.com
SANDBOXD_ENABLED=true
SANDBOXD_DEFAULT_TEMPLATE=react-standard

# ═══════════════════════════════════════════════════════════════════════
# STEP 2: sandboxd .env (/mnt/apps/Softwares2/sandboxd/.env)
# ═══════════════════════════════════════════════════════════════════════
# UPDATE existing entries:
#
# PREVIEW_DOMAIN=preview.flowmanner.com          # was: localhost
# PREVIEW_ENTRYPOINT=websecure                    # was: web
# PREVIEW_TLS=true                                # was: false
# SANDBOXD_API_AUTH_DISABLED=false                # was: true
# SANDBOXD_API_TOKENS=flowmanner=37fb6669393046712d2b68be235c082ee4d3a82160f5d18450a15205d5ad3046  # was: empty
# SANDBOXD_SET_MEMORY_HIGH=true                   # was: false

# ═══════════════════════════════════════════════════════════════════════
# STEP 3: Infrastructure (manual)
# ═══════════════════════════════════════════════════════════════════════
#
# 1. IONOS DNS: Add A record *.preview.flowmanner.com → 74.208.115.142
# 2. VPS certbot: certbot certonly --manual --preferred-challenges dns \
#      -d '*.preview.flowmanner.com'
# 3. Copy certs to /etc/nginx/certs/preview.flowmanner.com/

# ═══════════════════════════════════════════════════════════════════════
# STEP 4: Restart services
# ═══════════════════════════════════════════════════════════════════════
#
# Homelab:
#   bash /opt/flowmanner/deploy-backend.sh --migrate
#
# sandboxd:
#   cd /mnt/apps/Softwares2/sandboxd && docker compose down && docker compose up -d
#
# VPS (deploys nginx config):
#   bash /opt/flowmanner/deploy-frontend.sh
