"""
GitLab Connector

Provides integration with GitLab API for:
- Projects (list, get)
- Merge requests (list, get, create, merge, approve)
- Issues (list, get, create, add note)
- Pipelines (list, get, retry, cancel)
- Deployments (list)
- Releases (list, create)
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
    from app.services.gitlab.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


class GitLabConnector(BaseConnector):
    """GitLab DevOps platform connector."""

    CONNECTOR_TYPE = "gitlab"

    GITLAB_RATE_LIMIT = RateLimitConfig(
        requests_per_second=30.0,  # 2,000/min per IP
        requests_per_minute=1000,
        requests_per_hour=30000,
        burst_size=50,
    )

    ACTIONS = [
        "get_me",
        "list_projects",
        "get_project",
        "list_merge_requests",
        "get_merge_request",
        "create_merge_request",
        "merge_merge_request",
        "approve_merge_request",
        "list_issues",
        "get_issue",
        "create_issue",
        "add_issue_note",
        "list_pipelines",
        "retry_pipeline",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://gitlab.com/api/v4"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.GITLAB_RATE_LIMIT
        super().__init__(config)
        self._client: GitLabClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.gitlab.gitlab_client import GitLabClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No GitLab token available — skipping credential validation")
                return True
            # Support self-hosted instances via base_url in auth_config
            base_url = self.config.auth_config.get("base_url", "https://gitlab.com/api/v4")
            self._client = GitLabClient(auth_token=token, base_url=base_url)
            me = await self._client.get_me()
            return bool(me.get("id"))
        except Exception as e:
            logger.warning("GitLab credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "list_projects": self._list_projects,
            "get_project": self._get_project,
            "list_merge_requests": self._list_merge_requests,
            "get_merge_request": self._get_merge_request,
            "create_merge_request": self._create_merge_request,
            "merge_merge_request": self._merge_merge_request,
            "approve_merge_request": self._approve_merge_request,
            "list_issues": self._list_issues,
            "get_issue": self._get_issue,
            "create_issue": self._create_issue,
            "add_issue_note": self._add_issue_note,
            "list_pipelines": self._list_pipelines,
            "retry_pipeline": self._retry_pipeline,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("GitLab action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        result = await self._client.get_me()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_projects(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        result = await self._client.list_projects(
            membership=params.get("membership", True),
            page=params.get("page", 1),
            per_page=params.get("per_page", 20),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_project(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        if not project_id:
            return ConnectorResponse(success=False, error="Missing: project_id", status_code=400)
        result = await self._client.get_project(project_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_merge_requests(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        if not project_id:
            return ConnectorResponse(success=False, error="Missing: project_id", status_code=400)
        result = await self._client.list_merge_requests(
            project_id,
            state=params.get("state", "opened"),
            page=params.get("page", 1),
            per_page=params.get("per_page", 20),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_merge_request(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        mr_iid = params.get("mr_iid")
        if not project_id or mr_iid is None:
            return ConnectorResponse(success=False, error="Missing: project_id and mr_iid", status_code=400)
        result = await self._client.get_merge_request(project_id, int(mr_iid))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_merge_request(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        source_branch = params.get("source_branch")
        target_branch = params.get("target_branch")
        title = params.get("title")
        if not project_id or not source_branch or not target_branch or not title:
            return ConnectorResponse(
                success=False,
                error="Missing: project_id, source_branch, target_branch, and title",
                status_code=400,
            )
        result = await self._client.create_merge_request(
            project_id,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            description=params.get("description"),
        )
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _merge_merge_request(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        mr_iid = params.get("mr_iid")
        if not project_id or mr_iid is None:
            return ConnectorResponse(success=False, error="Missing: project_id and mr_iid", status_code=400)
        result = await self._client.merge_merge_request(project_id, int(mr_iid))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _approve_merge_request(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        mr_iid = params.get("mr_iid")
        if not project_id or mr_iid is None:
            return ConnectorResponse(success=False, error="Missing: project_id and mr_iid", status_code=400)
        result = await self._client.approve_merge_request(project_id, int(mr_iid))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_issues(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        if not project_id:
            return ConnectorResponse(success=False, error="Missing: project_id", status_code=400)
        result = await self._client.list_issues(
            project_id,
            state=params.get("state", "opened"),
            page=params.get("page", 1),
            per_page=params.get("per_page", 20),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        issue_iid = params.get("issue_iid")
        if not project_id or issue_iid is None:
            return ConnectorResponse(success=False, error="Missing: project_id and issue_iid", status_code=400)
        result = await self._client.get_issue(project_id, int(issue_iid))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        title = params.get("title")
        if not project_id or not title:
            return ConnectorResponse(success=False, error="Missing: project_id and title", status_code=400)
        result = await self._client.create_issue(
            project_id,
            title=title,
            description=params.get("description"),
            assignee_ids=params.get("assignee_ids"),
            labels=params.get("labels"),
        )
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _add_issue_note(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        issue_iid = params.get("issue_iid")
        body = params.get("body")
        if not project_id or issue_iid is None or not body:
            return ConnectorResponse(success=False, error="Missing: project_id, issue_iid, and body", status_code=400)
        result = await self._client.add_issue_note(project_id, int(issue_iid), body)
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _list_pipelines(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        if not project_id:
            return ConnectorResponse(success=False, error="Missing: project_id", status_code=400)
        result = await self._client.list_pipelines(
            project_id,
            status=params.get("status"),
            page=params.get("page", 1),
            per_page=params.get("per_page", 20),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _retry_pipeline(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "GitLabClient not initialized — call connect() first"
        project_id = params.get("project_id")
        pipeline_id = params.get("pipeline_id")
        if not project_id or pipeline_id is None:
            return ConnectorResponse(success=False, error="Missing: project_id and pipeline_id", status_code=400)
        result = await self._client.retry_pipeline(project_id, int(pipeline_id))
        return ConnectorResponse(success=True, data=result, status_code=200)
