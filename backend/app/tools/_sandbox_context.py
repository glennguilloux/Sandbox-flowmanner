"""Sandbox context — thread/task-local storage for the current mission's sandbox_id.

The mission executor sets this before executing tasks so that sandboxd
tools can resolve which sandbox to target without circular imports.
"""

from __future__ import annotations

from contextvars import ContextVar

_current_sandbox_id: ContextVar[str | None] = ContextVar(
    "current_sandbox_id", default=None
)


def set_current_sandbox_id(sandbox_id: str | None) -> None:
    """Set the current sandbox_id for this async task."""
    _current_sandbox_id.set(sandbox_id)


def get_current_sandbox_id() -> str | None:
    """Get the current sandbox_id for this async task."""
    return _current_sandbox_id.get()
