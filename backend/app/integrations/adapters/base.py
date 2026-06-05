"""Base integration adapter — shared OAuth token handling and action dispatch."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.integration_models import UserOAuthConnection

logger = logging.getLogger(__name__)


class BaseIntegrationAdapter(ABC):
    """Abstract base for service-specific integration adapters.

    Each adapter implements service-specific actions (e.g., Slack's
    send_message, GitHub's create_issue).  The base class provides
    common token retrieval, refresh, and error handling.

    Subclasses override:
        - ``_execute_action(action, params, access_token)`` to
          implement provider-specific action dispatch.
        - Optionally ``_refresh_token(connection, db)`` to refresh
          expired OAuth tokens.

    Usage::

        adapter = SlackAdapter()
        result = await adapter.execute(
            action="send_message",
            params={"channel": "#general", "text": "Hello"},
            connection=slack_connection,
        )
    """

    # Override in subclasses — the provider slug (slack, github, etc.)
    provider: str = ""

    # ── Public API ─────────────────────────────────────────────────────────

    @abstractmethod
    async def _execute_action(
        self,
        action: str,
        params: dict[str, Any],
        access_token: str,
    ) -> dict[str, Any]:
        """Execute a service-specific action.

        Args:
            action: Action name (e.g., "send_message").
            params: Action parameters from the caller.
            access_token: Decrypted OAuth access token.

        Returns:
            Dict with ``success``, ``response`` (action output),
            ``error`` (on failure).
        """
        ...

    async def execute(
        self,
        action: str,
        params: dict[str, Any],
        connection: UserOAuthConnection,
    ) -> dict[str, Any]:
        """Execute an action against a connected service.

        Retrieves the access token from the connection (decrypting it),
        executes the action, and handles 401 token-refresh scenarios.

        Args:
            action: Action name (e.g., "send_message").
            params: Action parameters dict.
            connection: UserOAuthConnection with stored encrypted tokens.

        Returns:
            Dict with:
                - ``success`` (bool)
                - ``response`` (Any) — action-specific output payload
                - ``error`` (str | None) — on failure
        """
        if connection.provider != self.provider:
            return {
                "success": False,
                "error": (
                    f"Provider mismatch: adapter is for {self.provider}, "
                    f"connection is for {connection.provider}"
                ),
            }

        access_token = connection.get_access_token()
        if not access_token:
            return {
                "success": False,
                "error": "No access token available for this connection",
            }

        result = await self._execute_action(action, params, access_token)

        # Handle token expiry (401) — try refresh if supported
        if not result.get("success") and result.get("error") == "token_expired":
            new_token = await self._refresh_token(connection)
            if new_token:
                result = await self._execute_action(action, params, new_token)

        return result

    # ── Token refresh (override in subclasses that support refresh) ────────

    async def _refresh_token(self, connection: UserOAuthConnection) -> str | None:
        """Attempt to refresh the OAuth access token.

        Subclasses override this if the provider supports refresh tokens
        (e.g., Google, Slack).

        Args:
            connection: The connection with an expired token.

        Returns:
            The new access token, or None if refresh is not supported
            or failed.
        """
        return None
