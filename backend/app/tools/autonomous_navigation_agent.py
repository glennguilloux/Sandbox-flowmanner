"""
Browser Automation Tools — Autonomous Navigation Agent.

autonomous_navigation_agent → Self-healing LLM-powered browser agent that
    finds and interacts with elements even when the DOM changes.
"""

from __future__ import annotations

import logging

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Input ─────────────────────────────────────────────────────────────


class AutonomousNavigationAgentInput(ToolInput):
    task: str = Field(
        ...,
        description="Natural language description of the web task to accomplish",
    )
    model: str | None = Field(
        None,
        description="LLM model to use for agent reasoning (defaults to deepseek-chat)",
    )
    temperature: float | None = Field(
        None,
        ge=0.0,
        le=2.0,
        description="LLM temperature for agent reasoning",
    )
    max_tokens: int | None = Field(
        None,
        ge=100,
        le=8000,
        description="Max tokens per LLM call for agent reasoning",
    )
    system_prompt: str | None = Field(
        None,
        description="Custom system prompt to override the default agent prompt",
    )
    byok_key: str | None = Field(
        None,
        description="Bring-your-own-key override for the LLM API key",
    )
    byok_base_url: str | None = Field(
        None,
        description="Base URL override for the LLM API endpoint",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class AutonomousNavigationAgentTool(BaseTool):
    """LLM-powered browser agent that navigates and interacts with web pages autonomously.

    Uses the BrowserAgent under the hood to loop through: snapshot → LLM decides →
    execute action → repeat until done. Self-healing via coordinate fallback when
    element references go stale.
    """

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="autonomous_navigation_agent",
            name="Autonomous Navigation Agent",
            description=(
                "Self-healing LLM-powered browser agent that finds and interacts "
                "with elements even when the DOM changes. Give it a natural language "
                "task and it navigates, clicks, types, and scrolls to accomplish it."
            ),
            category="browser-automation",
            input_schema=AutonomousNavigationAgentInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["browser", "agent", "llm", "autonomous", "self-healing"],
            requires_auth=True,
            timeout_seconds=120,  # Longer timeout for agent loops
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        from app.services.browser_agent import BrowserAgent

        try:
            validated = AutonomousNavigationAgentInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        context = input_data.get("context")
        if not context:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="No context provided"
            )

        user_id = context.get("user_id")
        if not user_id:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="No user_id in context"
            )

        uid = str(user_id)

        try:
            agent = BrowserAgent(uid)
            result = await agent.run(
                message=validated.task,
                model=validated.model,
                temperature=validated.temperature,
                max_tokens=validated.max_tokens,
                system_prompt=validated.system_prompt,
                byok_key=validated.byok_key,
                byok_base_url=validated.byok_base_url,
            )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "action": "run",
                    "task": validated.task,
                    "response": result.get("response", ""),
                    "actions_taken": len(result.get("actions", [])),
                    "actions": result.get("actions", []),
                    "final_url": result.get("final_url"),
                    "screenshot": result.get("screenshot"),
                },
            )
        except Exception as e:
            logger.exception("autonomous_navigation_agent failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── Register ──────────────────────────────────────────────────────────

register_tool(AutonomousNavigationAgentTool())
