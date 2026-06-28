"""
Integration Bridge — Wires OAuth-connected integrations into Nexus capabilities.

When a user connects an external service (Slack, GitHub, Google) via the
settings/integrations page, this bridge:

1. Registers the connection's capabilities in the Nexus CapabilityRegistry
   so agents can discover and execute them.
2. On disconnect, unregisters those capabilities.
3. On startup, re-registers capabilities for all active connections.
4. Provides a factory to create live connector instances backed by the
   user's encrypted OAuth tokens.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.oauth import OAUTH_PROVIDERS, decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

# ── Capability definitions per integration slug ──────────────────────

_INTEGRATION_CAPABILITIES: dict[str, list[dict[str, Any]]] = {
    "slack": [
        {
            "id": "send_message",
            "name": "Send Slack Message",
            "description": "Send a message to a Slack channel or user",
            "params": {"channel": "string", "text": "string"},
        },
        {
            "id": "list_channels",
            "name": "List Slack Channels",
            "description": "List all channels in the Slack workspace",
            "params": {},
        },
        {
            "id": "list_users",
            "name": "List Slack Users",
            "description": "List all users in the Slack workspace",
            "params": {},
        },
        {
            "id": "get_channel_history",
            "name": "Get Slack Channel History",
            "description": "Get recent messages from a Slack channel",
            "params": {"channel": "string", "limit": "integer"},
        },
    ],
    "github": [
        {
            "id": "create_issue",
            "name": "Create GitHub Issue",
            "description": "Create a new issue on a GitHub repository",
            "params": {
                "owner": "string",
                "repo": "string",
                "title": "string",
                "body": "string",
            },
        },
        {
            "id": "list_issues",
            "name": "List GitHub Issues",
            "description": "List issues in a GitHub repository",
            "params": {"owner": "string", "repo": "string", "state": "string"},
        },
        {
            "id": "create_pr",
            "name": "Create GitHub Pull Request",
            "description": "Create a pull request on a GitHub repository",
            "params": {
                "owner": "string",
                "repo": "string",
                "title": "string",
                "head": "string",
                "base": "string",
            },
        },
        {
            "id": "list_prs",
            "name": "List GitHub Pull Requests",
            "description": "List pull requests in a GitHub repository",
            "params": {"owner": "string", "repo": "string", "state": "string"},
        },
        {
            "id": "search_code",
            "name": "Search GitHub Code",
            "description": "Search code across GitHub repositories",
            "params": {"q": "string"},
        },
        {
            "id": "get_repo",
            "name": "Get GitHub Repository",
            "description": "Get details about a GitHub repository",
            "params": {"owner": "string", "repo": "string"},
        },
        {
            "id": "list_repos",
            "name": "List GitHub Repositories",
            "description": "List repositories for the authenticated user",
            "params": {},
        },
    ],
    "notion": [
        {
            "id": "search",
            "name": "Search Notion",
            "description": "Search pages and databases by title in Notion",
            "params": {"q": "string", "page_size": "integer"},
        },
        {
            "id": "list_databases",
            "name": "List Notion Databases",
            "description": "List all databases shared with the Notion integration",
            "params": {"page_size": "integer"},
        },
        {
            "id": "query_database",
            "name": "Query Notion Database",
            "description": "Query rows from a Notion database with optional filters and sorts",
            "params": {"database_id": "string", "filter": "object", "sorts": "array"},
        },
        {
            "id": "get_page",
            "name": "Get Notion Page",
            "description": "Get the properties and content of a Notion page",
            "params": {"page_id": "string"},
        },
        {
            "id": "create_page",
            "name": "Create Notion Page",
            "description": "Create a new page in a Notion database or as a sub-page",
            "params": {"parent": "object", "properties": "object", "children": "array"},
        },
        {
            "id": "update_page",
            "name": "Update Notion Page",
            "description": "Update the properties or archive status of a Notion page",
            "params": {"page_id": "string", "properties": "object"},
        },
        {
            "id": "get_block_children",
            "name": "Get Notion Block Children",
            "description": "Get the content blocks of a Notion page or block",
            "params": {"block_id": "string", "page_size": "integer"},
        },
        {
            "id": "append_block_children",
            "name": "Append Notion Blocks",
            "description": "Add content blocks to a Notion page or block",
            "params": {"block_id": "string", "children": "array"},
        },
    ],
    "discord": [
        {
            "id": "send_message",
            "name": "Send Discord Message",
            "description": "Send a message (text or embed) to a Discord channel",
            "params": {"channel_id": "string", "content": "string", "embeds": "array"},
        },
        {
            "id": "edit_message",
            "name": "Edit Discord Message",
            "description": "Edit a previously sent message in a Discord channel",
            "params": {
                "channel_id": "string",
                "message_id": "string",
                "content": "string",
            },
        },
        {
            "id": "get_channel_messages",
            "name": "Get Discord Channel Messages",
            "description": "Read recent messages from a Discord channel",
            "params": {
                "channel_id": "string",
                "limit": "integer",
                "before": "string",
                "after": "string",
            },
        },
        {
            "id": "list_channels",
            "name": "List Discord Channels",
            "description": "List all channels in a Discord guild",
            "params": {"guild_id": "string"},
        },
        {
            "id": "list_guilds",
            "name": "List Discord Guilds",
            "description": "List all guilds (servers) the bot is a member of",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_guild",
            "name": "Get Discord Guild",
            "description": "Get detailed information about a Discord guild",
            "params": {"guild_id": "string"},
        },
        {
            "id": "get_user",
            "name": "Get Discord User",
            "description": "Get a Discord user's profile by ID",
            "params": {"user_id": "string"},
        },
        {
            "id": "create_dm",
            "name": "Create Discord DM",
            "description": "Create a direct message channel with a user",
            "params": {"recipient_id": "string"},
        },
        {
            "id": "add_reaction",
            "name": "Add Discord Reaction",
            "description": "Add an emoji reaction to a message",
            "params": {
                "channel_id": "string",
                "message_id": "string",
                "emoji": "string",
            },
        },
        {
            "id": "create_channel",
            "name": "Create Discord Channel",
            "description": "Create a new channel in a Discord guild",
            "params": {"guild_id": "string", "name": "string", "type": "integer"},
        },
    ],
    "sentry": [
        {
            "id": "list_organizations",
            "name": "List Sentry Organizations",
            "description": "List Sentry organizations accessible to the connected account",
            "params": {},
        },
        {
            "id": "list_projects",
            "name": "List Sentry Projects",
            "description": "List projects in a Sentry organization",
            "params": {"org_slug": "string"},
        },
        {
            "id": "list_issues",
            "name": "List Sentry Issues",
            "description": "List error issues in a Sentry organization/project",
            "params": {"org_slug": "string", "query": "string", "limit": "integer"},
        },
        {
            "id": "get_issue",
            "name": "Get Sentry Issue",
            "description": "Get details of a specific Sentry issue",
            "params": {"issue_id": "string"},
        },
        {
            "id": "get_latest_event",
            "name": "Get Sentry Latest Event",
            "description": "Get the latest event (with stack trace) for a Sentry issue",
            "params": {"issue_id": "string"},
        },
        {
            "id": "resolve_issue",
            "name": "Resolve Sentry Issue",
            "description": "Mark a Sentry issue as resolved",
            "params": {"issue_id": "string"},
        },
        {
            "id": "ignore_issue",
            "name": "Ignore Sentry Issue",
            "description": "Mark a Sentry issue as ignored",
            "params": {"issue_id": "string"},
        },
        {
            "id": "list_releases",
            "name": "List Sentry Releases",
            "description": "List releases in a Sentry organization",
            "params": {"org_slug": "string"},
        },
    ],
    "linear": [
        {
            "id": "create_issue",
            "name": "Create Linear Issue",
            "description": "Create a new issue in Linear",
            "params": {
                "title": "string",
                "team_id": "string",
                "description": "string",
                "priority": "integer",
            },
        },
        {
            "id": "update_issue",
            "name": "Update Linear Issue",
            "description": "Update an existing Linear issue (title, status, priority, etc.)",
            "params": {
                "issue_id": "string",
                "title": "string",
                "state_id": "string",
                "priority": "integer",
            },
        },
        {
            "id": "get_issue",
            "name": "Get Linear Issue",
            "description": "Get a Linear issue by ID or identifier (e.g., TEAM-123)",
            "params": {"issue_id": "string", "identifier": "string"},
        },
        {
            "id": "list_issues",
            "name": "List Linear Issues",
            "description": "List issues for a Linear team",
            "params": {"team_id": "string", "max_results": "integer"},
        },
        {
            "id": "search_issues",
            "name": "Search Linear Issues",
            "description": "Search for Linear issues by identifier (e.g., TEAM-123)",
            "params": {"q": "string"},
        },
        {
            "id": "add_comment",
            "name": "Add Linear Comment",
            "description": "Add a comment to a Linear issue",
            "params": {"issue_id": "string", "body": "string"},
        },
        {
            "id": "list_teams",
            "name": "List Linear Teams",
            "description": "List all teams in the Linear workspace",
            "params": {},
        },
    ],
    "vercel": [
        {
            "id": "get_me",
            "name": "Get Vercel User",
            "description": "Get authenticated Vercel user info",
            "params": {},
        },
        {
            "id": "list_projects",
            "name": "List Vercel Projects",
            "description": "List Vercel projects",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_project",
            "name": "Get Vercel Project",
            "description": "Get project details",
            "params": {"project_id": "string"},
        },
        {
            "id": "list_deployments",
            "name": "List Vercel Deployments",
            "description": "List deployments, optionally filtered by project",
            "params": {"project_id": "string", "limit": "integer"},
        },
        {
            "id": "get_deployment",
            "name": "Get Vercel Deployment",
            "description": "Get deployment details (status, URL, build info)",
            "params": {"deployment_id": "string"},
        },
        {
            "id": "cancel_deployment",
            "name": "Cancel Vercel Deployment",
            "description": "Cancel a running deployment",
            "params": {"deployment_id": "string"},
        },
        {
            "id": "redeploy",
            "name": "Redeploy Vercel Project",
            "description": "Trigger a redeployment from an existing deployment",
            "params": {"deployment_id": "string", "target": "string"},
        },
        {
            "id": "get_deployment_logs",
            "name": "Get Deployment Logs",
            "description": "Get build events and logs for a deployment",
            "params": {"deployment_id": "string"},
        },
        {
            "id": "list_domains",
            "name": "List Vercel Domains",
            "description": "List domains for a Vercel project",
            "params": {"project_id": "string"},
        },
    ],
    "jira": [
        {
            "id": "list_projects",
            "name": "List Jira Projects",
            "description": "List all Jira projects",
            "params": {},
        },
        {
            "id": "get_project",
            "name": "Get Jira Project",
            "description": "Get Jira project details",
            "params": {"project_key": "string"},
        },
        {
            "id": "search_issues",
            "name": "Search Jira Issues",
            "description": "Search issues with JQL query",
            "params": {"jql": "string", "max_results": "integer"},
        },
        {
            "id": "get_issue",
            "name": "Get Jira Issue",
            "description": "Get Jira issue details",
            "params": {"issue_key": "string"},
        },
        {
            "id": "create_issue",
            "name": "Create Jira Issue",
            "description": "Create a new Jira issue (description auto-converted to ADF)",
            "params": {
                "project_key": "string",
                "summary": "string",
                "issue_type": "string",
                "description": "string",
            },
        },
        {
            "id": "update_issue",
            "name": "Update Jira Issue",
            "description": "Update Jira issue fields",
            "params": {"issue_key": "string", "fields": "object"},
        },
        {
            "id": "add_comment",
            "name": "Add Jira Comment",
            "description": "Add a comment to a Jira issue (auto-converted to ADF)",
            "params": {"issue_key": "string", "body": "string"},
        },
        {
            "id": "transition_issue",
            "name": "Transition Jira Issue",
            "description": "Change issue status via transition",
            "params": {"issue_key": "string", "transition_id": "string"},
        },
        {
            "id": "list_boards",
            "name": "List Jira Boards",
            "description": "List Scrum/Kanban boards",
            "params": {},
        },
        {
            "id": "list_sprints",
            "name": "List Jira Sprints",
            "description": "List sprints for a board",
            "params": {"board_id": "integer"},
        },
    ],
    "confluence": [
        {
            "id": "get_me",
            "name": "Get Confluence User",
            "description": "Get authenticated Confluence user info",
            "params": {},
        },
        {
            "id": "list_spaces",
            "name": "List Confluence Spaces",
            "description": "List Confluence spaces",
            "params": {"limit": "integer"},
        },
        {
            "id": "get_space",
            "name": "Get Confluence Space",
            "description": "Get space details",
            "params": {"space_id": "string"},
        },
        {
            "id": "get_page",
            "name": "Get Confluence Page",
            "description": "Get page details with body",
            "params": {"page_id": "string"},
        },
        {
            "id": "create_page",
            "name": "Create Confluence Page",
            "description": "Create a new page in a Confluence space",
            "params": {
                "space_id": "string",
                "title": "string",
                "body": "string",
                "parent_id": "string",
            },
        },
        {
            "id": "update_page",
            "name": "Update Confluence Page",
            "description": "Update page content (auto-increments version)",
            "params": {
                "page_id": "string",
                "title": "string",
                "body": "string",
            },
        },
        {
            "id": "search_content",
            "name": "Search Confluence Content",
            "description": "Search content with CQL query",
            "params": {"cql": "string", "limit": "integer"},
        },
        {
            "id": "list_page_children",
            "name": "List Confluence Page Children",
            "description": "List sub-pages of a page",
            "params": {"page_id": "string", "limit": "integer"},
        },
        {
            "id": "add_comment",
            "name": "Add Confluence Comment",
            "description": "Add a comment to a Confluence page",
            "params": {"page_id": "string", "body": "string"},
        },
        {
            "id": "list_attachments",
            "name": "List Confluence Attachments",
            "description": "List attachments on a page",
            "params": {"page_id": "string", "limit": "integer"},
        },
        {
            "id": "add_labels",
            "name": "Add Confluence Labels",
            "description": "Add labels to a Confluence page",
            "params": {"page_id": "string", "labels": "array"},
        },
    ],
    "figma": [
        {
            "id": "get_me",
            "name": "Get Figma User",
            "description": "Get authenticated Figma user info",
            "params": {},
        },
        {
            "id": "get_file",
            "name": "Get Figma File",
            "description": "Get file details (nodes, styles, components)",
            "params": {"file_key": "string"},
        },
        {
            "id": "get_file_nodes",
            "name": "Get Figma File Nodes",
            "description": "Get specific nodes from a file",
            "params": {"file_key": "string", "node_ids": "array"},
        },
        {
            "id": "list_comments",
            "name": "List Figma Comments",
            "description": "List comments on a Figma file",
            "params": {"file_key": "string"},
        },
        {
            "id": "post_comment",
            "name": "Post Figma Comment",
            "description": "Add a comment to a Figma file",
            "params": {"file_key": "string", "message": "string"},
        },
        {
            "id": "get_file_versions",
            "name": "Get Figma File Versions",
            "description": "Get version history of a file",
            "params": {"file_key": "string"},
        },
        {
            "id": "list_team_projects",
            "name": "List Figma Team Projects",
            "description": "List projects for a Figma team",
            "params": {"team_id": "string"},
        },
        {
            "id": "list_project_files",
            "name": "List Figma Project Files",
            "description": "List files in a Figma project",
            "params": {"project_id": "string"},
        },
    ],
    "google": [
        # Drive
        {
            "id": "drive_list_files",
            "name": "List Google Drive Files",
            "description": "List files in Google Drive",
            "params": {"folder_id": "string", "max_results": "integer"},
        },
        {
            "id": "drive_search_files",
            "name": "Search Google Drive Files",
            "description": "Search for files by name in Google Drive",
            "params": {"query": "string", "max_results": "integer"},
        },
        {
            "id": "drive_get_file",
            "name": "Get Google Drive File",
            "description": "Get file metadata from Google Drive",
            "params": {"file_id": "string"},
        },
        {
            "id": "drive_create_folder",
            "name": "Create Google Drive Folder",
            "description": "Create a new folder in Google Drive",
            "params": {"name": "string", "parent_id": "string"},
        },
        # Gmail
        {
            "id": "gmail_send",
            "name": "Send Gmail Email",
            "description": "Send an email via Gmail",
            "params": {"to": "string", "subject": "string", "body": "string"},
        },
        {
            "id": "gmail_list",
            "name": "List Gmail Emails",
            "description": "List recent emails from Gmail inbox",
            "params": {"max_results": "integer", "q": "string"},
        },
        {
            "id": "gmail_search",
            "name": "Search Gmail Emails",
            "description": "Search emails in Gmail",
            "params": {"q": "string", "max_results": "integer"},
        },
        # Calendar
        {
            "id": "calendar_list_events",
            "name": "List Calendar Events",
            "description": "List events from Google Calendar",
            "params": {
                "calendar_id": "string",
                "max_results": "integer",
                "time_min": "string",
                "time_max": "string",
            },
        },
        {
            "id": "calendar_create_event",
            "name": "Create Calendar Event",
            "description": "Create a new event in Google Calendar",
            "params": {
                "summary": "string",
                "start": "object",
                "end": "object",
                "description": "string",
            },
        },
        {
            "id": "calendar_get_event",
            "name": "Get Calendar Event",
            "description": "Get details about a Google Calendar event",
            "params": {"calendar_id": "string", "event_id": "string"},
        },
    ],
}


# ── Non-OAuth integrations (API key / bot token based) ─────────
# These skip the per-user OAuth token DB lookup entirely.
# Add new entries here when building API-key-backed connectors.

_NON_OAUTH_CONFIGS: dict[str, dict[str, Any]] = {
    "linear": {
        "name": "linear-workspace",
        "auth_type": "api_key",
        "label": "Linear API key",
    },
    "discord": {
        "name": "discord-bot",
        "auth_type": "bearer_token",
        "label": "Discord bot token",
    },
    "apiflow": {
        "name": "apiflow-instance",
        "auth_type": "api_key",
        "label": "Apiflow API key + instance URL",
    },
    "sentry": {
        "name": "sentry-instance",
        "auth_type": "bearer_token",
        "label": "Sentry API token",
    },
}


# ── Bridge Service ────────────────────────────────────────────────────


@dataclass
class IntegrationCapabilityRegistration:
    """Tracks a user's registered integration capability IDs."""

    user_id: int
    slug: str
    capability_ids: list[str] = field(default_factory=list)


