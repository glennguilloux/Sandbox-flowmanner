"""
API & SaaS Integration Tools — Linear Tasks.

linear_tasks → Create issues, update statuses, and query project boards in Linear.
"""

from __future__ import annotations

import logging
import os

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearTasksInput(ToolInput):
    action: str = Field(
        ...,
        description="Action: 'list_issues', 'get_issue', 'create_issue', 'update_issue', "
        "'list_teams', 'search_issues', 'get_workflow_states'",
    )
    team_id: str | None = Field(None, description="Linear team ID")
    issue_id: str | None = Field(None, description="Linear issue ID")
    title: str | None = Field(None, description="Issue title (for create/update)")
    description: str | None = Field(None, description="Issue description")
    state_id: str | None = Field(None, description="Workflow state ID (for update)")
    assignee_id: str | None = Field(None, description="Assignee user ID")
    priority: int | None = Field(
        None,
        ge=0,
        le=4,
        description="Priority: 0=no priority, 1=urgent, 2=high, 3=medium, 4=low",
    )
    query: str | None = Field(None, description="Search query for issues")
    limit: int = Field(25, ge=1, le=250)
    api_key: str | None = Field(
        None, description="Linear API key (uses LINEAR_API_KEY env var if omitted)"
    )


class LinearTasksTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="linear_tasks",
            name="Linear Tasks",
            description="Create issues, update statuses, and query project boards in Linear",
            category="api-integrations",
            input_schema=LinearTasksInput.schema_extra(),
            tags=["linear", "issues", "project-management", "tasks", "integration"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def _graphql(
        self, client: httpx.AsyncClient, query: str, variables: dict | None = None
    ) -> dict:
        """Execute a GraphQL query against the Linear API."""
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        r = await client.post(LINEAR_API_URL, json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"Linear API HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        if "errors" in data:
            errors = [e.get("message", str(e)) for e in data.get("errors", [])]
            raise RuntimeError(f"Linear API errors: {'; '.join(errors[:3])}")
        return data.get("data", {})

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = LinearTasksInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        api_key = validated.api_key or os.getenv("LINEAR_API_KEY", "")
        if not api_key:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No Linear API key. Set LINEAR_API_KEY or pass api_key.",
            )

        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }
        action = validated.action.lower().strip()

        try:
            async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
                if action == "list_issues":
                    return await self._list_issues(client, validated)
                elif action == "get_issue":
                    return await self._get_issue(client, validated)
                elif action == "create_issue":
                    return await self._create_issue(client, validated)
                elif action == "update_issue":
                    return await self._update_issue(client, validated)
                elif action == "list_teams":
                    return await self._list_teams(client, validated)
                elif action == "search_issues":
                    return await self._search_issues(client, validated)
                elif action == "get_workflow_states":
                    return await self._get_workflow_states(client, validated)
                else:
                    return ToolResult.error_result(
                        tool_id=self.tool_id, error=f"Unknown action: {action}"
                    )
        except RuntimeError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        except Exception as e:
            logger.exception("linear_tasks failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _list_issues(self, client, v) -> ToolResult:
        team_filter = (
            f'(filter: {{ team: {{ id: {{ eq: "{v.team_id}" }} }} }})'
            if v.team_id
            else ""
        )
        query = f"""
        query {{
          issues(first: {v.limit}{team_filter}) {{
            nodes {{
              id
              identifier
              title
              description
              state {{ id name type }}
              priority
              assignee {{ id name }}
              team {{ id name }}
              createdAt
              url
            }}
          }}
        }}
        """
        data = await self._graphql(client, query)
        issues = [
            {
                "id": i["id"],
                "identifier": i["identifier"],
                "title": i["title"],
                "state": i.get("state", {}).get("name"),
                "priority": i.get("priority"),
                "assignee": (
                    i.get("assignee", {}).get("name") if i.get("assignee") else None
                ),
                "team": i.get("team", {}).get("name"),
                "url": i.get("url"),
                "created_at": i.get("createdAt"),
            }
            for i in data.get("issues", {}).get("nodes", [])
        ]
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "list_issues",
                "count": len(issues),
                "issues": issues,
            },
        )

    async def _get_issue(self, client, v) -> ToolResult:
        if not v.issue_id:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="issue_id required"
            )
        query = f"""
        query {{
          issue(id: "{v.issue_id}") {{
            id identifier title description
            state {{ id name type }}
            priority
            assignee {{ id name }}
            team {{ id name }}
            createdAt updatedAt url
            parent {{ id title }}
            children {{ nodes {{ id title }} }}
          }}
        }}
        """
        data = await self._graphql(client, query)
        issue = data.get("issue")
        if not issue:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Issue {v.issue_id} not found"
            )
        return ToolResult.success_result(
            tool_id=self.tool_id, result={"action": "get_issue", "issue": issue}
        )

    async def _create_issue(self, client, v) -> ToolResult:
        if not v.team_id or not v.title:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="team_id and title required"
            )
        escaped_title = v.title.replace('"', '\\"')
        input_fields = f"""teamId: "{v.team_id}", title: "{escaped_title}" """
        if v.description:
            escaped_desc = v.description.replace('"', '\\"').replace("\n", "\\n")
            input_fields += f""", description: "{escaped_desc}" """
        if v.state_id:
            input_fields += f""", stateId: "{v.state_id}" """
        if v.assignee_id:
            input_fields += f""", assigneeId: "{v.assignee_id}" """
        if v.priority is not None:
            input_fields += f", priority: {v.priority}"
        query = f"""
        mutation {{
          issueCreate(input: {{ {input_fields} }}) {{
            success
            issue {{
              id identifier title url
              state {{ id name }}
              team {{ id name }}
            }}
          }}
        }}
        """
        data = await self._graphql(client, query)
        result = data.get("issueCreate", {})
        if not result.get("success"):
            return ToolResult.error_result(
                tool_id=self.tool_id, error="Failed to create issue"
            )
        i = result["issue"]
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "create_issue",
                "issue": {
                    "id": i["id"],
                    "identifier": i["identifier"],
                    "title": i["title"],
                    "url": i["url"],
                },
            },
        )

    async def _update_issue(self, client, v) -> ToolResult:
        if not v.issue_id:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="issue_id required"
            )
        input_fields = f'id: "{v.issue_id}"'
        if v.title:
            escaped_title = v.title.replace('"', '\\"')
            input_fields += f""", title: "{escaped_title}" """
        if v.description:
            escaped_desc = v.description.replace('"', '\\"').replace("\n", "\\n")
            input_fields += f""", description: "{escaped_desc}" """
        if v.state_id:
            input_fields += f""", stateId: "{v.state_id}" """
        if v.assignee_id:
            input_fields += f""", assigneeId: "{v.assignee_id}" """
        if v.priority is not None:
            input_fields += f", priority: {v.priority}"
        query = f"""
        mutation {{
          issueUpdate(input: {{ {input_fields} }}) {{
            success
            issue {{
              id identifier title
              state {{ id name }}
            }}
          }}
        }}
        """
        data = await self._graphql(client, query)
        result = data.get("issueUpdate", {})
        if not result.get("success"):
            return ToolResult.error_result(
                tool_id=self.tool_id, error="Failed to update issue"
            )
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "update_issue",
                "ok": True,
                "issue": result["issue"],
            },
        )

    async def _list_teams(self, client, v) -> ToolResult:
        query = """
        query {
          teams(first: 50) {
            nodes { id name key description }
          }
        }
        """
        data = await self._graphql(client, query)
        teams = data.get("teams", {}).get("nodes", [])
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "list_teams",
                "count": len(teams),
                "teams": teams,
            },
        )

    async def _search_issues(self, client, v) -> ToolResult:
        if not v.query:
            return ToolResult.error_result(tool_id=self.tool_id, error="query required")
        escaped_query = v.query.replace('"', '\\"')
        query = f"""
        query {{
          searchIssues(query: "{escaped_query}", first: {v.limit}) {{
            nodes {{
              id identifier title
              state {{ name }}
              team {{ name }}
              priority url
            }}
          }}
        }}
        """
        data = await self._graphql(client, query)
        issues = data.get("searchIssues", {}).get("nodes", [])
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "search_issues",
                "query": v.query,
                "count": len(issues),
                "issues": issues,
            },
        )

    async def _get_workflow_states(self, client, v) -> ToolResult:
        team_filter = (
            f'(filter: {{ team: {{ id: {{ eq: "{v.team_id}" }} }} }})'
            if v.team_id
            else ""
        )
        query = f"""
        query {{
          workflowStates(first: 100{team_filter}) {{
            nodes {{ id name type color position }}
          }}
        }}
        """
        data = await self._graphql(client, query)
        states = data.get("workflowStates", {}).get("nodes", [])
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "get_workflow_states",
                "count": len(states),
                "states": states,
            },
        )


register_tool(LinearTasksTool())
