"""Blueprint CQRS error types."""


class BlueprintError(Exception):
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
