"""
Linear GraphQL API Client

Async client for Linear's GraphQL API:
- Query issues, teams, states
- Create/update issues
- Add comments
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearError(Exception):
    """Linear API error."""

    pass


class LinearClient:
    """Async GraphQL client for Linear."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=LINEAR_API_URL,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query/mutation."""
        client = await self._get_client()
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            resp = await client.post("", json=payload)
            resp.raise_for_status()
            data = resp.json()

            if "errors" in data:
                error_msg = "; ".join(e.get("message", "Unknown") for e in data["errors"])
                raise LinearError(f"GraphQL errors: {error_msg}")

            return data.get("data", {})
        except httpx.HTTPStatusError as e:
            raise LinearError(f"HTTP {e.response.status_code}: {e.response.text[:500]}")
        except httpx.RequestError as e:
            raise LinearError(f"Request failed: {e}")

    # ── Teams ──────────────────────────────────────────────────

    async def get_teams(self) -> list[dict[str, Any]]:
        """List all teams."""
        query = """
        query Teams {
            teams {
                nodes { id name key }
            }
        }
        """
        result = await self._execute(query)
        return result.get("teams", {}).get("nodes", [])

    async def get_default_team_id(self) -> str | None:
        """Get the first team ID (fallback when LINEAR_TEAM_ID not set)."""
        teams = await self.get_teams()
        if teams:
            return teams[0]["id"]
        return None

    # ── Workflow States ────────────────────────────────────────

    async def get_workflow_states(self, team_id: str) -> list[dict[str, Any]]:
        """Get workflow states for a team."""
        query = """
        query WorkflowStates($teamId: ID!) {
            workflowStates(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name type }
            }
        }
        """
        result = await self._execute(query, {"teamId": team_id})
        return result.get("workflowStates", {}).get("nodes", [])

    # ── Issues ─────────────────────────────────────────────────

    async def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        """Get a single issue by ID."""
        query = """
        query Issue($id: String!) {
            issue(id: $id) {
                id
                title
                description
                identifier
                url
                state { id name type }
                priority
                assignee { id name }
                team { id name key }
                createdAt
                updatedAt
            }
        }
        """
        result = await self._execute(query, {"id": issue_id})
        return result.get("issue")

    async def create_issue(
        self,
        team_id: str,
        title: str,
        description: str | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        """Create a new issue. Returns {id, title, identifier, url, team {id, name}}."""
        query = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    title
                    identifier
                    url
                    state { id name }
                    team { id name }
                }
            }
        }
        """
        input_data: dict[str, Any] = {"teamId": team_id, "title": title}
        if description:
            input_data["description"] = description
        if priority is not None:
            input_data["priority"] = priority

        result = await self._execute(query, {"input": input_data})
        create_result = result.get("issueCreate", {})
        if not create_result.get("success"):
            raise LinearError(f"Failed to create issue: {create_result}")
        return create_result["issue"]

    async def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        description: str | None = None,
        state_id: str | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        """Update an issue. Returns updated issue data."""
        query = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    title
                    identifier
                    url
                    state { id name }
                }
            }
        }
        """
        input_data: dict[str, Any] = {}
        if title is not None:
            input_data["title"] = title
        if description is not None:
            input_data["description"] = description
        if state_id is not None:
            input_data["stateId"] = state_id
        if priority is not None:
            input_data["priority"] = priority

        if not input_data:
            return {}

        result = await self._execute(query, {"id": issue_id, "input": input_data})
        update_result = result.get("issueUpdate", {})
        if not update_result.get("success"):
            raise LinearError(f"Failed to update issue: {update_result}")
        return update_result["issue"]

    async def add_comment(self, issue_id: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        query = """
        mutation CreateComment($issueId: String!, $body: String!) {
            commentCreate(input: { issueId: $issueId, body: $body }) {
                success
                comment { id body createdAt }
            }
        }
        """
        result = await self._execute(query, {"issueId": issue_id, "body": body})
        comment_result = result.get("commentCreate", {})
        if not comment_result.get("success"):
            raise LinearError(f"Failed to add comment: {comment_result}")
        return comment_result["comment"]

    async def get_issue_by_identifier(self, identifier: str) -> dict[str, Any] | None:
        """Look up an issue by its identifier (e.g. 'TEAM-123')."""
        query = """
        query IssueByIdentifier($identifier: String!) {
            issueSearch(filter: { identifier: { eq: $identifier } }, first: 1) {
                nodes {
                    id
                    title
                    description
                    identifier
                    url
                    state { id name type }
                    priority
                }
            }
        }
        """
        result = await self._execute(query, {"identifier": identifier})
        nodes = result.get("issueSearch", {}).get("nodes", [])
        return nodes[0] if nodes else None

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton
_linear_client: LinearClient | None = None


def get_linear_client() -> LinearClient | None:
    """Get or create the Linear client singleton. Returns None if API key not configured."""
    global _linear_client
    if _linear_client is None:
        from app.config import settings

        api_key = settings.LINEAR_API_KEY
        if not api_key:
            logger.warning("LINEAR_API_KEY not configured — Linear integration disabled")
            return None
        _linear_client = LinearClient(api_key)
    return _linear_client
