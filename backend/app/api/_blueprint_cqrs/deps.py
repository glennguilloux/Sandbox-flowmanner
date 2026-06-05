"""Blueprint CQRS dependency injection for FastAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, Request

from app.database import get_db_session

from .commands import BlueprintCommandHandlers, RunCommandHandlers
from .queries import BlueprintQueryHandlers, RunQueryHandlers

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def get_blueprint_queries(
    session: AsyncSession = Depends(get_db_session),
) -> BlueprintQueryHandlers:
    return BlueprintQueryHandlers(session)


def get_blueprint_commands(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> BlueprintCommandHandlers:
    request_id = request.headers.get("X-Request-ID")
    return BlueprintCommandHandlers(session, request_id=request_id)


def get_run_queries(
    session: AsyncSession = Depends(get_db_session),
) -> RunQueryHandlers:
    return RunQueryHandlers(session)


def get_run_commands(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> RunCommandHandlers:
    request_id = request.headers.get("X-Request-ID")
    return RunCommandHandlers(session, request_id=request_id)
