"""
Jira Connector

Provides integration with Jira Cloud for issue tracking via the BaseConnector framework.
Wraps the JiraClient REST client to expose standard connector actions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

if TYPE_CHECKING:
    from app.services.jira.jira_client import JiraClient

logger = logging.getLogger(__name__)


class JiraConnector(BaseConnector):
    """Jira Cloud issue tracking connector."""

    CONNECTOR_TYPE = "jira"

    JIRA_RATE_LIMIT = RateLimitConfig(
        requests_per_second=5.0,
        requests_per_minute=100,
        requests_per_hour=5000,
        burst_size=10,
    )

    ACTIONS = [
        "list_projects",
        "get_project",
        "search_issues",
        "get_issue",
        "create_issue",
        "update_issue",
        "add_comment",
        "transition_issue",
        "list_boards",
        "list_sprints",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.atlassian.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.JIRA_RATE_LIMIT
        super().__init__(config)
        self._client: JiraClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.jira.jira_client import JiraClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            cloud_id = self.config.auth_config.get("cloud_id", "")
            if not token or not cloud_id:
                logger.debug("No Jira token or cloudId available — skipping credential validation")
                return True
            self._client = JiraClient(cloud_id=cloud_id, auth_token=token)
            user = await self._client.get_myself()
            return bool(user.get("accountId"))
        except Exception as e:
            logger.warning("Jira credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "list_projects": self._list_projects,
            "get_project": self._get_project,
            "search_issues": self._search_issues,
            "get_issue": self._get_issue,
            "create_issue": self._create_issue,
            "update_issue": self._update_issue,
            "add_comment": self._add_comment,
            "transition_issue": self._transition_issue,
            "list_boards": self._list_boards,
            "list_sprints": self._list_sprints,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Jira action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _list_projects(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        projects = await self._client.list_projects()
        return ConnectorResponse(success=True, data={"projects": projects}, status_code=200)

    async def _get_project(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        project_key = params.get("project_key")
        if not project_key:
            return ConnectorResponse(success=False, error="Missing: project_key", status_code=400)
        project = await self._client.get_project(project_key)
        return ConnectorResponse(success=True, data=project, status_code=200)

    async def _search_issues(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        jql = params.get("jql")
        if not jql:
            return ConnectorResponse(success=False, error="Missing: jql", status_code=400)
        result = await self._client.search_issues(
            jql=jql,
            fields=params.get("fields"),
            max_results=params.get("max_results", 50),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        issue_key = params.get("issue_key")
        if not issue_key:
            return ConnectorResponse(success=False, error="Missing: issue_key", status_code=400)
        issue = await self._client.get_issue(issue_key)
        return ConnectorResponse(success=True, data=issue, status_code=200)

    async def _create_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        project_key = params.get("project_key")
        summary = params.get("summary")
        if not project_key or not summary:
            return ConnectorResponse(success=False, error="Missing: project_key and summary", status_code=400)
        issue = await self._client.create_issue(
            project_key=project_key,
            summary=summary,
            issue_type=params.get("issue_type", "Task"),
            description=params.get("description"),
            priority=params.get("priority"),
            assignee_account_id=params.get("assignee_account_id"),
            labels=params.get("labels"),
        )
        return ConnectorResponse(success=True, data=issue, status_code=201)

    async def _update_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        issue_key = params.get("issue_key")
        fields = params.get("fields")
        if not issue_key or not fields:
            return ConnectorResponse(success=False, error="Missing: issue_key and fields", status_code=400)
        result = await self._client.update_issue(issue_key, fields)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _add_comment(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        issue_key = params.get("issue_key")
        body = params.get("body")
        if not issue_key or not body:
            return ConnectorResponse(success=False, error="Missing: issue_key and body", status_code=400)
        comment = await self._client.add_comment(issue_key, body)
        return ConnectorResponse(success=True, data=comment, status_code=201)

    async def _transition_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        issue_key = params.get("issue_key")
        transition_id = params.get("transition_id")
        if not issue_key or not transition_id:
            return ConnectorResponse(success=False, error="Missing: issue_key and transition_id", status_code=400)
        result = await self._client.transition_issue(issue_key, transition_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_boards(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        boards = await self._client.list_boards()
        return ConnectorResponse(success=True, data={"boards": boards}, status_code=200)

    async def _list_sprints(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "JiraClient not initialized — call connect() first"
        board_id = params.get("board_id")
        if not board_id:
            return ConnectorResponse(success=False, error="Missing: board_id", status_code=400)
        sprints = await self._client.list_sprints(int(board_id))
        return ConnectorResponse(success=True, data={"sprints": sprints}, status_code=200)
