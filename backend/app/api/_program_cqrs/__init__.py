"""Internal CQRS package for mission-program endpoints.

Mirrors ``_mission_cqrs/__init__.py`` — re-exports the public surface so
routes can do ``from app.api._program_cqrs import ProgramCommandHandlers``
without reaching into individual sub-modules.
"""

from .audit import ProgramAudit
from .base import CommandHandlerBase, QueryHandlerBase
from .commands import ProgramCommandHandlers
from .deps import get_program_commands, get_program_queries
from .errors import map_program_infra_error
from .queries import ProgramQueryHandlers

__all__ = [
    "CommandHandlerBase",
    "ProgramAudit",
    "ProgramCommandHandlers",
    "ProgramQueryHandlers",
    "QueryHandlerBase",
    "get_program_commands",
    "get_program_queries",
    "map_program_infra_error",
]
