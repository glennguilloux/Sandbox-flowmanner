"""Blueprint CQRS error types."""

from app.core.exceptions import AppError


class BlueprintError(AppError):
    """Base error for blueprint operations.

    Subclasses ``AppError`` so these surface through the unified FastAPI
    exception handler as a typed 4xx envelope (code + http_status) instead of
    falling through to the generic 500 handler.
    """

    code = "BLUEPRINT_ERROR"
    http_status = 400


class BlueprintNotFoundError(BlueprintError):
    """Blueprint not found or access denied."""

    code = "BLUEPRINT_NOT_FOUND"
    http_status = 404


class RunNotFoundError(BlueprintError):
    """Run not found or access denied."""

    code = "RUN_NOT_FOUND"
    http_status = 404


class BlueprintValidationError(BlueprintError):
    """Invalid blueprint operation (e.g. malformed graph, bad status transition)."""

    code = "BLUEPRINT_VALIDATION_ERROR"
    http_status = 400


class RunValidationError(BlueprintError):
    """Invalid run operation."""

    code = "RUN_VALIDATION_ERROR"
    http_status = 400
