"""V2 /personal_memory endpoints — Memory Inspector API.

The Memory Inspector UI tree view, the ``[memory]`` citation cross-link
UX, and the "Why did you think this?" inspection all hit these
endpoints. They are thin envelope-wrapping layers over
``PersonalMemoryService`` — no business logic in the route.

Five endpoints (per the End-of-Galaxy D0-30 plan §T23):

| Method | Path                          | Purpose                                  |
|--------|-------------------------------|------------------------------------------|
| POST   | /personal_memory/recall       | Search claims by query + filters         |
| GET    | /personal_memory/inspector    | Paginated list for the Inspector UI      |
| PATCH  | /personal_memory/claims/{id}  | Update editable fields (PATCH semantics) |
| DELETE | /personal_memory/claims/{id}  | Hard forget (204)                        |
| POST   | /personal_memory/forget       | Soft/hard forget (body controls `hard`)  |

Error mapping (leak avoidance — ``NotFound`` surfaces as 404 in all
cases to prevent existence-disclosure across the workspace boundary):

| Domain exception                          | HTTP | Envelope code                       |
|-------------------------------------------|------|-------------------------------------|
| PersonalMemoryClaimNotFound               | 404  | PERSONAL_MEMORY_CLAIM_NOT_FOUND     |
| PersonalMemoryValidationError (ValueError)| 422  | PERSONAL_MEMORY_VALIDATION_ERROR    |
| PersonalMemoryError (other)               | 500  | PERSONAL_MEMORY_INTERNAL_ERROR      |
| Pydantic RequestValidationError           | 422  | PERSONAL_MEMORY_VALIDATION_ERROR    |
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
from app.schemas.personal_memory import (
    PersonalMemoryClaimResponse,
    PersonalMemoryClaimUpdate,
    PersonalMemoryCorrectionListResponse,
    PersonalMemoryCorrectionResponse,
    PersonalMemoryForgetRequest,
    PersonalMemoryProvenanceResponse,
    PersonalMemoryRecallItem,
    PersonalMemoryRecallRequest,
    PersonalMemoryRecallResponse,
)
from app.services.memory_correction_service import MemoryCorrectionService
from app.services.personal_memory_service import (
    PersonalMemoryClaimNotFound,
    PersonalMemoryError,
    PersonalMemoryService,
    PersonalMemoryValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personal_memory", tags=["v2-personal-memory"])


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic validation handler — wraps FastAPI's default 422 into the v2
# envelope with code=PERSONAL_MEMORY_VALIDATION_ERROR (project convention
# is to use a domain-specific code rather than the generic VALIDATION_ERROR,
# so clients can branch on it without parsing the message).
#
# NOTE: ``APIRouter`` has no ``exception_handler`` decorator (only
# ``FastAPI`` does), so this handler is registered from
# ``app/api/v2/__init__.py`` after the router is included. Exported
# here as a module attribute for that wiring.
# ═══════════════════════════════════════════════════════════════════════════


async def pm_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    error = ErrorDetail(
        code="PERSONAL_MEMORY_VALIDATION_ERROR",
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
# Error envelope helper (local copy of the programs.py pattern).
# Returns a JSONResponse with the correct HTTP status AND the v2 envelope
# — `err()` in base.py is a dict-only helper and ignores status_code.
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


async def _get_service(db: AsyncSession = Depends(get_db)) -> PersonalMemoryService:
    return PersonalMemoryService(db)


async def _commit(db: AsyncSession) -> None:
    """Commit the service's flushed writes (per services/AGENTS.md rule 3,
    the service NEVER commits; the route owns the transaction)."""
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# 1. POST /recall — search claims
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/recall")
async def recall_claims(
    payload: PersonalMemoryRecallRequest,
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    service: PersonalMemoryService = Depends(_get_service),
) -> dict[str, Any]:
    items, total = await service.recall(
        user_id=user.id,
        workspace_id=workspace_id,
        query=payload.query,
        scopes=[s.value for s in payload.scopes] if payload.scopes else None,
        top_k=payload.top_k,
        min_confidence=payload.min_confidence,
    )
    return ok(
        PersonalMemoryRecallResponse(
            items=[PersonalMemoryRecallItem.model_validate(c) for c in items],
            total=total,
        ).model_dump(mode="json")
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. GET /inspector — paginated list for the Memory Inspector UI
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/inspector")
async def inspector(
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    service: PersonalMemoryService = Depends(_get_service),
    scope: str | None = Query(default=None),
    claim_type: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    # Service uses limit/offset; route exposes page/per_page for clients.
    offset = (page - 1) * per_page
    items, total = await service.list_for_user(
        user_id=user.id,
        workspace_id=workspace_id,
        scope=scope,
        claim_type=claim_type,
        include_deleted=include_deleted,
        limit=per_page,
        offset=offset,
    )
    return paginated(
        items=[PersonalMemoryClaimResponse.model_validate(c).model_dump(mode="json") for c in items],
        total=total,
        page=page,
        per_page=per_page,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. PATCH /claims/{id} — update editable fields (PATCH semantics)
# ═══════════════════════════════════════════════════════════════════════════


@router.patch("/claims/{claim_id}", response_model=None)
async def update_claim(
    claim_id: uuid.UUID,
    patch: PersonalMemoryClaimUpdate,
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    service: PersonalMemoryService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    try:
        claim = await service.update(
            user_id=user.id,
            workspace_id=workspace_id,
            claim_id=claim_id,
            **patch.model_dump(exclude_unset=True),
        )
    except PersonalMemoryClaimNotFound as exc:
        return _envelope_error(
            "PERSONAL_MEMORY_CLAIM_NOT_FOUND",
            str(exc),
            status.HTTP_404_NOT_FOUND,
        )
    except PersonalMemoryValidationError as exc:
        return _envelope_error(
            "PERSONAL_MEMORY_VALIDATION_ERROR",
            str(exc),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except PersonalMemoryError:
        logger.exception("personal_memory.update failed")
        return _envelope_error(
            "PERSONAL_MEMORY_INTERNAL_ERROR",
            "An internal personal memory error occurred",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    # Commit the service's flushed write (services/AGENTS.md rule 3).
    await _commit(db)
    return ok(PersonalMemoryClaimResponse.model_validate(claim).model_dump(mode="json"))


# ═══════════════════════════════════════════════════════════════════════════
# 4. DELETE /claims/{id} — hard forget (204)
# ═══════════════════════════════════════════════════════════════════════════


@router.delete("/claims/{claim_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def hard_forget_claim(
    claim_id: uuid.UUID,
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    service: PersonalMemoryService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    """Hard-delete a claim. Returns 204 on success, 404 envelope on not-found.

    204 is the project convention for DELETE (per v2 AGENTS.md rule 7).
    404 returns the v2 envelope so clients can distinguish "exists in
    another workspace" from "genuinely missing" without leaking the
    distinction.
    """
    try:
        await service.forget(
            user_id=user.id,
            workspace_id=workspace_id,
            claim_id=claim_id,
            hard=True,
        )
    except PersonalMemoryClaimNotFound as exc:
        return _envelope_error(
            "PERSONAL_MEMORY_CLAIM_NOT_FOUND",
            str(exc),
            status.HTTP_404_NOT_FOUND,
        )
    # Commit the service's flushed write (services/AGENTS.md rule 3).
    await _commit(db)
    return None  # FastAPI turns 204 + None body into a real 204


# ═══════════════════════════════════════════════════════════════════════════
# 5. POST /forget — soft/hard forget (body controls the hard flag)
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/forget", response_model=None)
async def forget_claim(
    payload: PersonalMemoryForgetRequest,
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    service: PersonalMemoryService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    try:
        claim_id = uuid.UUID(payload.claim_id)
    except ValueError:
        return _envelope_error(
            "PERSONAL_MEMORY_VALIDATION_ERROR",
            f"claim_id must be a valid UUID; got {payload.claim_id!r}",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    try:
        claim = await service.forget(
            user_id=user.id,
            workspace_id=workspace_id,
            claim_id=claim_id,
            hard=payload.hard,
        )
    except PersonalMemoryClaimNotFound as exc:
        return _envelope_error(
            "PERSONAL_MEMORY_CLAIM_NOT_FOUND",
            str(exc),
            status.HTTP_404_NOT_FOUND,
        )
    except PersonalMemoryValidationError as exc:
        return _envelope_error(
            "PERSONAL_MEMORY_VALIDATION_ERROR",
            str(exc),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    # Commit the service's flushed write (services/AGENTS.md rule 3).
    await _commit(db)
    return ok(PersonalMemoryClaimResponse.model_validate(claim).model_dump(mode="json"))


# ═══════════════════════════════════════════════════════════════════════════
# 6. GET /claims/{id}/provenance — per-claim audit summary (T32)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/claims/{claim_id}/provenance")
async def claim_provenance(
    claim_id: uuid.UUID,
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return the audit-trail summary for a single claim.

    Thin envelope-wrapping layer over
    ``MemoryCorrectionService.get_provenance()`` (D30-60, T29 service).
    The service does the heavy lifting (workspace-isolated event fetch
    + stable ``events_by_type`` bucket map); the route just unwraps
    the dataclass into a Pydantic response.

    Privacy guardrail: cross-tenant claims return
    ``event_count: 0, *_at: None`` (NOT 404) so a malicious user can't
    probe whether a claim exists in a different workspace. This mirrors
    the design of ``PersonalMemoryService.list_for_user`` for the same
    reason.
    """
    service = MemoryCorrectionService(db)
    summary = await service.get_provenance(
        user_id=user.id,
        workspace_id=workspace_id,
        claim_id=claim_id,
    )
    # The service already returns the canonical shape; wrap it in the
    # Pydantic response for OpenAPI documentation + validation.
    payload = PersonalMemoryProvenanceResponse.model_validate(summary)
    return ok(payload.model_dump(mode="json"))


