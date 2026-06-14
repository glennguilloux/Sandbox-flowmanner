"""FastAPI DI for program CQRS handler classes.

Mirrors ``_mission_cqrs/deps.py``.  ``get_program_commands`` injects a
``ProgramAudit`` (structlog-backed) and the ``X-Request-ID`` from the
request headers, so every audit event carries the request trace id
without the handler needing to know about FastAPI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, Request

from app.database import get_db_session

from .audit import ProgramAudit
from .commands import ProgramCommandHandlers
from .queries import ProgramQueryHandlers

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def get_program_queries(
    session: AsyncSession = Depends(get_db_session),
) -> ProgramQueryHandlers:
    return ProgramQueryHandlers(session)


def get_program_commands(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ProgramCommandHandlers:
    request_id = request.headers.get("X-Request-ID")
    return ProgramCommandHandlers(
        session, audit=ProgramAudit(session), request_id=request_id
    )