class IntegrationBridge:
    """
    Bridges OAuth token storage to the Nexus capability system.

    Responsibilities:
    - Register/unregister integration capabilities per user
    - Create live connector instances backed by encrypted tokens
    - Re-register all active connections on startup
    """

    def __init__(self):
        self._active_registrations: dict[str, IntegrationCapabilityRegistration] = {}

    @staticmethod
    def _registration_key(user_id: int, slug: str) -> str:
        return f"{user_id}:{slug}"

    # ── Capability Registration ─────────────────────────────────

    async def register_capabilities_for_user(
        self,
        user_id: int,
        slug: str,
    ) -> list[str]:
        """
        Register all capabilities for a user's integration in Nexus.

        Called after OAuth callback stores the token.
        """
        capabilities = _INTEGRATION_CAPABILITIES.get(slug)
        if not capabilities:
            logger.debug("No Nexus capabilities defined for integration: %s", slug)
            return []

        try:
            from app.services.nexus.capability_registry import (
                Capability,
                get_capability_registry,
            )

            registry = get_capability_registry()
            registered_ids: list[str] = []

            for cap_def in capabilities:
                cap_id = f"integration:{slug}:{cap_def['id']}"
                try:
                    # Build input schema from params
                    properties = {}
                    for pname, ptype in cap_def.get("params", {}).items():
                        properties[pname] = {"type": ptype}

                    # Create a handler that executes the action via the bridge
                    async def make_handler(uid=user_id, s=slug, action=cap_def["id"]):
                        async def handler(params: dict[str, Any]) -> dict[str, Any]:
                            bridge = get_integration_bridge()
                            result = await bridge.execute_integration_action(uid, s, action, params)
                            if result.success:
                                return {"success": True, "data": result.data}
                            return {"success": False, "error": result.error}

                        return handler

                    capability = Capability(
                        id=cap_id,
                        name=cap_def["name"],
                        description=f"[Integration: {slug}] {cap_def['description']}",
                        category=f"integration:{slug}",
                        handler=await make_handler(),
                        input_schema={
                            "type": "object",
                            "properties": properties,
                        },
                        requires_auth=True,
                        metadata={
                            "user_id": user_id,
                            "integration_slug": slug,
                            "action": cap_def["id"],
                            "source": "integration",
                        },
                    )

                    # Register — this replaces any previous registration
                    registry.register(capability)
                    registered_ids.append(cap_id)
                    logger.debug(
                        "Registered Nexus capability: %s for user %s",
                        cap_id,
                        user_id,
                    )

                except Exception as e:
                    logger.warning(
                        "Failed to register capability %s for user %s: %s",
                        cap_def["id"],
                        user_id,
                        e,
                    )

            # Track the registration
            key = self._registration_key(user_id, slug)
            self._active_registrations[key] = IntegrationCapabilityRegistration(
                user_id=user_id,
                slug=slug,
                capability_ids=registered_ids,
            )

            logger.info(
                "Registered %d Nexus capabilities for user %s integration %s",
                len(registered_ids),
                user_id,
                slug,
            )

            return registered_ids

        except Exception as e:
            logger.warning(
                "Failed to register capabilities for user %s, %s: %s",
                user_id,
                slug,
                e,
            )
            return []

    async def unregister_capabilities_for_user(
        self,
        user_id: int,
        slug: str,
    ) -> int:
        """
        Unregister all Nexus capabilities for a user's integration.

        Called on disconnect.
        """
        key = self._registration_key(user_id, slug)
        reg = self._active_registrations.pop(key, None)

        if not reg or not reg.capability_ids:
            logger.debug("No capabilities to unregister for user %s, %s", user_id, slug)
            return 0

        try:
            from app.services.nexus.capability_registry import get_capability_registry

            registry = get_capability_registry()
            unregistered = 0

            for cap_id in reg.capability_ids:
                if registry.unregister(cap_id):
                    unregistered += 1

            logger.info(
                "Unregistered %d Nexus capabilities for user %s integration %s",
                unregistered,
                user_id,
                slug,
            )

            return unregistered

        except Exception as e:
            logger.warning(
                "Failed to unregister capabilities for user %s, %s: %s",
                user_id,
                slug,
                e,
            )
            return 0

    # ── Non-OAuth Connector Factory ───────────────────────────

    @staticmethod
    async def _get_non_oauth_connector(slug: str):
        """
        Create a connector for non-OAuth integrations (API key, bot token, etc.).

        Looks up slug in _NON_OAUTH_CONFIGS and creates a ConnectorConfig with
        the appropriate auth type. Settings/env vars provide the actual credential.
        """
        from app.services.connectors import AuthType, ConnectorConfig, ConnectorManager

        cfg = _NON_OAUTH_CONFIGS.get(slug)
        if not cfg:
            logger.warning("No non-OAuth config for: %s", slug)
            return None

        manager = ConnectorManager()
        cls = manager.get_connector_class(slug)
        if not cls:
            logger.warning("No connector class for: %s", slug)
            return None

        # Map auth type string to AuthType enum
        try:
            auth_type = getattr(AuthType, cfg["auth_type"].upper())
        except AttributeError:
            logger.error(
                "Non-OAuth config for %s has unknown auth_type: %s",
                slug,
                cfg["auth_type"],
            )
            return None

        config = ConnectorConfig(
            name=cfg["name"],
            connector_type=slug,
            auth_type=auth_type,
            auth_config={},
        )

        connector = cls(config)
        connected = await connector.connect()
        if not connected:
            logger.warning("Failed to connect %s connector (check %s)", slug, cfg["label"])
            return None

        return connector

    # ── Token-Backed Connector Factory ──────────────────────────

    async def get_connector_for_user(
        self,
        user_id: int,
        slug: str,
    ):
        """
        Create a live connector instance backed by the user's encrypted token.

        Automatically refreshes expired Google OAuth tokens before use.
        Returns None if no active connection exists.

        API-key integrations (e.g., Linear) skip the OAuth token flow entirely.
        """
        # ── Non-OAuth integrations (API key / bot token) ──
        if slug in _NON_OAUTH_CONFIGS:
            return await self._get_non_oauth_connector(slug)

        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            return await self._get_connector(session, user_id, slug)

    async def _get_connector(
        self,
        db: AsyncSession,
        user_id: int,
        slug: str,
    ):
        from app.models.phase4_models import IntegrationConnection
        from app.services.connectors import AuthType, ConnectorConfig, ConnectorManager

        result = await db.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.integration_slug == slug,
                IntegrationConnection.is_active.is_(True),
            )
        )
        conn = result.scalar_one_or_none()

        if not conn or not conn.encrypted_access_token:
            logger.warning("No active token for user %s, integration %s", user_id, slug)
            return None

        # Decrypt the token
        try:
            access_token = decrypt_token(conn.encrypted_access_token)
        except Exception as e:
            logger.error("Failed to decrypt token for user %s, %s: %s", user_id, slug, e)
            return None

        # ── Auto-refresh expired Google OAuth tokens ─────────────
        if slug == "google" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_google_token(decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    # Encrypt and store the fresh token
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Google token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Google token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Jira (Atlassian) OAuth tokens ──
        if slug == "jira" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("jira", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Jira token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Jira token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Confluence (Atlassian) OAuth tokens ──
        if slug == "confluence" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("confluence", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Confluence token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Confluence token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Auto-refresh expired Figma OAuth tokens ──────────────
        if slug == "figma" and conn.encrypted_refresh_token:
            try:
                new_token = await self._refresh_oauth_token("figma", decrypt_token(conn.encrypted_refresh_token))
                if new_token:
                    conn.encrypted_access_token = encrypt_token(new_token["access_token"])
                    if new_token.get("refresh_token"):
                        conn.encrypted_refresh_token = encrypt_token(new_token["refresh_token"])
                    if new_token.get("expires_in"):
                        from datetime import timedelta

                        conn.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                            seconds=int(new_token["expires_in"])
                        )
                    await db.commit()
                    access_token = new_token["access_token"]
                    logger.info(
                        "Refreshed Figma token for user %s (expires in %ss)",
                        user_id,
                        new_token.get("expires_in", "?"),
                    )
            except Exception as e:
                logger.warning("Failed to refresh Figma token for user %s: %s", user_id, e)
                # Fall through — try the existing token anyway in case it's still valid

        # ── Jira + Confluence: extract cloudId from account_id ──
        extra_auth_config: dict[str, str] = {}
        if slug in ("jira", "confluence"):
            cloud_id = conn.account_id
            if not cloud_id:
                logger.warning("No cloudId for user %s %s connection", user_id, slug)
                return None
            extra_auth_config["cloud_id"] = cloud_id

        # Create connector config with the (possibly refreshed) decrypted token
        auth_config: dict[str, Any] = {"access_token": access_token, **extra_auth_config}
        config = ConnectorConfig(
            name=f"{slug}-user-{user_id}",
            connector_type=slug,
            auth_type=AuthType.OAUTH2,
            auth_config=auth_config,
        )

        manager = ConnectorManager()
        cls = manager.get_connector_class(slug)
        if not cls:
            logger.warning("No connector class for: %s", slug)
            return None

        connector = cls(config)
        connected = await connector.connect()
        if not connected:
            logger.warning("Failed to connect %s connector for user %s", slug, user_id)
            return None

        return connector

    # ── Action Execution ────────────────────────────────────────

    async def execute_integration_action(
        self,
        user_id: int,
        slug: str,
        action: str,
        params: dict[str, Any],
    ) -> Any:
        """
        Execute an integration action on behalf of a user.

        This is called by the Nexus capability handlers registered above.
        """
        connector = await self.get_connector_for_user(user_id, slug)
        if not connector:
            from app.services.connectors.base import ConnectorResponse

            return ConnectorResponse(
                success=False,
                error=f"No active {slug} connection for user {user_id}",
                status_code=401,
            )

        try:
            result = await connector.execute_action(action, params)
            return result
        finally:
            await connector.disconnect()

    # ── Token Refresh ───────────────────────────────────────────

    @staticmethod
    async def _refresh_google_token(refresh_token: str) -> dict[str, Any] | None:
        """
        Exchange a Google refresh token for a fresh access token.

        Returns {'access_token': ..., 'expires_in': ..., 'refresh_token': ...}
        or None on failure.
        """
        provider = OAUTH_PROVIDERS.get("google")
        if not provider or not provider.is_configured:
            logger.warning("Google OAuth provider not configured — cannot refresh token")
            return None

        data = {
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(provider.token_url, data=data)

        if resp.status_code != 200:
            logger.warning(
                "Google token refresh failed: %s %s",
                resp.status_code,
                resp.text[:200],
            )
            return None

        return resp.json()

    @staticmethod
    async def _refresh_oauth_token(slug: str, refresh_token: str) -> dict[str, Any] | None:
        """
        Generic OAuth2 refresh — works for any provider that uses the standard
        `grant_type=refresh_token` flow at the same token_url.

        Used by Jira, Confluence, Figma, and future standard OAuth2 providers.
        Returns {'access_token': ..., 'expires_in': ..., 'refresh_token': ...}
        or None on failure.
        """
        provider = OAUTH_PROVIDERS.get(slug)
        if not provider or not provider.is_configured:
            logger.warning("OAuth provider '%s' not configured — cannot refresh token", slug)
            return None

        data = {
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                provider.token_url,
                data=data,
                headers={"Accept": "application/json"},
            )

        if resp.status_code != 200:
            logger.warning(
                "%s token refresh failed: %s %s",
                slug,
                resp.status_code,
                resp.text[:200],
            )
            return None

        return resp.json()

    # ── Startup Re-Registration ────────────────────────────────

    async def register_all_active_connections(self) -> int:
        """
        Re-register Nexus capabilities for all active integration connections.

        Called at application startup.
        """
        from app.database import AsyncSessionLocal
        from app.models.phase4_models import IntegrationConnection

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(IntegrationConnection).where(
                    IntegrationConnection.is_active.is_(True),
                    IntegrationConnection.encrypted_access_token.is_not(None),
                )
            )
            connections = result.scalars().all()

        total = 0
        for conn in connections:
            try:
                registered = await self.register_capabilities_for_user(
                    user_id=conn.user_id,
                    slug=conn.integration_slug,
                )
                total += len(registered)
            except Exception as e:
                logger.warning(
                    "Failed to re-register capabilities for user %s, %s: %s",
                    conn.user_id,
                    conn.integration_slug,
                    e,
                )

        logger.info(
            "Startup: re-registered %d Nexus capabilities from %d active connections",
            total,
            len(connections),
        )
        return total


# ── Singleton ─────────────────────────────────────────────────────────

_bridge: IntegrationBridge | None = None


def get_integration_bridge() -> IntegrationBridge:
    """Get or create the singleton IntegrationBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = IntegrationBridge()
    return _bridge
