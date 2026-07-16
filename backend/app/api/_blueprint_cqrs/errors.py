"""Blueprint CQRS error types.

``BlueprintError`` subclasses ``AppError`` so these domain errors are
surfaced through the unified ``AppError`` handler in
``main_fastapi.py`` as a proper 4xx envelope (default 400) with the
real exception message — NOT a 500 with a generic body. Previously
they were plain ``Exception`` subclasses and hit the catch-all
``Exception`` handler, masking blueprint/run validation failures as
internal server errors.
"""

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
