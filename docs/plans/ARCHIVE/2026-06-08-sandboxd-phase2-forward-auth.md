# sandboxd Forward Auth — Traefik Middleware Config
#
# This configures Traefik's forward-auth middleware to gate sandbox
# preview URLs behind FlowManner session authentication.
#
# Only authenticated users can access sandbox previews.
# Unauthenticated requests are redirected to the FlowManner login page.
#
# DEPLOYMENT:
#   Add the middleware label to sandboxd's Traefik routing config.
#   The /forward-auth endpoint is served by sandboxd itself (port 9090).
#
# In sandboxd's docker-compose.yml, add to the Traefik labels:
#
#   - "traefik.http.routers.sandbox-preview.middlewares=flowmanner-auth@file"
#   - "traefik.http.middlewares.flowmanner-auth.forwardauth.address=http://localhost:9090/forward-auth"
#   - "traefik.http.middlewares.flowmanner-auth.forwardauth.trustForwardHeader=true"
#   - "traefik.http.middlewares.flowmanner-auth.forwardauth.authResponseHeaders=X-Forwarded-User"
#
# OR via Traefik dynamic config file (traefik-dynamic.yml):
#
# http:
#   middlewares:
#     flowmanner-auth:
#       forwardAuth:
#         address: "http://localhost:9090/forward-auth"
#         trustForwardHeader: true
#         authResponseHeaders:
#           - "X-Forwarded-User"
#
# Then apply to sandbox routers:
#   - "traefik.http.routers.sandbox.rule=HostRegexp(`{subdomain:.+}.preview.flowmanner.com`)"
#   - "traefik.http.routers.sandbox.middlewares=flowmanner-auth@file"
#
# ── How it works ──────────────────────────────────────────────────────
#
# 1. Browser requests https://s-abc-3000.preview.flowmanner.com
# 2. Traefik receives request, sees forward-auth middleware
# 3. Traefik sends GET to sandboxd /forward-auth with original request headers
# 4. sandboxd checks for FlowManner session cookie or Bearer token
# 5. If authenticated → 200, proxy to sandbox container
#    If not → 302 redirect to https://flowmanner.com/auth/signin
#
# ── Rollback ──────────────────────────────────────────────────────────
#
# To disable forward auth (preview URLs become public):
#   Remove the middleware label from sandboxd's Traefik config
#   and restart sandboxd.
