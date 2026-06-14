"""Infrastructure-to-domain error mapping for program CQRS handlers.

Mirrors ``_mission_cqrs/errors.py``.  Translates SQLAlchemy low-level
exceptions into the program-domain error hierarchy defined in
``app.services.mission_program_service``.
"""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError, IntegrityError

from app.services.mission_program_service import (
    ProgramError,
    ProgramValidationError,
)


def map_program_infra_error(exc: Exception) -> ProgramError:
    """Map a low-level infrastructure error to a program-domain error."""
    if isinstance(exc, IntegrityError):
        return ProgramValidationError("Database constraint violation")
    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return ProgramError("Transient database connectivity error")
    return ProgramError(f"Unhandled infrastructure failure: {exc!s}")
