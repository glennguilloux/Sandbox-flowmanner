"""
Sentry Connector

Provides integration with Sentry for error monitoring via the BaseConnector framework.
Wraps the SentryClient REST client to expose standard connector actions.
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
    from app.services.sentry.sentry_client import SentryClient

logger = logging.getLogger(__name__)


class SentryConnector(BaseConnector):
    """Sentry error monitoring connector."""

    CONNECTOR_TYPE = "sentry"

    SENTRY_RATE_LIMIT = RateLimitConfig(
        requests_per_second=5.0,
        requests_per_minute=200,
        requests_per_hour=5000,
        burst_size=10,
    )

    ACTIONS = [
        "list_organizations",
        "list_projects",
        "list_issues",
        "get_issue",
        "get_latest_event",
        "resolve_issue",
        "ignore_issue",
        "list_releases",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://sentry.io"
        config.auth_type = config.auth_type or AuthType.BEARER_TOKEN
        config.rate_limit = config.rate_limit or self.SENTRY_RATE_LIMIT
        super().__init__(config)
        self._client: SentryClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.sentry.sentry_client import SentryClient

            # Support both "token" (non-OAuth factory) and "access_token" (OAuth bridge)
            token = self.config.auth_config.get("token", "") or self.config.auth_config.get("access_token", "")
            if not token:
                logger.debug("No Sentry token available — skipping credential validation")
                return True
            base_url = self.config.base_url or "https://sentry.io"
            self._client = SentryClient(base_url=base_url, auth_token=token)
            orgs = await self._client.list_organizations()
            return len(orgs) > 0
        except Exception as e:
            logger.warning("Sentry credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "list_organizations": self._list_organizations,
            "list_projects": self._list_projects,
            "list_issues": self._list_issues,
            "get_issue": self._get_issue,
            "get_latest_event": self._get_latest_event,
            "resolve_issue": self._resolve_issue,
            "ignore_issue": self._ignore_issue,
            "list_releases": self._list_releases,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Sentry action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _list_organizations(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "SentryClient not initialized — call connect() first"
        orgs = await self._client.list_organizations()
        return ConnectorResponse(success=True, data={"organizations": orgs}, status_code=200)

    async def _list_projects(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "SentryClient not initialized — call connect() first"
        org_slug = params.get("org_slug")
        if not org_slug:
            return ConnectorResponse(success=False, error="Missing: org_slug", status_code=400)
        projects = await self._client.list_projects(org_slug)
        return ConnectorResponse(success=True, data={"projects": projects}, status_code=200)

    async def _list_issues(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "SentryClient not initialized — call connect() first"
        org_slug = params.get("org_slug")
        if not org_slug:
            return ConnectorResponse(success=False, error="Missing: org_slug", status_code=400)
        issues = await self._client.list_issues(
            org_slug=org_slug,
            project_slug=params.get("project_slug"),
            query=params.get("query", ""),
            sort=params.get("sort", "date"),
            limit=params.get("limit", 25),
        )
        return ConnectorResponse(success=True, data={"issues": issues}, status_code=200)

    async def _get_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "SentryClient not initialized — call connect() first"
        issue_id = params.get("issue_id")
        if not issue_id:
            return ConnectorResponse(success=False, error="Missing: issue_id", status_code=400)
        issue = await self._client.get_issue(issue_id)
        return ConnectorResponse(success=True, data=issue, status_code=200)

    async def _get_latest_event(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "SentryClient not initialized — call connect() first"
        issue_id = params.get("issue_id")
        if not issue_id:
            return ConnectorResponse(success=False, error="Missing: issue_id", status_code=400)
        event = await self._client.get_latest_event(issue_id)
        return ConnectorResponse(success=True, data=event, status_code=200)

    async def _resolve_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "SentryClient not initialized — call connect() first"
        issue_id = params.get("issue_id")
        if not issue_id:
            return ConnectorResponse(success=False, error="Missing: issue_id", status_code=400)
        result = await self._client.resolve_issue(issue_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _ignore_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "SentryClient not initialized — call connect() first"
        issue_id = params.get("issue_id")
        if not issue_id:
            return ConnectorResponse(success=False, error="Missing: issue_id", status_code=400)
        result = await self._client.ignore_issue(issue_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_releases(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "SentryClient not initialized — call connect() first"
        org_slug = params.get("org_slug")
        if not org_slug:
            return ConnectorResponse(success=False, error="Missing: org_slug", status_code=400)
        releases = await self._client.list_releases(org_slug, params.get("project_slug"))
        return ConnectorResponse(success=True, data={"releases": releases}, status_code=200)
