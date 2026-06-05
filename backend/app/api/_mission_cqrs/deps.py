"""FastAPI DI for CQRS handler classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, Request

from app.database import get_db_session

from .audit import AuditService
from .commands import MissionCommandHandlers
from .queries import MissionQueryHandlers

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def get_mission_queries(
    session: AsyncSession = Depends(get_db_session),
) -> MissionQueryHandlers:
    return MissionQueryHandlers(session)


def get_mission_commands(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> MissionCommandHandlers:
    request_id = request.headers.get("X-Request-ID")
    return MissionCommandHandlers(session, audit=AuditService(session), request_id=request_id)
