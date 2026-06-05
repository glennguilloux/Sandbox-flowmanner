from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

api_v3_router = APIRouter(prefix="/api/v3")

from app.api.v3.auth import router as auth_router
from app.api.v3.auth_oidc import router as oidc_router
from app.api.v3.auth_webhooks import router as webhooks_router
from app.api.v3.teams import router as teams_router
from app.api.v3.workspace_activity import router as activity_router
from app.api.v3.workspace_billing import router as billing_router
from app.api.v3.workspace_invitations import router as invitations_router
from app.api.v3.workspaces import router as workspaces_router

api_v3_router.include_router(auth_router)
api_v3_router.include_router(workspaces_router)
api_v3_router.include_router(invitations_router)
api_v3_router.include_router(teams_router)
api_v3_router.include_router(activity_router)
api_v3_router.include_router(billing_router)
api_v3_router.include_router(oidc_router)
api_v3_router.include_router(webhooks_router)

logger.info("API v3 router initialized with all sub-routers")
