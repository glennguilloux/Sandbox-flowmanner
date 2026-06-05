"""Mission error hierarchy — used by mission_executor and its sub-services."""


class MissionError(Exception):
    """Base for all mission errors."""
    pass


class RetryableMissionError(MissionError):
    """Transient error — retry may fix it (timeout, rate limit, 5xx)."""
    pass


class PermanentMissionError(MissionError):
    """Bad input or state — must be fixed by user (401, 403, 404, bad config)."""
    pass


# ── API-layer exceptions ──────────────────────────────────────────────────────

class MissionNotFoundError(MissionError):
    """Mission not found — maps to HTTP 404."""
    pass


class MissionTransitionConflictError(MissionError):
    """Invalid status transition — maps to HTTP 409."""
    pass


class MissionForbiddenError(MissionError):
    """User does not own or have access to mission — maps to HTTP 403."""
    pass


class MissionValidationError(MissionError):
    """Bad request / validation failure — maps to HTTP 400."""
    pass


class GraphNotFoundError(MissionError):
    """Graph workflow not found or access denied — maps to HTTP 404."""
    pass
