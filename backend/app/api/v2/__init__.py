"""API v2 Router — clean paths, standardized response envelope, GraphQL.

v2 is a genuine redesign, not a wrapper around v1.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

api_v2_router = APIRouter(prefix="/api/v2")

from app.api.v2.agents import router as agents_router
from app.api.v2.auth import router as auth_router
from app.api.v2.chat import router as chat_router
from app.api.v2.missions import router as missions_router
from app.api.v2.search import router as search_router
from app.api.v2.workspaces import router as workspaces_router

api_v2_router.include_router(auth_router)
api_v2_router.include_router(missions_router)
api_v2_router.include_router(agents_router)
api_v2_router.include_router(chat_router)
api_v2_router.include_router(workspaces_router)
api_v2_router.include_router(search_router)

from app.api.v2.dashboard import router as dashboard_router
from app.api.v2.integrations import router as integrations_router
from app.api.v2.integrations_actions import router as integrations_actions_router
from app.api.v2.integrations_oauth import router as integrations_oauth_router
from app.api.v2.openapi import router as openapi_router

api_v2_router.include_router(dashboard_router)
api_v2_router.include_router(integrations_router)
api_v2_router.include_router(integrations_oauth_router)
api_v2_router.include_router(integrations_actions_router)
api_v2_router.include_router(openapi_router)

# Blueprint + Run endpoints (Phase 10)
from app.api.v2.blueprints import router as blueprints_router
from app.api.v2.runs import router as runs_router

api_v2_router.include_router(blueprints_router)
api_v2_router.include_router(runs_router)

# Regression / Assertion endpoints (Phase 0 — the moat)
from app.api.v2.regression import router as regression_router

api_v2_router.include_router(regression_router)

logger.info("API v2 router initialized — %d sub-routers", len(api_v2_router.routes))
