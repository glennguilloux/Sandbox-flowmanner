"""Blueprint query handlers — read-only operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.schemas.blueprint import (
    BlueprintResponse,
    BlueprintVersionResponse,
    RunEventResponse,
    RunResponse,
)
from app.services.blueprint_service import BlueprintService
from app.services.run_service import RunService

from .base import QueryHandlerBase

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PaginatedBlueprints:
    items: list[BlueprintResponse]
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        n = self.per_page or 1
        return (self.total + n - 1) // n


@dataclass(slots=True)
class PaginatedRuns:
    items: list[RunResponse]
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        n = self.per_page or 1
        return (self.total + n - 1) // n


class BlueprintQueryHandlers(QueryHandlerBase):
    async def list_blueprints(
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        workspace_id: str | None = None,
        blueprint_type: str | None = None,
        status: str | None = None,
    ) -> PaginatedBlueprints:
        svc = BlueprintService(self.session)
        items, total = await svc.list(
            user_id,
            page=page,
            per_page=per_page,
            workspace_id=workspace_id,
            blueprint_type=blueprint_type,
            status=status,
        )
        return PaginatedBlueprints(
            items=[BlueprintResponse.model_validate(b) for b in items],
            total=total,
            page=page,
            per_page=per_page,
        )

    async def get_blueprint(self, user_id: int, blueprint_id: str) -> BlueprintResponse:
        svc = BlueprintService(self.session)
        bp = await svc.get(blueprint_id, user_id)
        return BlueprintResponse.model_validate(bp)

    async def list_versions(
        self, user_id: int, blueprint_id: str
    ) -> list[BlueprintVersionResponse]:
        svc = BlueprintService(self.session)
        versions = await svc.get_versions(blueprint_id, user_id)
        return [BlueprintVersionResponse.model_validate(v) for v in versions]  # type: ignore[attr-defined]


class RunQueryHandlers(QueryHandlerBase):
    async def list_runs(
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        workspace_id: str | None = None,
        blueprint_id: str | None = None,
        status: str | None = None,
    ) -> PaginatedRuns:
        svc = RunService(self.session)
        items, total = await svc.list(
            user_id,
            page=page,
            per_page=per_page,
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            status=status,
        )
        return PaginatedRuns(
            items=[RunResponse.model_validate(r) for r in items],
            total=total,
            page=page,
            per_page=per_page,
        )

    async def get_run(self, user_id: int, run_id: str) -> RunResponse:
        svc = RunService(self.session)
        run = await svc.get(run_id, user_id)
        return RunResponse.model_validate(run)

    async def get_events(
        self, user_id: int, run_id: str, from_sequence: int = 0, limit: int = 1000
    ) -> list[RunEventResponse]:
        svc = RunService(self.session)
        events = await svc.get_events(
            run_id, user_id, from_sequence=from_sequence, limit=limit
        )
        return [RunEventResponse.model_validate(e) for e in events]  # type: ignore[attr-defined]

    async def replay_state(
        self,
        user_id: int,
        run_id: str,
        at_sequence: int | None = None,
    ) -> dict:
        svc = RunService(self.session)
        return await svc.replay_state(run_id, user_id, at_sequence=at_sequence)

    async def get_assertions(self, user_id: int, run_id: str) -> dict:
        """Auto-generate and evaluate assertions for a completed run."""
        svc = RunService(self.session)
        return await svc.get_assertions(run_id, user_id)

    async def diff_runs(self, user_id: int, run_a_id: str, run_b_id: str) -> dict:
        svc = RunService(self.session)
        return await svc.diff_runs(run_a_id, run_b_id, user_id)
