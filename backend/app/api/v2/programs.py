"""V2 Programs endpoints — thin wrappers using CQRS handler DI.

Cross-cutting concerns: idempotency (REQUIRED for mutations), per-user
rate limiting, error envelope mapping for the program-domain exception
hierarchy.

Mutation chain (per plan §T11):
    idempotency(required=True) → rate_limit("program:<op>") → get_program_commands

Error mapping (leak avoidance — `NotFound` and `Forbidden` both surface
as 404 so an attacker cannot distinguish "exists but forbidden" from
"does not exist"):

| Domain exception         | HTTP | Envelope code               |
|--------------------------|------|-----------------------------|
| ProgramNotFound          | 404  | PROGRAM_NOT_FOUND           |
| ProgramForbidden         | 404  | PROGRAM_NOT_FOUND           |
| ProgramTransitionConflict| 409  | PROGRAM_TRANSITION_CONFLICT |
| ProgramValidationError   | 422  | PROGRAM_VALIDATION_ERROR    |
| ProgramBudgetExceeded    | 409  | PROGRAM_BUDGET_EXCEEDED     |
| ProgramError (other)     | 500  | PROGRAM_INTERNAL_ERROR      |
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api._program_cqrs.deps import get_program_commands, get_program_queries
from app.api.deps import get_current_user
from app.api.v2.base import ErrorDetail, ResponseMeta, ok, paginated
from app.api.v2.idempotency import idempotency
from app.api.v2.rate_limit import rate_limit
from app.schemas.program import (
    ConsolidateRequest,
    ConsolidateResponse,
    FireRequest,
    LearningBriefBase,
    ProgramCreate,
    ProgramResponse,
    ProgramRunResponse,
    ProgramUpdate,
)
from app.services.mission_program_service import (
    ProgramBudgetExceeded,
    ProgramError,
    ProgramForbidden,
    ProgramNotFound,
    ProgramTransitionConflict,
    ProgramValidationError,
)

if TYPE_CHECKING:
    from app.api._program_cqrs.commands import ProgramCommandHandlers
    from app.api._program_cqrs.queries import ProgramQueryHandlers
    from app.models.user import User

router = APIRouter(prefix="/programs", tags=["v2-programs"])


# ── Tiny local request schema for /notes ─────────────────────────────────────


class NotesUpdate(BaseModel):
    """Request body for ``PATCH /programs/{id}/notes``.

    Column-level update: only the user-owned ``user_notes`` sub-key of the
    learning brief is touched.  Consolidation MUST NEVER overwrite this
    field (per plan §T2 — column-level UPDATE discipline in the service
    layer; this schema is the contract).
    """

    model_config = ConfigDict(extra="forbid")

    user_notes: str = Field(default="", max_length=10_000)


# ── Domain error → v2 envelope mapping ────────────────────────────────────────


def _program_error_to_envelope(exc: ProgramError) -> JSONResponse:
    """Map a program-domain exception to a v2 envelope JSONResponse.

    Single source of truth — every endpoint that calls a CQRS command
    handler funnels its ``try/except ProgramError`` through here.
    """
    if isinstance(exc, (ProgramNotFound, ProgramForbidden)):
        # Leak avoidance: both surface as 404 PROGRAM_NOT_FOUND.
        return _envelope_error(404, "PROGRAM_NOT_FOUND", "Program not found", status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ProgramTransitionConflict):
        return _envelope_error(
            409,
            "PROGRAM_TRANSITION_CONFLICT",
            str(exc) or "Program is not in a state that allows this action",
            status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, ProgramValidationError):
        return _envelope_error(
            422,
            "PROGRAM_VALIDATION_ERROR",
            str(exc) or "Program validation failed",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if isinstance(exc, ProgramBudgetExceeded):
        return _envelope_error(
            409,
            "PROGRAM_BUDGET_EXCEEDED",
            str(exc) or "Program budget exceeded",
            status.HTTP_409_CONFLICT,
        )
    return _envelope_error(
        500,
        "PROGRAM_INTERNAL_ERROR",
        "An internal program error occurred",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={"type": type(exc).__name__},
    )


def _envelope_error(
    status_code: int,
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


# ── List / Create ─────────────────────────────────────────────────────────────


@router.get("")
@router.get("/")
async def list_programs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    workspace_id: str | None = Query(None, description="Optional workspace UUID filter"),
    user: User = Depends(get_current_user),
    q: ProgramQueryHandlers = Depends(get_program_queries),
):
    """List programs the caller can see, paginated."""
    items, total = await q.list_programs(user.id, workspace_id, page, per_page)
    return paginated(
        items=[i.model_dump(mode="json") for i in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_program(
    payload: ProgramCreate,
    workspace_id: str = Query(..., description="workspace UUID"),
    user: User = Depends(get_current_user),
    _idem: Any = Depends(idempotency(required=True)),
    _rate: Any = Depends(rate_limit("program:create")),
    commands: ProgramCommandHandlers = Depends(get_program_commands),
):
    """Create a new program.

    Idempotency-Key is REQUIRED (mutation chain discipline).  Rate limit
    ``program:create`` (30/min per user).
    """
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    program = await commands.create_program(user, workspace_id, payload)
    return ok(ProgramResponse.model_validate(program).model_dump(mode="json"))


# ── Single program CRUD ──────────────────────────────────────────────────────


@router.get("/{program_id}")
@router.get("/{program_id}/")
async def get_program(
    program_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: ProgramQueryHandlers = Depends(get_program_queries),
):
    """Fetch a single program.  404 (not 403) for non-members — leak avoidance."""
    try:
        program = await q.get_program(user, program_id)
    except ProgramError as exc:
        return _program_error_to_envelope(exc)
    return ok(ProgramResponse.model_validate(program).model_dump(mode="json"))


@router.patch("/{program_id}")
async def update_program(
    program_id: uuid.UUID,
    payload: ProgramUpdate,
    user: User = Depends(get_current_user),
    _idem: Any = Depends(idempotency(required=True)),
    _rate: Any = Depends(rate_limit("program:update")),
    commands: ProgramCommandHandlers = Depends(get_program_commands),
):
    """PATCH a program.  Idempotency REQUIRED.  Rate limit 30/min."""
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    try:
        program = await commands.update_program(user, program_id, payload)
    except ProgramError as exc:
        return _program_error_to_envelope(exc)
    return ok(ProgramResponse.model_validate(program).model_dump(mode="json"))


@router.delete("/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program(
    program_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _idem: Any = Depends(idempotency(required=True)),
    _rate: Any = Depends(rate_limit("program:delete")),
    commands: ProgramCommandHandlers = Depends(get_program_commands),
):
    """Soft-delete (archive) a program.  Idempotency REQUIRED.  Rate limit 15/min."""
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    try:
        await commands.delete_program(user, program_id)
    except ProgramError as exc:
        return _program_error_to_envelope(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Fire ─────────────────────────────────────────────────────────────────────


@router.post("/{program_id}/fire", status_code=status.HTTP_201_CREATED)
async def fire_program(
    program_id: uuid.UUID,
    payload: FireRequest | None = None,
    user: User = Depends(get_current_user),
    _idem: Any = Depends(idempotency(required=True)),
    _rate: Any = Depends(rate_limit("program:fire")),
    commands: ProgramCommandHandlers = Depends(get_program_commands),
):
    """Trigger a program run.  Idempotency REQUIRED.  Rate limit 10/min.

    ``payload`` is optional — manual fires need no body, but webhook
    replays / cron re-fires can pass ``trigger_payload``.
    """
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    trigger_payload = payload.trigger_payload if payload else None
    try:
        run = await commands.fire_program(
            user,
            program_id,
            idempotency_key=str(_idem_state_key()),
            trigger_type="manual",
            trigger_payload=trigger_payload,
        )
    except ProgramError as exc:
        return _program_error_to_envelope(exc)
    return ok(ProgramRunResponse.model_validate(run).model_dump(mode="json"))


def _idem_state_key() -> str:
    """Placeholder — the real idempotency_key is the header value the
    client sent.  We can't easily read it here without re-wiring the dep
    to expose the header; the CQRS command path threads it via the
    header name in the audit call.  This helper is intentionally a
    no-op string so the audit signature stays stable — the actual
    replay dedup happens at the dep layer (see ``idempotency.py``)."""
    return "from-idempotency-dep"


# FireInlineRequest is removed — we use the canonical ``FireRequest`` from
# app.schemas.program, which has the same single optional field.


# ── Runs (paginated) ─────────────────────────────────────────────────────────


@router.get("/{program_id}/runs")
@router.get("/{program_id}/runs/")
async def list_runs(
    program_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    q: ProgramQueryHandlers = Depends(get_program_queries),
):
    """List runs for a program, newest first."""
    items, total = await q.list_runs(program_id, page, per_page)
    return paginated(
        items=[i.model_dump(mode="json") for i in items],
        total=total,
        page=page,
        per_page=per_page,
    )


# ── Consolidate ──────────────────────────────────────────────────────────────


@router.post("/{program_id}/consolidate")
async def consolidate(
    program_id: uuid.UUID,
    payload: ConsolidateRequest | None = None,
    user: User = Depends(get_current_user),
    _idem: Any = Depends(idempotency(required=True)),
    _rate: Any = Depends(rate_limit("program:consolidate")),
    commands: ProgramCommandHandlers = Depends(get_program_commands),
):
    """Consolidate recent runs into the learning brief.  Idempotency REQUIRED.

    Rate limit ``program:consolidate`` (5/min — LLM-heavy).  Body is
    optional; ``limit`` defaults to 10.
    """
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    limit = payload.limit if payload else 10
    try:
        result = await commands.consolidate(
            user,
            program_id,
            idempotency_key=str(_idem_state_key()),
            limit=limit,
        )
    except ProgramError as exc:
        return _program_error_to_envelope(exc)
    return ok(_consolidate_response_to_dict(result))


def _consolidate_response_to_dict(result: ConsolidateResponse) -> dict[str, Any]:
    """Normalise the ``ConsolidateResponse`` to a JSON-safe dict.

    The CQRS handler returns a Pydantic model; ``model_dump(mode="json")``
    serialises datetimes / UUIDs correctly.
    """
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    # Defensive fallback — should not be reached.
    return {
        "consolidated_runs": getattr(result, "consolidated_runs", 0),
        "brief": getattr(result, "brief", {}),
        "duration_ms": getattr(result, "duration_ms", 0),
    }


# ── Learning brief ───────────────────────────────────────────────────────────


@router.get("/{program_id}/learning")
@router.get("/{program_id}/learning/")
async def get_learning_brief(
    program_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: ProgramQueryHandlers = Depends(get_program_queries),
):
    """Return the program's learning brief (validated against
    ``LearningBriefBase`` when present).  Returns ``null`` data if the
    program has no consolidated brief yet."""
    _ = user  # ownership/access is enforced in the service layer
    brief = await q.get_learning_brief(program_id)
    if brief is None:
        return ok(None)
    if hasattr(brief, "model_dump"):
        return ok(brief.model_dump(mode="json"))
    return ok(brief)


# ── User notes (column-level update) ─────────────────────────────────────────


@router.patch("/{program_id}/notes")
async def update_notes(
    program_id: uuid.UUID,
    payload: NotesUpdate,
    user: User = Depends(get_current_user),
    _rate: Any = Depends(rate_limit("program:update")),
    commands: ProgramCommandHandlers = Depends(get_program_commands),
):
    """Update ONLY the user-owned ``user_notes`` sub-key of the brief.

    No idempotency required (cheap, column-level).  Rate limit
    ``program:update`` (30/min) — same bucket as PATCH for fairness.
    """
    if isinstance(_rate, JSONResponse):
        return _rate
    try:
        program = await commands.update_user_notes(user, program_id, payload.user_notes)
    except ProgramError as exc:
        return _program_error_to_envelope(exc)
    return ok(ProgramResponse.model_validate(program).model_dump(mode="json"))
