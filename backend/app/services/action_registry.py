"""Action registry — discovers adapters and dispatches integration actions.

Provides:
    - ``get_available_actions(user_id, db)`` — actions the user can use
      based on their active OAuth connections.
    - ``execute_action(user_id, connection_id, action_name, params, db)`` —
      invokes the appropriate adapter with the user's stored token.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.integration_models import UserOAuthConnection

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Action catalog ────────────────────────────────────────────────────────────
# Each adapter's actions are declared here with their input schema so the
# frontend can render dynamic forms without hard-coding provider logic.

_ACTION_CATALOG: dict[str, dict[str, Any]] = {}

# --------------------------------------------------------------------------- #
# Slack
# --------------------------------------------------------------------------- #
_ACTION_CATALOG["slack.send_message"] = {
    "provider": "slack",
    "name": "send_message",
    "label": "Send Message",
    "description": "Post a message to a Slack channel.",
    "required_params": ["channel", "text"],
    "optional_params": ["thread_ts"],
}
_ACTION_CATALOG["slack.search_messages"] = {
    "provider": "slack",
    "name": "search_messages",
    "label": "Search Messages",
    "description": "Search messages in your Slack workspace.",
    "required_params": ["query"],
    "optional_params": ["limit"],
}
_ACTION_CATALOG["slack.list_channels"] = {
    "provider": "slack",
    "name": "list_channels",
    "label": "List Channels",
    "description": "List public channels in your Slack workspace.",
    "required_params": [],
    "optional_params": ["limit", "cursor"],
}
_ACTION_CATALOG["slack.create_channel"] = {
    "provider": "slack",
    "name": "create_channel",
    "label": "Create Channel",
    "description": "Create a new public or private Slack channel.",
    "required_params": ["name"],
    "optional_params": ["is_private"],
}

# --------------------------------------------------------------------------- #
# GitHub
# --------------------------------------------------------------------------- #
_ACTION_CATALOG["github.create_issue"] = {
    "provider": "github",
    "name": "create_issue",
    "label": "Create Issue",
    "description": "Create a new issue in a GitHub repository.",
    "required_params": ["owner", "repo", "title"],
    "optional_params": ["body", "labels"],
}
_ACTION_CATALOG["github.create_pr"] = {
    "provider": "github",
    "name": "create_pr",
    "label": "Create Pull Request",
    "description": "Create a new pull request.",
    "required_params": ["owner", "repo", "title", "head", "base"],
    "optional_params": ["body"],
}
_ACTION_CATALOG["github.search_repos"] = {
    "provider": "github",
    "name": "search_repos",
    "label": "Search Repositories",
    "description": "Search GitHub repositories.",
    "required_params": ["query"],
    "optional_params": ["sort", "limit"],
}
_ACTION_CATALOG["github.get_file_contents"] = {
    "provider": "github",
    "name": "get_file_contents",
    "label": "Get File Contents",
    "description": "Retrieve file contents from a GitHub repository.",
    "required_params": ["owner", "repo", "path"],
    "optional_params": ["ref"],
}

# --------------------------------------------------------------------------- #
# Notion
# --------------------------------------------------------------------------- #
_ACTION_CATALOG["notion.create_page"] = {
    "provider": "notion",
    "name": "create_page",
    "label": "Create Page",
    "description": "Create a new page in a Notion parent page or database.",
    "required_params": ["parent_page_id", "properties"],
    "optional_params": ["children"],
}
_ACTION_CATALOG["notion.query_database"] = {
    "provider": "notion",
    "name": "query_database",
    "label": "Query Database",
    "description": "Query a Notion database with optional filters and sorts.",
    "required_params": ["database_id"],
    "optional_params": ["filter", "sorts", "limit"],
}
_ACTION_CATALOG["notion.append_block"] = {
    "provider": "notion",
    "name": "append_block",
    "label": "Append Block",
    "description": "Append children blocks to a Notion block.",
    "required_params": ["block_id", "children"],
    "optional_params": [],
}

# --------------------------------------------------------------------------- #
# Google Drive
# --------------------------------------------------------------------------- #
_ACTION_CATALOG["google_drive.list_files"] = {
    "provider": "google_drive",
    "name": "list_files",
    "label": "List Files",
    "description": "List files in your Google Drive with optional query filter.",
    "required_params": [],
    "optional_params": ["query", "page_size"],
}
_ACTION_CATALOG["google_drive.create_doc"] = {
    "provider": "google_drive",
    "name": "create_doc",
    "label": "Create Google Doc",
    "description": "Create a new Google Doc, optionally with content.",
    "required_params": ["title"],
    "optional_params": ["folder_id", "content"],
}
_ACTION_CATALOG["google_drive.search_files"] = {
    "provider": "google_drive",
    "name": "search_files",
    "label": "Search Files",
    "description": "Search files in Google Drive by name or content.",
    "required_params": ["query"],
    "optional_params": ["page_size"],
}
_ACTION_CATALOG["google_drive.read_file"] = {
    "provider": "google_drive",
    "name": "read_file",
    "label": "Read File",
    "description": "Read the contents of a file from Google Drive (max 10 MB).",
    "required_params": ["file_id"],
    "optional_params": [],
}

# --------------------------------------------------------------------------- #
# Linear
# --------------------------------------------------------------------------- #
_ACTION_CATALOG["linear.create_issue"] = {
    "provider": "linear",
    "name": "create_issue",
    "label": "Create Issue",
    "description": "Create a new issue in a Linear team.",
    "required_params": ["team_id", "title"],
    "optional_params": ["description", "priority", "assignee_id"],
}
_ACTION_CATALOG["linear.update_issue"] = {
    "provider": "linear",
    "name": "update_issue",
    "label": "Update Issue",
    "description": "Update an existing Linear issue.",
    "required_params": ["issue_id"],
    "optional_params": ["title", "description", "status", "priority"],
}
_ACTION_CATALOG["linear.search_issues"] = {
    "provider": "linear",
    "name": "search_issues",
    "label": "Search Issues",
    "description": "Search for issues across Linear teams.",
    "required_params": ["query"],
    "optional_params": ["limit"],
}
_ACTION_CATALOG["linear.list_projects"] = {
    "provider": "linear",
    "name": "list_projects",
    "label": "List Projects",
    "description": "List Linear projects, optionally scoped to a team.",
    "required_params": [],
    "optional_params": ["team_id", "limit"],
}

# ── Public API ────────────────────────────────────────────────────────────────


async def get_available_actions(
    user_id: str,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Return the list of integration actions available to a user.

    Each item includes the action metadata from the catalog AND the
    ``connection_id`` so the caller can target a specific connection.

    Returns a list of dicts with keys:
        - ``provider``, ``name``, ``label``, ``description``
        - ``required_params``, ``optional_params``
        - ``connection_id``, ``provider_account_name``
    """
    # Fetch active OAuth connections for this user
    result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user_id,
            UserOAuthConnection.status == "active",
        )
    )
    connections = result.scalars().all()

    actions: list[dict[str, Any]] = []

    for conn in connections:
        provider = conn.provider
        # Find all catalog entries for this provider
        for meta in _ACTION_CATALOG.values():
            if meta["provider"] != provider:
                continue
            actions.append(
                {
                    **meta,
                    "connection_id": str(conn.id),
                    "provider_account_name": conn.provider_account_name or provider,
                }
            )

    # Sort by provider then action name for stable output
    actions.sort(key=lambda a: (a["provider"], a["name"]))
    return actions


