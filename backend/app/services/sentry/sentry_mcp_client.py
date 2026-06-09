"""
Sentry MCP Client

Client for interacting with Sentry MCP Server and Seer AI
for automated error analysis and fix recommendations.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class IssueSeverity(str, Enum):
    """Sentry issue severity levels"""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


class IssueStatus(str, Enum):
    """Sentry issue status"""

    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    IGNORED = "ignored"
    ASSIGNED = "assigned"


@dataclass
class SeerAnalysis:
    """Seer AI analysis result"""

    issue_id: str
    root_cause: str
    confidence: float  # 0.0 to 1.0
    suggested_fix: str
    affected_components: list[str]
    similar_issues: list[str]
    analysis_timestamp: datetime = field(default_factory=datetime.utcnow)
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "suggested_fix": self.suggested_fix,
            "affected_components": self.affected_components,
            "similar_issues": self.similar_issues,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
        }


@dataclass
class FixRecommendation:
    """AI-generated fix recommendation"""

    issue_id: str
    title: str
    description: str
    code_changes: list[dict[str, Any]]  # List of file changes
    confidence: float
    auto_applicable: bool  # True if confidence >= 0.95
    requires_approval: bool  # True if confidence < 0.95
    estimated_impact: str  # "low", "medium", "high"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "title": self.title,
            "description": self.description,
            "code_changes": self.code_changes,
            "confidence": self.confidence,
            "auto_applicable": self.auto_applicable,
            "requires_approval": self.requires_approval,
            "estimated_impact": self.estimated_impact,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SentryIssue:
    """Sentry issue data"""

    id: str
    short_id: str
    title: str
    culprit: str
    permalink: str
    first_seen: datetime
    last_seen: datetime
    count: int
    user_count: int
    severity: IssueSeverity
    status: IssueStatus
    project: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "short_id": self.short_id,
            "title": self.title,
            "culprit": self.culprit,
            "permalink": self.permalink,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "count": self.count,
            "user_count": self.user_count,
            "severity": self.severity.value,
            "status": self.status.value,
            "project": self.project,
        }


class SentryMCPClient:
    """
    Client for Sentry MCP Server with Seer AI integration.

    Provides:
    - Error capture with workflow context
    - Seer AI root cause analysis
    - Fix recommendations
    - Similar issue search
    - Issue management
    """

    def __init__(
        self,
        mcp_url: str = "https://mcp.sentry.dev/mcp",
        org_slug: str | None = None,
        project_slug: str | None = None,
        api_token: str | None = None,
        confidence_threshold: float = 0.95,
    ):
        self.mcp_url = mcp_url.rstrip("/")
        self.org_slug = org_slug or os.getenv("SENTRY_ORG_SLUG")
        self.project_slug = project_slug or os.getenv("SENTRY_PROJECT_SLUG")
        self.api_token = api_token or os.getenv("SENTRY_API_TOKEN")
        self.confidence_threshold = confidence_threshold
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            headers = {
                "Content-Type": "application/json",
            }
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _mcp_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Make an MCP JSON-RPC request.

        Args:
            method: MCP method name
            params: Method parameters

        Returns:
            Response result
        """
        session = await self._get_session()

        payload = {
            "jsonrpc": "2.0",
            "id": datetime.now(UTC).timestamp(),
            "method": method,
            "params": params or {},
        }

        try:
            async with session.post(self.mcp_url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error('MCP request failed: %s - %s', response.status, error_text)
                    raise Exception(f"MCP request failed: {response.status}")

                data = await response.json()

                if "error" in data:
                    logger.error('MCP error: %s', data['error'])
                    raise Exception(f"MCP error: {data['error']}")

                return data.get("result", {})

        except aiohttp.ClientError as e:
            logger.error('MCP request error: %s', e)
            raise

    async def capture_execution_error(
        self,
        workflow_id: str,
        agent_id: str,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Capture an error from workflow execution.

        Args:
            workflow_id: ID of the workflow
            agent_id: ID of the agent
            error: The exception that occurred
            context: Additional context

        Returns:
            Sentry event ID
        """
        import traceback

        params = {
            "message": str(error),
            "level": "error",
            "tags": {
                "workflow_id": workflow_id,
                "agent_id": agent_id,
                "error_type": type(error).__name__,
            },
            "extra": {
                "stack_trace": traceback.format_exc(),
                "context": context or {},
            },
            "project": self.project_slug,
        }

        try:
            result = await self._mcp_request("sentry/capture_event", params)
            event_id = result.get("event_id")
            logger.info('Captured execution error: %s', event_id)
            return event_id
        except Exception as e:
            logger.error('Failed to capture execution error: %s', e)
            # Return a placeholder - the local Sentry SDK will handle it
            return ""

    async def analyze_with_seer(self, issue_id: str) -> SeerAnalysis | None:
        """
        Trigger Seer AI root cause analysis for an issue.

        Args:
            issue_id: Sentry issue ID

        Returns:
            SeerAnalysis with root cause and suggestions
        """
        params = {
            "issue_id": issue_id,
            "org_slug": self.org_slug,
            "project_slug": self.project_slug,
        }

        try:
            result = await self._mcp_request("sentry/seer_analyze", params)

            if not result:
                logger.warning('No Seer analysis result for issue %s', issue_id)
                return None

            analysis = SeerAnalysis(
                issue_id=issue_id,
                root_cause=result.get("root_cause", "Unknown"),
                confidence=result.get("confidence", 0.0),
                suggested_fix=result.get("suggested_fix", ""),
                affected_components=result.get("affected_components", []),
                similar_issues=result.get("similar_issues", []),
                raw_response=result,
            )

            logger.info('Seer analysis complete for %s: confidence=%s', issue_id, analysis.confidence)
            return analysis

        except Exception as e:
            logger.error('Seer analysis failed: %s', e)
            return None

    async def get_fix_recommendation(self, issue_id: str) -> FixRecommendation | None:
        """
        Get AI-generated fix recommendation for an issue.

        Args:
            issue_id: Sentry issue ID

        Returns:
            FixRecommendation with code changes
        """
        params = {
            "issue_id": issue_id,
            "org_slug": self.org_slug,
            "project_slug": self.project_slug,
        }

        try:
            result = await self._mcp_request("sentry/seer_fix", params)

            if not result:
                logger.warning('No fix recommendation for issue %s', issue_id)
                return None

            confidence = result.get("confidence", 0.0)

            recommendation = FixRecommendation(
                issue_id=issue_id,
                title=result.get("title", "Fix Recommendation"),
                description=result.get("description", ""),
                code_changes=result.get("code_changes", []),
                confidence=confidence,
                auto_applicable=confidence >= self.confidence_threshold,
                requires_approval=confidence < self.confidence_threshold,
                estimated_impact=result.get("estimated_impact", "medium"),
            )

            logger.info('Fix recommendation for %s: auto_applicable=%s', issue_id, recommendation.auto_applicable)
            return recommendation

        except Exception as e:
            logger.error('Fix recommendation failed: %s', e)
            return None

    async def search_similar_issues(
        self, fingerprint: str | None = None, query: str | None = None, limit: int = 10
    ) -> list[SentryIssue]:
        """
        Search for similar issues across projects.

        Args:
            fingerprint: Issue fingerprint to match
            query: Search query
            limit: Maximum results

        Returns:
            List of similar issues
        """
        params = {
            "org_slug": self.org_slug,
            "limit": limit,
        }

        if fingerprint:
            params["fingerprint"] = fingerprint
        if query:
            params["query"] = query

        try:
            result = await self._mcp_request("sentry/search_issues", params)

            issues = []
            for item in result.get("issues", []):
                try:
                    issue = SentryIssue(
                        id=item["id"],
                        short_id=item.get("short_id", ""),
                        title=item.get("title", "Unknown"),
                        culprit=item.get("culprit", ""),
                        permalink=item.get("permalink", ""),
                        first_seen=datetime.fromisoformat(item["first_seen"]),
                        last_seen=datetime.fromisoformat(item["last_seen"]),
                        count=item.get("count", 0),
                        user_count=item.get("user_count", 0),
                        severity=IssueSeverity(item.get("level", "error")),
                        status=IssueStatus(item.get("status", "unresolved")),
                        project=item.get("project", {}),
                    )
                    issues.append(issue)
                except Exception as e:
                    logger.warning('Failed to parse issue: %s', e)
                    continue

            logger.info('Found %s similar issues', len(issues))
            return issues

        except Exception as e:
            logger.error('Issue search failed: %s', e)
            return []

    async def get_issue(self, issue_id: str) -> SentryIssue | None:
        """Get details of a specific issue."""
        params = {
            "issue_id": issue_id,
            "org_slug": self.org_slug,
        }

        try:
            result = await self._mcp_request("sentry/get_issue", params)

            if not result:
                return None

            return SentryIssue(
                id=result["id"],
                short_id=result.get("short_id", ""),
                title=result.get("title", "Unknown"),
                culprit=result.get("culprit", ""),
                permalink=result.get("permalink", ""),
                first_seen=datetime.fromisoformat(result["first_seen"]),
                last_seen=datetime.fromisoformat(result["last_seen"]),
                count=result.get("count", 0),
                user_count=result.get("user_count", 0),
                severity=IssueSeverity(result.get("level", "error")),
                status=IssueStatus(result.get("status", "unresolved")),
                project=result.get("project", {}),
            )

        except Exception as e:
            logger.error('Failed to get issue: %s', e)
            return None

    async def resolve_issue(self, issue_id: str) -> bool:
        """Mark an issue as resolved."""
        params = {
            "issue_id": issue_id,
            "org_slug": self.org_slug,
            "status": "resolved",
        }

        try:
            await self._mcp_request("sentry/update_issue", params)
            logger.info('Resolved issue %s', issue_id)
            return True
        except Exception as e:
            logger.error('Failed to resolve issue: %s', e)
            return False

    async def get_project_issues(
        self, query: str | None = None, limit: int = 100
    ) -> list[SentryIssue]:
        """Get all issues for the project."""
        return await self.search_similar_issues(query=query, limit=limit)


# Singleton instance
_sentry_mcp_client: SentryMCPClient | None = None


def get_sentry_mcp_client() -> SentryMCPClient:
    """Get or create the Sentry MCP client singleton."""
    global _sentry_mcp_client
    if _sentry_mcp_client is None:
        _sentry_mcp_client = SentryMCPClient()
    return _sentry_mcp_client
