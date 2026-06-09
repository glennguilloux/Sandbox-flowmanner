"""
Linear Connector

Provides integration with Linear for issue tracking via the BaseConnector framework.
Wraps the existing Linear GraphQL client (app.services.linear.client) to expose
standard connector actions that can be used by the Nexus capability system.

Note: Linear uses a workspace-wide API key (not per-user OAuth), so this connector
does not use the IntegrationBridge's OAuth token flow. It reads the API key from
settings.LINEAR_API_KEY.
"""

import logging
from typing import Any

from app.config import settings

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class LinearConnector(BaseConnector):
    """
    Linear issue tracker connector.

    Wraps the LinearClient GraphQL API behind the standard connector interface.

    Supports:
    - Issue management: create, update, get, search
    - Comments: add comments to issues
    - Teams: list available teams
    """

    CONNECTOR_TYPE = "linear"

    # Linear rate limits: ~250 queries per 30 seconds per workspace
    LINEAR_RATE_LIMIT = RateLimitConfig(
        requests_per_second=5.0,
        requests_per_minute=200,
        requests_per_hour=8000,
        burst_size=10,
    )

    ACTIONS = [
        "create_issue",
        "update_issue",
        "get_issue",
        "search_issues",
        "list_issues",
        "add_comment",
        "list_teams",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.linear.app/graphql"
        config.auth_type = config.auth_type or AuthType.API_KEY
        config.rate_limit = config.rate_limit or self.LINEAR_RATE_LIMIT

        # Use the API key from settings if not provided in auth_config
        if not config.auth_config.get("api_key"):
            api_key = settings.LINEAR_API_KEY
            if api_key:
                config.auth_config["key_name"] = "Authorization"
                config.auth_config["key_value"] = api_key
                config.auth_config["key_location"] = "header"

        super().__init__(config)
        self._linear_client = None
        self._authenticated_team: str | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        """Validate Linear API key by fetching teams."""
        try:
            from app.services.linear.client import LinearClient

            api_key = (
                self.config.auth_config.get("key_value") or settings.LINEAR_API_KEY
            )
            if not api_key:
                logger.warning("No Linear API key configured")
                return False

            self._linear_client = LinearClient(api_key)
            teams = await self._linear_client.get_teams()  # type: ignore[attr-defined]
            if teams:
                self._authenticated_team = teams[0].get("name")
                return True
            return False
        except Exception as e:
            logger.warning("Linear credential validation failed: %s", e)
            return False

    async def execute_action(
        self,
        action: str,
        params: dict[str, Any],
    ) -> ConnectorResponse:
        """Execute a Linear connector action."""

        action_handlers = {
            "create_issue": self._create_issue,
            "update_issue": self._update_issue,
            "get_issue": self._get_issue,
            "search_issues": self._search_issues,
            "list_issues": self._list_issues,
            "add_comment": self._add_comment,
            "list_teams": self._list_teams,
        }

        handler = action_handlers.get(action)
        if not handler:
            return ConnectorResponse(
                success=False,
                error=f"Unknown action: {action}",
                status_code=400,
            )

        try:
            return await handler(params)
        except Exception as e:
            logger.error("Linear action %s failed: %s", action, e)
            return ConnectorResponse(
                success=False,
                error=str(e),
                status_code=500,
            )

    # ═══════════════════════════════════════════════════════════════
    #  Issues
    # ═══════════════════════════════════════════════════════════════

    async def _create_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create a Linear issue."""
        title = params.get("title")
        team_id = params.get("team_id") or settings.LINEAR_TEAM_ID

        if not title:
            return ConnectorResponse(
                success=False,
                error="Missing required param: title",
                status_code=400,
            )
        if not team_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: team_id (or set LINEAR_TEAM_ID)",
                status_code=400,
            )

        issue = await self._linear_client.create_issue(  # type: ignore[attr-defined]
            team_id=team_id,
            title=title,
            description=params.get("description"),
            priority=params.get("priority"),
        )

        return ConnectorResponse(
            success=True,
            data=issue,
            status_code=200,
        )

    async def _update_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        """Update a Linear issue."""
        issue_id = params.get("issue_id")
        if not issue_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: issue_id",
                status_code=400,
            )

        issue = await self._linear_client.update_issue(  # type: ignore[attr-defined]
            issue_id=issue_id,
            title=params.get("title"),
            description=params.get("description"),
            state_id=params.get("state_id"),
            priority=params.get("priority"),
        )

        return ConnectorResponse(
            success=True,
            data=issue,
            status_code=200,
        )

    async def _get_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get a Linear issue by ID or identifier."""
        # Support lookup by identifier (e.g., "TEAM-123") or UUID ID
        if params.get("identifier"):
            issue = await self._linear_client.get_issue_by_identifier(  # type: ignore[attr-defined]
                params["identifier"]
            )
        elif params.get("issue_id"):
            issue = await self._linear_client.get_issue(params["issue_id"])  # type: ignore[attr-defined]
        else:
            return ConnectorResponse(
                success=False,
                error="Missing required param: issue_id or identifier",
                status_code=400,
            )

        if not issue:
            return ConnectorResponse(
                success=False,
                error="Issue not found",
                status_code=404,
            )

        return ConnectorResponse(
            success=True,
            data=issue,
            status_code=200,
        )

    async def _search_issues(self, params: dict[str, Any]) -> ConnectorResponse:
        """Search for Linear issues by exact identifier (e.g., TEAM-123)."""
        q = params.get("q") or params.get("query")
        if not q:
            return ConnectorResponse(
                success=False,
                error="Missing required param: q (search query)",
                status_code=400,
            )

        # First, try lookup by exact identifier (e.g., "TEAM-123")
        if "-" in q:
            issue = await self._linear_client.get_issue_by_identifier(q)  # type: ignore[attr-defined]
            if issue:
                return ConnectorResponse(
                    success=True,
                    data={"issues": [issue], "total": 1},
                    status_code=200,
                )

        return ConnectorResponse(
            success=True,
            data={"issues": [], "total": 0, "query": q},
            status_code=200,
        )

    async def _list_issues(self, params: dict[str, Any]) -> ConnectorResponse:
        """List Linear issues for the default team."""
        team_id = params.get("team_id") or settings.LINEAR_TEAM_ID
        if not team_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: team_id (or set LINEAR_TEAM_ID)",
                status_code=400,
            )

        # Use GraphQL query to list issues for a team
        try:
            client = self._linear_client
            query = """
            query TeamIssues($teamId: ID!, $first: Int!) {
                team(id: $teamId) {
                    issues(first: $first, orderBy: updatedAt) {
                        nodes {
                            id
                            title
                            identifier
                            url
                            state { id name }
                            priority
                            assignee { id name }
                            createdAt
                            updatedAt
                        }
                    }
                }
            }
            """
            result = await client._execute(  # type: ignore[attr-defined]
                query,
                {"teamId": team_id, "first": params.get("max_results", 20)},
            )
            issues = result.get("team", {}).get("issues", {}).get("nodes", [])

            return ConnectorResponse(
                success=True,
                data={"issues": issues, "total": len(issues)},
                status_code=200,
            )
        except Exception as e:
            return ConnectorResponse(
                success=False,
                error=f"Failed to list issues: {e}",
                status_code=500,
            )

    # ═══════════════════════════════════════════════════════════════
    #  Comments
    # ═══════════════════════════════════════════════════════════════

    async def _add_comment(self, params: dict[str, Any]) -> ConnectorResponse:
        """Add a comment to a Linear issue."""
        issue_id = params.get("issue_id")
        body = params.get("body")

        if not issue_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: issue_id",
                status_code=400,
            )
        if not body:
            return ConnectorResponse(
                success=False,
                error="Missing required param: body",
                status_code=400,
            )

        comment = await self._linear_client.add_comment(issue_id, body)  # type: ignore[attr-defined]

        return ConnectorResponse(
            success=True,
            data=comment,
            status_code=200,
        )

    # ═══════════════════════════════════════════════════════════════
    #  Teams
    # ═══════════════════════════════════════════════════════════════

    async def _list_teams(self, params: dict[str, Any]) -> ConnectorResponse:
        """List all Linear teams."""
        teams = await self._linear_client.get_teams()  # type: ignore[attr-defined]

        return ConnectorResponse(
            success=True,
            data={"teams": teams, "total": len(teams)},
            status_code=200,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics including Linear-specific info."""
        stats = super().get_stats()
        stats.update({"authenticated_team": self._authenticated_team})
        return stats
