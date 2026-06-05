"""Shared v2-style standardized response envelope.

Import this from any route module to wrap responses consistently:

    from app.api.envelope import envelope

    return envelope({"key": "value"})
    # => {"data": {"key": "value"}, "meta": {}, "error": None}

    return envelope({"key": "value"}, meta={"page": 1})
    # => {"data": {"key": "value"}, "meta": {"page": 1}, "error": None}
"""

from __future__ import annotations

from typing import Any


def envelope(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrap response in v2-style standardized envelope."""
    return {"data": data, "meta": meta or {}, "error": None}
