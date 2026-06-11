"""Blueprint command handlers — mutation operations with explicit transactions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.blueprint_service import BlueprintService
from app.services.run_service import RunService

from .base import CommandHandlerBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User
    from app.schemas.blueprint import BlueprintCreate, BlueprintUpdate, RunCreate

logger = logging.getLogger(__name__)


class BlueprintCommandHandlers(CommandHandlerBase):
    def __init__(self, session: AsyncSession, request_id: str | None = None) -> None:
        super().__init__(session)
        self._request_id = request_id

    async def create_blueprint(self, user: User, payload: BlueprintCreate, workspace_id: str | None = None):
        svc = BlueprintService(self.session)

        async def _op():
            definition = None
            if payload.definition is not None:
                definition = payload.definition.model_dump()
            return await svc.create(
                user_id=user.id,
                title=payload.title,
                description=payload.description or "",
                blueprint_type=payload.blueprint_type,
                definition=definition,
                input_schema=payload.input_schema,
                output_schema=payload.output_schema,
                tags=payload.tags,
                category=payload.category,
                icon=payload.icon,
                workspace_id=workspace_id,
            )

        return await self.wrap_command(_op)

    async def update_blueprint(self, user: User, blueprint_id: str, payload: BlueprintUpdate):
        svc = BlueprintService(self.session)

        async def _op():
            kwargs = {}
            if payload.title is not None:
                kwargs["title"] = payload.title
            if payload.description is not None:
                kwargs["description"] = payload.description
            if payload.definition is not None:
                kwargs["definition"] = payload.definition.model_dump()
            if payload.status is not None:
                kwargs["status"] = payload.status
            if payload.input_schema is not None:
                kwargs["input_schema"] = payload.input_schema
            if payload.output_schema is not None:
                kwargs["output_schema"] = payload.output_schema
            if payload.tags is not None:
                kwargs["tags"] = payload.tags
            if payload.category is not None:
                kwargs["category"] = payload.category
            if payload.icon is not None:
                kwargs["icon"] = payload.icon
            return await svc.update(blueprint_id, user.id, **kwargs)

        return await self.wrap_command(_op)

    async def delete_blueprint(self, user: User, blueprint_id: str):
        svc = BlueprintService(self.session)

        async def _op():
            return await svc.delete(blueprint_id, user.id)

        return await self.wrap_command(_op)

    async def publish_blueprint(self, user: User, blueprint_id: str):
        svc = BlueprintService(self.session)

        async def _op():
            return await svc.publish(blueprint_id, user.id)

        return await self.wrap_command(_op)

    async def run_blueprint(self, user: User, blueprint_id: str, payload: RunCreate | None = None):
        svc = RunService(self.session)

        async def _op():
            budget_override = None
            if payload and payload.budget_override:
                budget_override = payload.budget_override.model_dump()
            run = await svc.create_from_blueprint(
                blueprint_id=blueprint_id,
                user_id=user.id,
                input_data=payload.input_data if payload else None,
                budget_override=budget_override,
            )
            # Execute immediately
            return await svc.execute(str(run.id), user.id)

        return await self.wrap_command(_op)


class RunCommandHandlers(CommandHandlerBase):
    def __init__(self, session: AsyncSession, request_id: str | None = None) -> None:
        super().__init__(session)
        self._request_id = request_id

    async def abort_run(self, user: User, run_id: str, reason: str = "user_requested"):
        svc = RunService(self.session)

        async def _op():
            return await svc.abort(run_id, user.id, reason)

        return await self.wrap_command(_op)

    async def retry_run(self, user: User, run_id: str):
        svc = RunService(self.session)

        async def _op():
            new_run = await svc.retry(run_id, user.id)
            # Auto-execute the retry
            return await svc.execute(str(new_run.id), user.id)

        return await self.wrap_command(_op)
