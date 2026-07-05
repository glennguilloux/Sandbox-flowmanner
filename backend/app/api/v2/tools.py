"""V2 Tool discovery — returns the tool list the calling user/workspace is authorized to invoke."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.api.v2.base import ok
from app.tools.base import get_tool_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["v2-tools"])


def _user_has_scopes(user: Any, required_scopes: list[str]) -> bool:
    """Check if the user has all required scopes.

    Uses the same semantics as ``require_scope`` from app.api.deps but
    operates on the user object already resolved by ``get_current_user``
    (JWT path, v2 contract).

    Scope resolution:
    - Superusers (``is_superuser``) pass all scope checks.
    - Otherwise, check ``user.scopes`` (list[str]) or ``user.role`` for
      a mapping that covers the required set.
    - If the user object has no scope information, deny by default.
    """
    if not required_scopes:
        return True

    # Superuser bypass
    if getattr(user, "is_superuser", False):
        return True

    # Check user.scopes attribute (set by JWT claims or session)
    user_scopes = set(getattr(user, "scopes", []) or [])

    # Also include role-derived scopes for common admin roles
    role = getattr(user, "role", None)
    if role in ("admin", "owner"):
        return True  # Admin/owner roles have full access

    return all(s in user_scopes for s in required_scopes)


@router.get("/discover")
async def discover_tools(
    user=Depends(get_current_user),
    category: str | None = Query(None, description="Filter by tool category"),
    tag: str | None = Query(None, description="Filter by tag"),
):
    """Return the tools the calling user is authorized to invoke.

    Filters by:
    - ``required_scopes``: tools with no scopes are public; tools with
      scopes require the user to hold all listed scopes.
    - Optional ``category`` and ``tag`` narrowing.
    """
    registry = get_tool_registry()

    tools = registry.list_all()
    if category:
        tools = [t for t in tools if t.category == category]
    if tag:
        tools = [t for t in tools if tag in t.tags]

    # Filter by required_scopes
    permitted = [t for t in tools if _user_has_scopes(user, t.metadata.required_scopes)]

    return ok(
        {
            "tools": [
                {
                    "tool_id": t.tool_id,
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "input_schema": t.metadata.input_schema,
                    "output_schema": t.metadata.output_schema,
                    "requires_auth": t.metadata.requires_auth,
                    "required_scopes": t.metadata.required_scopes,
                    "requires_sandbox": t.metadata.requires_sandbox,
                    "rate_limit_key": t.metadata.rate_limit_key,
                    "tags": t.tags,
                    "timeout_seconds": t.metadata.timeout_seconds,
                }
                for t in permitted
            ],
            "total": len(permitted),
            "categories": sorted(registry._categories.keys()),
        }
    )
