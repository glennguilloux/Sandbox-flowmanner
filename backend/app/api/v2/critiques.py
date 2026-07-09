"""V2 /critiques endpoints — Critic Inspection API (D30-60, T28).

The Programs brief UI, the future "show alternatives" UI, and any
ad-hoc diagnostic tooling hit these endpoints. They are thin
envelope-wrapping layers over ``CritiqueService`` — no business logic
in the route.

Two endpoints (per the End-of-Galaxy D30-60 plan §T28):

| Method | Path                  | Purpose                                       |
|--------|-----------------------|-----------------------------------------------|
| GET    | /critiques            | Paginated list (filters: mission, program,    |
|        |                       | critic_kind, min_score_overall, pagination)   |
| GET    | /critiques/{id}       | Get one critique by id                        |

T28 is read-only — there is no ``POST /critiques`` endpoint. New
critiques are created internally by the executor hook from T27
(``CritiqueService.create_from_critic``) after a critic run completes.

Error mapping (leak avoidance — ``NotFound`` surfaces as 404 in all
cases to prevent existence-disclosure across the workspace boundary):

| Domain exception            | HTTP | Envelope code                |
|-----------------------------|------|------------------------------|
| CritiqueNotFound            | 404  | CRITIQUE_NOT_FOUND           |
| CritiqueValidationError     | 422  | CRITIQUES_VALIDATION_ERROR   |
| CritiqueServiceError (other)| 500  | CRITIQUE_INTERNAL_ERROR      |
| Pydantic RequestValidationError | 422 | CRITIQUES_VALIDATION_ERROR |
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_workspace_id
from app.api.v2.base import ErrorDetail, ResponseMeta, ok, paginated
from app.models.user import User
from app.schemas.critique import (
    CritiqueListResponse,
    CritiqueResponse,
)
from app.services.critique_service import (
    CritiqueNotFound,
    CritiqueService,
    CritiqueServiceError,
    CritiqueValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/critiques", tags=["v2-critiques"])


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic validation handler — wraps FastAPI's default 422 into the v2
# envelope with code=CRITIQUES_VALIDATION_ERROR (project convention is to
# use a domain-specific code rather than the generic VALIDATION_ERROR, so
# clients can branch on it without parsing the message).
#
# NOTE: ``APIRouter`` has no ``exception_handler`` decorator (only
# ``FastAPI`` does), so this handler is registered from
# ``app/api/v2/__init__.py`` after the router is included. Exported
# here as a module attribute for that wiring.
# ═══════════════════════════════════════════════════════════════════════════


async def critiques_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    error = ErrorDetail(
        code="CRITIQUES_VALIDATION_ERROR",
        message="Request validation failed",
        details={"errors": exc.errors()},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "data": None,
            "meta": ResponseMeta().model_dump(),
            "error": error.model_dump(),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# Error envelope helper (local copy of the personal_memory.py pattern).
# Returns a JSONResponse with the correct HTTP status AND the v2 envelope
# — ``err()`` in base.py is a dict-only helper and ignores status_code.
# ═══════════════════════════════════════════════════════════════════════════


def _envelope_error(
    code: str,
    message: str,
    http_status: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    error = ErrorDetail(code=code, message=message, details=details)
    return JSONResponse(
        status_code=http_status,
        content={
            "data": None,
            "meta": ResponseMeta().model_dump(),
            "error": error.model_dump(),
        },
    )


async def _get_service(
    db: AsyncSession = Depends(get_db),
) -> CritiqueService:
    return CritiqueService(db)


# ═══════════════════════════════════════════════════════════════════════════
# 1. GET /critiques — paginated list
# ═══════════════════════════════════════════════════════════════════════════


@router.get("", response_model=None)
async def list_critiques(
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    service: CritiqueService = Depends(_get_service),
    mission_id: uuid.UUID | None = Query(default=None),
    program_id: uuid.UUID | None = Query(default=None),
    critic_kind: str | None = Query(default=None),
    min_score_overall: float | None = Query(default=None, ge=0.0, le=1.0),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    """Paginated list of critiques for the current user+workspace.

    Filters are all optional. The route is the only place where
    ``page``/``per_page`` are converted to ``offset``/``limit`` for
    the service layer (service uses limit/offset; route exposes
    page/per_page for clients — the v2 envelope convention).
    """
    # Convert page/per_page to offset/limit for the service.
    offset = (page - 1) * per_page
    try:
        items, total = await service.list(
            user_id=user.id,
            workspace_id=workspace_id,
            mission_id=mission_id,
            program_id=program_id,
            critic_kind=critic_kind,
            min_score_overall=min_score_overall,
            limit=per_page,
            offset=offset,
        )
    except CritiqueValidationError as exc:
        return _envelope_error(
            "CRITIQUES_VALIDATION_ERROR",
            str(exc),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except CritiqueServiceError:
        logger.exception("critiques.list failed")
        return _envelope_error(
            "CRITIQUE_INTERNAL_ERROR",
            "An internal critique error occurred",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return paginated(
        items=[CritiqueResponse.model_validate(c).model_dump(mode="json") for c in items],
        total=total,
        page=page,
        per_page=per_page,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. GET /critiques/{id} — get one
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/{critique_id}", response_model=None)
async def get_critique(
    critique_id: uuid.UUID,
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    service: CritiqueService = Depends(_get_service),
):
    """Get a single critique by id, scoped to (user_id, workspace_id).

    Returns 404 with code ``CRITIQUE_NOT_FOUND`` if the id does not
    exist OR if the row exists but belongs to another (user,
    workspace) tuple — the workspace-isolation guardrail surfaces a
    "not found" to the caller to avoid existence-disclosure.
    """
    try:
        critique = await service.get(
            user_id=user.id,
            workspace_id=workspace_id,
            critique_id=critique_id,
        )
    except CritiqueNotFound as exc:
        return _envelope_error(
            "CRITIQUE_NOT_FOUND",
            str(exc),
            status.HTTP_404_NOT_FOUND,
        )
    except CritiqueValidationError as exc:
        return _envelope_error(
            "CRITIQUES_VALIDATION_ERROR",
            str(exc),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except CritiqueServiceError:
        logger.exception("critiques.get failed")
        return _envelope_error(
            "CRITIQUE_INTERNAL_ERROR",
            "An internal critique error occurred",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return ok(CritiqueResponse.model_validate(critique).model_dump(mode="json"))


# Re-export the paginated wrapper for the import surface; tests may
# import it to construct fixtures.
__all__ = [
    "CritiqueListResponse",
    "CritiqueResponse",
    "critiques_validation_handler",
    "router",
]
