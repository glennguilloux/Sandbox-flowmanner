"""Shared authorization constants for role-based and scope-based access control.

Phase 2: extracted from hardcoded strings in v2/tools.py ``_user_has_scopes``
and chat_service.py ``_execute_tool_call``.

Usage::

    from app.core.auth_constants import ADMIN_ROLES

    if role in ADMIN_ROLES:
        return True  # full access
"""

from __future__ import annotations

# Roles that bypass scope checks entirely.
# Used by both the tool discovery endpoint (v2/tools.py) and the
# streaming chat tool-execution gate (chat_service.py).
ADMIN_ROLES: frozenset[str] = frozenset({"admin", "owner"})