async def execute_action(
    *,
    user_id: str,
    connection_id: str,
    action_name: str,
    params: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """Execute an integration action against a user's connected service.

    Args:
        user_id: The calling user's ID.
        connection_id: The OAuth connection to use.
        action_name: Action slug (e.g. ``"send_message"``).
        params: Action parameters dict.
        db: SQLAlchemy async session.

    Returns:
        Standard result dict with ``success``, ``response``, ``error``.
    """
    # 1. Look up the connection (ownership check)
    result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.id == connection_id,
            UserOAuthConnection.user_id == user_id,
        )
    )
    connection = result.scalars().first()
    if not connection:
        return {"success": False, "error": "Connection not found"}

    if connection.status != "active":
        return {
            "success": False,
            "error": f"Connection is {connection.status} (not active)",
        }

    # 2. Find the adapter for this provider
    adapter = _get_adapter(connection.provider)
    if not adapter:
        return {
            "success": False,
            "error": f"No adapter registered for provider: {connection.provider}",
        }

    # 3. Validate action exists in catalog
    catalog_key = f"{connection.provider}.{action_name}"
    if catalog_key not in _ACTION_CATALOG:
        return {
            "success": False,
            "error": f"Unknown action '{action_name}' for provider '{connection.provider}'",
        }

    # 4. Dispatch to adapter (with usage tracking)
    import time as _time

    start = _time.monotonic()
    try:
        action_result = await adapter.execute(
            action=action_name,
            params=params,
            connection=connection,
        )
        latency_ms = int((_time.monotonic() - start) * 1000)

        # Record usage (fire-and-forget — don't fail the action if logging fails)
        try:
            from app.services.integration_usage_service import IntegrationUsageService

            usage_svc = IntegrationUsageService(db)
            await usage_svc.record_call(
                user_id=int(user_id),
                integration_slug=connection.provider,
                action=action_name,
                status="success" if action_result.get("success") else "failed",
                latency_ms=latency_ms,
                error_message=action_result.get("error") if not action_result.get("success") else None,
            )
        except Exception:
            logger.debug("Usage recording failed (non-fatal)", exc_info=True)

        return action_result

    except Exception as exc:
        latency_ms = int((_time.monotonic() - start) * 1000)
        logger.exception(
            "Action %s/%s failed for connection %s",
            connection.provider,
            action_name,
            connection_id,
        )

        # Record failed usage
        try:
            from app.services.integration_usage_service import IntegrationUsageService

            usage_svc = IntegrationUsageService(db)
            await usage_svc.record_call(
                user_id=int(user_id),
                integration_slug=connection.provider,
                action=action_name,
                status="failed",
                latency_ms=latency_ms,
                error_message=str(exc)[:500],
            )
        except Exception:
            logger.debug("Usage recording failed (non-fatal)", exc_info=True)

        return {"success": False, "error": str(exc)}


# ── Adapter discovery ─────────────────────────────────────────────────────────

_ADAPTERS: dict[str, Any] | None = None  # lazy singleton


def _get_adapter(provider: str):
    """Return the adapter instance for *provider*, or None."""
    global _ADAPTERS
    if _ADAPTERS is None:
        _ADAPTERS = _discover_adapters()
    return _ADAPTERS.get(provider)


def _discover_adapters() -> dict[str, Any]:
    """Auto-discover adapter classes from the adapters package namespace.

    Since ``adapters/__init__.py`` already imports every adapter class,
    we read them from the package itself — no dynamic imports needed.
    """
    discovered: dict[str, Any] = {}

    try:
        import app.integrations.adapters as pkg
        from app.integrations.adapters.base import BaseIntegrationAdapter

        for name in dir(pkg):
            if name.startswith("_") or name == "BaseIntegrationAdapter":
                continue
            cls = getattr(pkg, name, None)
            if isinstance(cls, type) and issubclass(cls, BaseIntegrationAdapter):
                instance = cls()
                discovered[instance.provider] = instance
                logger.debug("Discovered adapter: %s -> %s", name, instance.provider)

    except Exception as exc:
        logger.error("Adapter discovery failed: %s", exc)

    return discovered
