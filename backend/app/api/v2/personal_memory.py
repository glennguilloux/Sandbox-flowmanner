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
    ConflictGroupResponse,
    ConflictListResponse,
    ConflictMemberResponse,
    PersonalMemoryClaimResponse,
    PersonalMemoryClaimUpdate,
    PersonalMemoryCorrectionListResponse,
    PersonalMemoryCorrectionResponse,
    PersonalMemoryForgetRequest,
    PersonalMemoryProvenanceInfo,
    PersonalMemoryProvenanceResponse,
    PersonalMemoryProvenanceTraceResponse,
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
# 6. GET /claims/{id}/provenance — full provenance trace (Epic 3.6)
#    "Why does the agent believe X?" — the claim + its origin provenance +
#    the durable correction/audit trail (and the T32 roll-up summary).
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/claims/{claim_id}/provenance", response_model=None)
async def claim_provenance(
    claim_id: uuid.UUID,
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    service: PersonalMemoryService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    """Return the full provenance trace for a single claim (Epic 3.6).

    Answers "Why does the agent believe X?" by composing three data
    sources that already exist — this is pure exposure work, no new
    persistence:

    * ``claim`` — the ``PersonalMemoryClaim`` itself.
    * ``provenance`` — origin projection (source_type, source_id, the
      mission-specific ``source_mission_id`` convenience alias, created_at,
      confidence, importance, scope).
    * ``corrections`` — the durable ``memory_correction_events`` audit
      trail scoped to this claim (most-recent-first).
    * ``audit_summary`` — the T32 aggregate roll-up (event counts by type,
      first/last event) preserved so nothing regresses.

    Scope guardrail: every read is filtered by ``(user_id, workspace_id)``.
    A claim that isn't visible to the caller (cross-tenant, wrong user)
    surfaces as a 404 envelope — never a cross-tenant leak, and the
    correction/summary reads are only performed once the claim is proven
    visible.
    """
    # 1. Fetch the claim first — this is the workspace-isolation gate.
    #    service.get() filters by (id, user_id, workspace_id) and raises
    #    PersonalMemoryClaimNotFound for anything the caller can't see.
    try:
        claim = await service.get(
            user_id=user.id,
            workspace_id=workspace_id,
            claim_id=claim_id,
        )
    except PersonalMemoryClaimNotFound as exc:
        return _envelope_error(
            "PERSONAL_MEMORY_CLAIM_NOT_FOUND",
            str(exc),
            status.HTTP_404_NOT_FOUND,
        )

    # 2. Correction trail + T32 roll-up summary — both scoped to
    #    (user_id, workspace_id, claim_id) by the correction service.
    correction_service = MemoryCorrectionService(db)
    corrections = await correction_service.list_for_claim(
        user_id=user.id,
        workspace_id=workspace_id,
        claim_id=claim_id,
    )
    summary = await correction_service.get_provenance(
        user_id=user.id,
        workspace_id=workspace_id,
        claim_id=claim_id,
    )

    # 3. Origin provenance projection. ``source_mission_id`` is a
    #    convenience alias: the claim model stores a generic ``source_id``
    #    whose meaning is set by ``source_type``, so we only surface it as
    #    a mission id when the source actually is a mission.
    source_mission_id = claim.source_id if claim.source_type == "mission" else None
    provenance = PersonalMemoryProvenanceInfo(
        source_type=claim.source_type,
        source_id=uuid.UUID(claim.source_id) if claim.source_id else None,
        source_mission_id=uuid.UUID(source_mission_id) if source_mission_id else None,
        created_at=claim.created_at,
        confidence=claim.confidence,
        importance=claim.importance,
        scope=claim.scope,
    )

    payload = PersonalMemoryProvenanceTraceResponse(
        claim=PersonalMemoryClaimResponse.model_validate(claim),
        provenance=provenance,
        corrections=[PersonalMemoryCorrectionResponse.model_validate(ev) for ev in corrections],
        audit_summary=PersonalMemoryProvenanceResponse.model_validate(summary),
    )
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
        ).model_dump(mode="json"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. GET /conflicts — Epic 2.3 E23-C conflict surfacing (read-only)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/conflicts")
async def list_conflicts(
    workspace_id: str = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    scope: str | None = Query(default=None),
) -> dict[str, Any]:
    """Surface conflicting live claims for the Memory Inspector.

    Returns only groups of claims that conflict on the same ``(subject,
    predicate)`` with a differing ``object``. Each group carries the
    deterministic winner (claim-type precedence > source priority > recency >
    confidence) plus the losers with an explainable ``superseded_because``.

    **Never deletes or merges** — surfacing only (per the 2.3 policy). Always
    scoped to ``(user_id, workspace_id)``.
    """
    from app.services.memory_conflict_service import list_conflicts as _list_conflicts

    groups = await _list_conflicts(
        db=db,
        user_id=user.id,
        workspace_id=workspace_id,
        scope=scope,
    )
    items = [
        ConflictGroupResponse(
            subject=g.subject,
            predicate=g.predicate,
            winner=PersonalMemoryClaimResponse.model_validate(g.winner),
            losers=[
                ConflictMemberResponse(
                    claim=PersonalMemoryClaimResponse.model_validate(m.claim),
                    rank=m.rank,
                    superseded_because=m.superseded_because,
                )
                for m in g.members[1:]
            ],
        )
        for g in groups
    ]
    return ok(ConflictListResponse(items=items, total=len(items)).model_dump(mode="json"))
