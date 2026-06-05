"""Infrastructure-to-domain error mapping for mission CQRS handlers."""

from sqlalchemy.exc import DBAPIError, IntegrityError

from app.services.mission_errors import (
    MissionError,
    MissionValidationError,
    PermanentMissionError,
    RetryableMissionError,
)


def map_infra_error(exc: Exception) -> MissionError:
    if isinstance(exc, IntegrityError):
        return MissionValidationError("Database constraint violation")
    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return RetryableMissionError("Transient database connectivity error")
    return PermanentMissionError("Unhandled infrastructure failure")
