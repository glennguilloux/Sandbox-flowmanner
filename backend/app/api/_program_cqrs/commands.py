"""Program command handlers — mutation operations with explicit transactions.

Mirrors the structure of ``_mission_cqrs/commands.py``.  All single-commit
mutations go through ``wrap_command()`` so the unit-of-work is bounded
to a single ``commit()`` / ``rollback()``.

The ``fire_program`` and ``consolidate`` command paths are explicitly
guarded against ``NotImplementedError`` from the T5 service stubs; they
re-raise the stub failure as a ``ProgramError`` so the HTTP layer maps
it to a 501 (not yet implemented) — this keeps the public surface
stable while T8 / T9 land.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.schemas.program import (
    ConsolidateResponse,
    ProgramCreate,
    ProgramResponse,
    ProgramRunResponse,
    ProgramUpdate,
)
from app.services.mission_program_service import (
    MissionProgramService,
    ProgramError,
)

from .base import CommandHandlerBase
from .errors import map_program_infra_error

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

    from .audit import ProgramAudit


class ProgramCommandHandlers(CommandHandlerBase):
    def __init__(
        self,
        session: AsyncSession,
        audit: ProgramAudit | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(session)
        self.audit = audit
        self._request_id = request_id

    def _build_service(self) -> MissionProgramService:
        return MissionProgramService(self.session, audit=self.audit)

    # ── Create ───────────────────────────────────────────────────────────────

    async def create_program(
        self,
        user: User,
        workspace_id: str,
        payload: ProgramCreate,
    ) -> ProgramResponse:
        service = self._build_service()
        program = await service.create(user.id, workspace_id, payload)
        return ProgramResponse.model_validate(program)

    # ── Update ───────────────────────────────────────────────────────────────

    async def update_program(
        self,
        user: User,
        program_id: uuid.UUID,
        patch: ProgramUpdate,
    ) -> ProgramResponse:
        service = self._build_service()
        program = await service.update(user.id, program_id, patch)
        return ProgramResponse.model_validate(program)

    # ── Delete (soft) ────────────────────────────────────────────────────────

    async def delete_program(
        self,
        user: User,
        program_id: uuid.UUID,
    ) -> None:
        """Soft-delete: set status=ARCHIVED via ``service.archive``."""
        service = self._build_service()
        await service.archive(user.id, program_id)
        return None

    # ── Fire ─────────────────────────────────────────────────────────────────

    async def fire_program(
        self,
        user: User,
        program_id: uuid.UUID,
        idempotency_key: str,
        trigger_type: str = "manual",
        trigger_payload: dict | None = None,
    ) -> ProgramRunResponse:
        """Trigger a program run.

        ``fire_program`` is implemented in T8 — the T5 stub raises
        ``NotImplementedError``.  We surface that as a ``ProgramError``
        so the HTTP layer returns 501 (stable surface area).
        """
        service = self._build_service()
        try:
            run = await service.fire_program(
                user.id,
                program_id,
                trigger_type=trigger_type,
                trigger_payload=trigger_payload,
            )
        except NotImplementedError as exc:
            # T8 will replace this stub; until then, return a domain error
            # so the route can map to 501.
            raise ProgramError(
                f"fire_program is not yet implemented (idempotency_key={idempotency_key})"
            ) from exc
        # Thread idempotency_key into the audit so duplicate fires are
        # correlated in the log stream (idempotency is enforced at the
        # HTTP layer; the audit is for traceability).
        if self.audit is not None and hasattr(self.audit, "program_fired"):
            try:
                self.audit.program_fired(
                    program_id=program_id,
                    actor_id=user.id,
                    trigger_type=trigger_type,
                    request_id=self._request_id,
                    idempotency_key=idempotency_key,
                )
            except Exception:  # pragma: no cover — audit is no-fail
                logger.debug("program_fired audit failed", exc_info=True)
        return ProgramRunResponse.model_validate(run)

    # ── Consolidate ──────────────────────────────────────────────────────────

    async def consolidate(
        self,
        user: User,
        program_id: uuid.UUID,
        idempotency_key: str,
        limit: int = 10,
    ) -> ConsolidateResponse:
        """Consolidate recent runs into the learning brief.

        ``consolidate_learning`` is implemented in T9 — the T5 stub
        raises ``NotImplementedError``.  We surface that as a
        ``ProgramError`` so the HTTP layer returns 501.
        """
        service = self._build_service()
        try:
            result = await service.consolidate_learning(
                user.id, program_id, limit=limit
            )
        except NotImplementedError as exc:
            raise ProgramError(
                f"consolidate is not yet implemented (idempotency_key={idempotency_key})"
            ) from exc
        # Audit the consolidation for traceability.
        if self.audit is not None and hasattr(self.audit, "program_consolidated"):
            try:
                self.audit.program_consolidated(
                    program_id=program_id,
                    actor_id=user.id,
                    consolidated_runs=getattr(result, "consolidated_runs", 0),
                    request_id=self._request_id,
                    idempotency_key=idempotency_key,
                )
            except Exception:  # pragma: no cover — audit is no-fail
                logger.debug("program_consolidated audit failed", exc_info=True)
        return result

    # ── User notes ───────────────────────────────────────────────────────────

    async def update_user_notes(
        self,
        user: User,
        program_id: uuid.UUID,
        notes: str,
    ) -> ProgramResponse:
        """Update ONLY the user-owned ``user_notes`` sub-key of the brief."""
        service = self._build_service()
        program = await service.update_user_notes(user.id, program_id, notes)
        return ProgramResponse.model_validate(program)


__all__ = ["ProgramCommandHandlers", "map_program_infra_error"]
