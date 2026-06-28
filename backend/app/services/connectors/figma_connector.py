"""
Figma Connector

Provides integration with Figma for design file access via the BaseConnector framework.
Wraps the FigmaClient REST client to expose standard connector actions.
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
    from app.services.figma.figma_client import FigmaClient

logger = logging.getLogger(__name__)


class FigmaConnector(BaseConnector):
    """Figma design tool connector."""

    CONNECTOR_TYPE = "figma"

    FIGMA_RATE_LIMIT = RateLimitConfig(
        requests_per_second=5.0,
        requests_per_minute=120,
        requests_per_hour=5000,
        burst_size=10,
    )

    ACTIONS = [
        "get_me",
        "get_file",
        "get_file_nodes",
        "list_comments",
        "post_comment",
        "get_file_versions",
        "list_team_projects",
        "list_project_files",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.figma.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.FIGMA_RATE_LIMIT
        super().__init__(config)
        self._client: FigmaClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.figma.figma_client import FigmaClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No Figma token available — skipping credential validation")
                return True
            self._client = FigmaClient(auth_token=token)
            user = await self._client.get_me()
            return bool(user.get("id"))
        except Exception as e:
            logger.warning("Figma credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "get_file": self._get_file,
            "get_file_nodes": self._get_file_nodes,
            "list_comments": self._list_comments,
            "post_comment": self._post_comment,
            "get_file_versions": self._get_file_versions,
            "list_team_projects": self._list_team_projects,
            "list_project_files": self._list_project_files,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Figma action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "FigmaClient not initialized — call connect() first"
        user = await self._client.get_me()
        return ConnectorResponse(success=True, data=user, status_code=200)

    async def _get_file(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "FigmaClient not initialized — call connect() first"
        file_key = params.get("file_key")
        if not file_key:
            return ConnectorResponse(success=False, error="Missing: file_key", status_code=400)
        file_data = await self._client.get_file(file_key)
        return ConnectorResponse(success=True, data=file_data, status_code=200)

    async def _get_file_nodes(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "FigmaClient not initialized — call connect() first"
        file_key = params.get("file_key")
        node_ids = params.get("node_ids")
        if not file_key or not node_ids:
            return ConnectorResponse(success=False, error="Missing: file_key and node_ids", status_code=400)
        nodes = await self._client.get_file_nodes(file_key, node_ids if isinstance(node_ids, list) else [node_ids])
        return ConnectorResponse(success=True, data=nodes, status_code=200)

    async def _list_comments(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "FigmaClient not initialized — call connect() first"
        file_key = params.get("file_key")
        if not file_key:
            return ConnectorResponse(success=False, error="Missing: file_key", status_code=400)
        comments = await self._client.list_comments(file_key)
        return ConnectorResponse(success=True, data={"comments": comments}, status_code=200)

    async def _post_comment(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "FigmaClient not initialized — call connect() first"
        file_key = params.get("file_key")
        message = params.get("message")
        if not file_key or not message:
            return ConnectorResponse(success=False, error="Missing: file_key and message", status_code=400)
        comment = await self._client.post_comment(file_key, message, client_meta=params.get("client_meta"))
        return ConnectorResponse(success=True, data=comment, status_code=201)

    async def _get_file_versions(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "FigmaClient not initialized — call connect() first"
        file_key = params.get("file_key")
        if not file_key:
            return ConnectorResponse(success=False, error="Missing: file_key", status_code=400)
        versions = await self._client.get_file_versions(file_key)
        return ConnectorResponse(success=True, data={"versions": versions}, status_code=200)

    async def _list_team_projects(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "FigmaClient not initialized — call connect() first"
        team_id = params.get("team_id")
        if not team_id:
            return ConnectorResponse(success=False, error="Missing: team_id", status_code=400)
        projects = await self._client.list_team_projects(team_id)
        return ConnectorResponse(success=True, data={"projects": projects}, status_code=200)

    async def _list_project_files(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "FigmaClient not initialized — call connect() first"
        project_id = params.get("project_id")
        if not project_id:
            return ConnectorResponse(success=False, error="Missing: project_id", status_code=400)
        files = await self._client.list_project_files(project_id)
        return ConnectorResponse(success=True, data={"files": files}, status_code=200)
