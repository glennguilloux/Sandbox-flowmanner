# DeepSeek Work Package: 5 Tasks (Priority Order)

## Context
Flowmanner is an AI workflow automation platform (Next.js frontend + FastAPI backend). We've done the plumbing — all endpoints work, marketplace auto-seeds, dashboard shows real data. Now we need to fix 5 medium-leverage issues that prevent this from being a real product.

## Task Summary

| # | Task | File(s) | Effort | Impact |
|---|------|---------|--------|--------|
| 1 | Mission Executor — eliminate silent failures | `app/services/mission_executor.py` | 3-4 hrs | Missions actually report errors and retry |
| 2 | Model Router — fix BYOK key resolution | `app/services/model_router.py` + new model + migration | 3-4 hrs | Users can bring their own API keys |
| 3 | Marketplace — replace generic listings | `app/services/marketplace_service.py` | 30 min | Listings people actually want |
| 4 | Analytics events — instrument real metrics | New: `analytics.py` model, service, routes + migration | 4-5 hrs | Dashboard shows activation, retention, engagement |
| 5 | Workspace onboarding — 4-screen wizard | `onboarding/page-client.tsx` + dashboard redirect | 3-4 hrs | New users get a workspace in 18 seconds |

Total estimated effort: ~15-18 hours

## Execution Order
Run tasks 1-3 first (backend, can be done in parallel). Then task 4 (backend). Then task 5 (frontend, depends on task 4's workspace API being stable).

## Important Notes
- All backend code is in `/opt/flowmanner/backend/` (homelab)
- All frontend code is in `/home/glenn/FlowmannerV2-frontend/` (homelab)
- Backend runs in Docker — after changes, rebuild: `cd /opt/flowmanner && docker compose build backend && docker compose up -d --force-recreate --no-deps backend`
- Frontend deploys via rsync to VPS — after changes, rsync + docker build on VPS
- NEVER edit files on the VPS directly
- All changes must pass existing tests before deploying