# ═══════════════════════════════════════════════════════════════════════════
# 7. GET /corrections — durable memory-correction audit trail (GOV-1.6)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/corrections")
async def list_corrections(
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    event_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return the durable ``memory_correction_events`` audit trail.

    GOV-1.6 closes the feedback loop read-side: the write path has been
    wired since GOV-1.4 (``PersonalMemoryService._safe_audit`` →
    ``MemoryCorrectionService``) but nothing ever surfaced it to the
    Inspector. This endpoint exposes the same privacy trail that every
    memory op / approval decision / dropped candidate writes to, so the
    corrections are finally readable — satisfying the C3 "corrections are
    wired, not just written" acceptance criterion.

    ``drop`` events (GOV-1.6 / C5) are dropped extraction candidates:
    ``claim_id`` is ``None`` and the candidate shape (claim_type / scope /
    confidence) lives in ``details``. Filter with ``?event_type=drop`` to
    see only calibration drops.

    Always scoped to ``(user_id, workspace_id)`` (the workspace isolation
    guardrail). A bad ``event_type`` surfaces as a 422 (raised by the
    service).
    """
    service = MemoryCorrectionService(db)
    items, total = await service.list_for_user(
        user_id=user.id,
        workspace_id=workspace_id,
        event_type=event_type,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return ok(
        PersonalMemoryCorrectionListResponse(
            items=[PersonalMemoryCorrectionResponse.model_validate(ev) for ev in items],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        ).model_dump(mode="json")
    )
