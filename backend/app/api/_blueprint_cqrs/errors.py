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
    """Base error for blueprint operations."""

    pass


class BlueprintNotFoundError(BlueprintError):
    """Blueprint not found or access denied."""

    pass


class RunNotFoundError(BlueprintError):
    """Run not found or access denied."""

    pass


class BlueprintValidationError(BlueprintError):
    """Invalid blueprint operation."""

    pass


class RunValidationError(BlueprintError):
    """Invalid run operation."""

    pass
