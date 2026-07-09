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

# Mission Programs (T11) — thin CQRS wrappers with idempotency + rate limits
from app.api.v2.programs import router as programs_router

api_v2_router.include_router(programs_router)

# Personal Memory MVP (D0-30, T23) — Memory Inspector API
# Import the router AND register a domain-specific Pydantic validation
# handler on the main FastAPI app so 422s from the personal_memory
# routes get ``PERSONAL_MEMORY_VALIDATION_ERROR`` instead of FastAPI's
# generic ``{"detail": [...]}`` default.
from fastapi.exceptions import RequestValidationError

from app.api.v2.personal_memory import (
    pm_validation_handler,
)
from app.api.v2.personal_memory import (
    router as personal_memory_router,
)
from app.main_fastapi import app as _fastapi_app

api_v2_router.include_router(personal_memory_router)
_fastapi_app.add_exception_handler(RequestValidationError, pm_validation_handler)

# Critic Inspection API (D30-60, T28) — read-only /critiques surface for
# the Programs brief UI and the future "show alternatives" UI. Mirrors
# the personal_memory section above: import router + validation handler,
# include router, register the domain-specific 422 handler on the main
# FastAPI app.
from app.api.v2.critiques import (
    critiques_validation_handler,
)
from app.api.v2.critiques import (
    router as critiques_router,
)

api_v2_router.include_router(critiques_router)
_fastapi_app.add_exception_handler(RequestValidationError, critiques_validation_handler)

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

# Marketplace — tool/capability discovery, install, reviews
from app.api.v2.marketplace import router as marketplace_router

api_v2_router.include_router(marketplace_router)

# Tool discovery — enumerate tools the user is authorized to invoke
from app.api.v2.tools import router as tools_router

api_v2_router.include_router(tools_router)

# Prompt Versioning (Phase 6) — versioned system prompts per workspace
from app.api.v2.prompts import router as prompts_router

api_v2_router.include_router(prompts_router)

# Eval Run API (Phase 6) — trigger eval suites and view results
from app.api.v2.eval_runs import router as eval_runs_router

api_v2_router.include_router(eval_runs_router)

# Contact form — public endpoint for submitting inquiries
from app.api.v2.contact import router as contact_router

api_v2_router.include_router(contact_router)

# T1 — Blog + Roadmap v2 read-only routers
from app.api.v2.blog import router as blog_router
from app.api.v2.roadmap import router as roadmap_router

api_v2_router.include_router(blog_router)
api_v2_router.include_router(roadmap_router)

logger.info("API v2 router initialized — %d sub-routers", len(api_v2_router.routes))
