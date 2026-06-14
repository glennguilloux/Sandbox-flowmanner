"""Program query handlers — read-only operations.

Mirrors the structure of ``_mission_cqrs/queries.py``.  Read-only —
no transactions, no audit.  Every method builds a fresh
``MissionProgramService`` against the same session so access checks,
ownership predicates, and budget reads flow through one code path.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.schemas.program import (
    LearningBriefBase,
    ProgramResponse,
    ProgramRunResponse,
)
from app.services.mission_program_service import MissionProgramService

from .base import QueryHandlerBase

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


class ProgramQueryHandlers(QueryHandlerBase):
    def _build_service(self) -> MissionProgramService:
        # Queries don't need the audit hook; service tolerates a None audit
        # by falling back to a no-op.
        return MissionProgramService(self.session, audit=None)

    # ── List ─────────────────────────────────────────────────────────────────

    async def list_programs(
        self,
        user_id: int,
        workspace_id: str | None,
        page: int,
        per_page: int,
    ) -> tuple[list[ProgramResponse], int]:
        """List programs the user can see, optionally filtered by workspace."""
        service = self._build_service()
        items, total = await service.list(
            user_id=user_id,
            workspace_id=workspace_id,
            page=page,
            per_page=per_page,
        )
        return [ProgramResponse.model_validate(p) for p in items], total

    # ── Get ──────────────────────────────────────────────────────────────────

    async def get_program(
        self,
        user: User,
        program_id: uuid.UUID,
    ) -> ProgramResponse:
        """Fetch a single program; raises ``ProgramNotFound`` /
        ``ProgramForbidden`` from the service."""
        service = self._build_service()
        program = await service.get(user.id, program_id)
        return ProgramResponse.model_validate(program)

    # ── Runs ─────────────────────────────────────────────────────────────────

    async def list_runs(
        self,
        program_id: uuid.UUID,
        page: int,
        per_page: int,
    ) -> tuple[list[ProgramRunResponse], int]:
        """List program runs (newest first)."""
        service = self._build_service()
        items, total = await service.list_runs(
            program_id=program_id, page=page, per_page=per_page
        )
        return [ProgramRunResponse.model_validate(r) for r in items], total

    # ── Learning brief ───────────────────────────────────────────────────────

    async def get_learning_brief(
        self,
        program_id: uuid.UUID,
    ) -> LearningBriefBase | None:
        """Return the program's learning brief (raw JSONB), validated
        against ``LearningBriefBase`` when present."""
        service = self._build_service()
        raw = await service.get_learning_brief(program_id)
        if raw is None:
            return None
        return LearningBriefBase.model_validate(raw)


__all__ = ["ProgramQueryHandlers"]
