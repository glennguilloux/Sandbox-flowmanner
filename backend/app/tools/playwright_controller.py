"""
Browser Automation Tools — Playwright Controller.

playwright_controller → Advanced browser control: execute JS, wait for
    elements, extract page content, and run action sequences.
"""

from __future__ import annotations

import json
import logging

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Input ─────────────────────────────────────────────────────────────


class PlaywrightControllerInput(ToolInput):
    action: str = Field(
        ...,
        description=(
            "Action: 'evaluate' (run JS in page), "
            "'get_content' (extract HTML/text), "
            "'wait' (wait for selector/text/time/navigation), or "
            "'execute_sequence' (run batch of low-level actions)"
        ),
    )
    script: str | None = Field(
        None,
        description="JavaScript to evaluate (for 'evaluate' action)",
    )
    selector: str | None = Field(
        None,
        description="CSS selector (for 'wait' action)",
    )
    wait_type: str | None = Field(
        None,
        description="Wait type: 'selector', 'text', 'timeout', 'navigation'",
    )
    text: str | None = Field(
        None,
        description="Text to wait for (for wait_type='text')",
    )
    timeout_ms: int = Field(
        5000,
        ge=100,
        le=60000,
        description="Max wait time in milliseconds",
    )
    extract_mode: str = Field(
        "html",
        description="Extraction mode for 'get_content': 'html', 'text', or 'inner_text'",
    )
    sequence: list[dict] | None = Field(
        None,
        description="List of action dicts for 'execute_sequence'",
    )
    screenshot_after: bool = Field(
        False,
        description="Take a screenshot after the action completes",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class PlaywrightControllerTool(BaseTool):
    """Advanced Playwright-level browser control: evaluate JS, wait, extract content."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="playwright_controller",
            name="Playwright Controller",
            description=(
                "Advanced browser control: execute JavaScript, wait for elements, "
                "extract page content, and run action sequences."
            ),
            category="browser-automation",
            input_schema=PlaywrightControllerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=[
                "browser",
                "playwright",
                "javascript",
                "extraction",
                "differentiator",
            ],
            requires_auth=True,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        from app.services.browser_manager import get_browser_manager
        from app.services.browser_service import get_browser_service

        try:
            validated = PlaywrightControllerInput(**input_data)
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

        manager = get_browser_manager()
        session = manager.get_user_session(str(user_id))
        if not session or not session.is_active():
            return ToolResult.error_result(
                tool_id=self.tool_id, error="No active browser session"
            )

        service = get_browser_service()
        action = validated.action

        try:
            if action == "evaluate":
                return await self._evaluate(session, validated)
            elif action == "get_content":
                return await self._get_content(session, validated)
            elif action == "wait":
                return await self._wait(session, validated)
            elif action == "execute_sequence":
                return await self._execute_sequence(
                    session, validated, str(user_id), service
                )
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"Unknown action: '{action}'. "
                        "Use 'evaluate', 'get_content', 'wait', or 'execute_sequence'."
                    ),
                )
        except Exception as e:
            logger.exception("playwright_controller failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── evaluate ────────────────────────────────────────────────

    async def _evaluate(
        self, session, validated: PlaywrightControllerInput
    ) -> ToolResult:
        if not validated.script:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="'script' parameter is required for 'evaluate' action",
            )

        try:
            result = await session.page.evaluate(validated.script)
            session.touch()

            response = {
                "action": "evaluate",
                "result": result,
                "result_type": type(result).__name__,
            }

            if validated.screenshot_after:
                import base64

                ss = await session.page.screenshot(type="png")
                response["screenshot"] = base64.b64encode(ss).decode("utf-8")

            return ToolResult.success_result(tool_id=self.tool_id, result=response)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"JavaScript evaluation failed: {e}",
            )

    # ── get_content ─────────────────────────────────────────────

    async def _get_content(
        self, session, validated: PlaywrightControllerInput
    ) -> ToolResult:
        try:
            page = session.page
            mode = validated.extract_mode

            if mode == "html":
                content = await page.content()
            elif mode == "text":
                content = await page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                )
            elif mode == "inner_text":
                if validated.selector:
                    content = await page.inner_text(validated.selector)
                else:
                    content = await page.inner_text("body")
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Unknown extract_mode: '{mode}'. Use 'html', 'text', or 'inner_text'.",
                )

            session.touch()

            # Truncate very large content
            max_chars = 50000
            truncated = len(content) > max_chars
            if truncated:
                content = content[:max_chars]

            response = {
                "action": "get_content",
                "mode": mode,
                "content": content,
                "content_length": len(content),
                "truncated": truncated,
                "selector": validated.selector,
            }

            if validated.screenshot_after:
                import base64

                ss = await session.page.screenshot(type="png")
                response["screenshot"] = base64.b64encode(ss).decode("utf-8")

            return ToolResult.success_result(tool_id=self.tool_id, result=response)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Content extraction failed: {e}",
            )

    # ── wait ────────────────────────────────────────────────────

    async def _wait(self, session, validated: PlaywrightControllerInput) -> ToolResult:
        wait_type = validated.wait_type or "timeout"
        page = session.page

        try:
            if wait_type == "selector":
                if not validated.selector:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error="'selector' is required for wait_type='selector'",
                    )
                await page.wait_for_selector(
                    validated.selector,
                    timeout=validated.timeout_ms,
                )
                detail = f"Selector '{validated.selector}' appeared"
            elif wait_type == "text":
                if not validated.text:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error="'text' is required for wait_type='text'",
                    )
                await page.wait_for_function(
                    f"document.body && document.body.innerText.includes({json.dumps(validated.text)})",
                    timeout=validated.timeout_ms,
                )
                detail = f"Text '{validated.text}' appeared"
            elif wait_type == "navigation":
                async with page.expect_navigation(timeout=validated.timeout_ms):
                    pass
                detail = "Navigation completed"
            elif wait_type == "timeout":
                await page.wait_for_timeout(validated.timeout_ms)
                detail = f"Waited {validated.timeout_ms}ms"
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Unknown wait_type: '{wait_type}'. Use 'selector', 'text', 'timeout', or 'navigation'.",
                )

            session.touch()
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "action": "wait",
                    "wait_type": wait_type,
                    "detail": detail,
                    "timeout_ms": validated.timeout_ms,
                },
            )
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Wait failed ({wait_type}): {e}",
            )

    # ── execute_sequence ────────────────────────────────────────

    async def _execute_sequence(
        self,
        session,
        validated: PlaywrightControllerInput,
        user_id: str,
        service,
    ) -> ToolResult:
        if not validated.sequence:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="'sequence' list is required for 'execute_sequence' action",
            )

        results = []
        for i, step in enumerate(validated.sequence):
            step_action = step.get("action", "")
            step_result = {"index": i, "action": step_action, "success": False}

            try:
                if step_action == "navigate":
                    url = step.get("url", "")
                    r = await service.navigate(user_id, url)
                    step_result.update(r)
                elif step_action == "click":
                    ref = step.get("ref", "")
                    r = await service.click(user_id, ref)
                    step_result.update(r)
                elif step_action == "type":
                    ref = step.get("ref", "")
                    text = step.get("text", "")
                    submit = step.get("submit", False)
                    r = await service.type_text(user_id, ref, text, submit)
                    step_result.update(r)
                elif step_action == "scroll":
                    x = step.get("x", 0)
                    y = step.get("y", 300)
                    r = await service.scroll(user_id, x, y)
                    step_result.update(r)
                elif step_action == "screenshot":
                    r = await service.screenshot(user_id)
                    step_result.update(r)
                elif step_action == "snapshot":
                    r = await service.snapshot(user_id)
                    step_result.update(r)
                elif step_action == "wait":
                    ms = step.get("timeout_ms", 1000)
                    await session.page.wait_for_timeout(ms)
                    step_result["success"] = True
                    step_result["detail"] = f"Waited {ms}ms"
                elif step_action == "evaluate":
                    js = step.get("script", "")
                    result = await session.page.evaluate(js)
                    step_result["success"] = True
                    step_result["result"] = result
                else:
                    step_result["error"] = f"Unknown step action: {step_action}"
            except Exception as e:
                step_result["error"] = str(e)

            results.append(step_result)
            if not step_result.get("success") and step.get("stop_on_error", True):
                break

        successes = sum(1 for r in results if r.get("success"))
        session.touch()

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "execute_sequence",
                "total_steps": len(results),
                "successful_steps": successes,
                "failed_steps": len(results) - successes,
                "results": results,
            },
        )


# ── Register ──────────────────────────────────────────────────────────

register_tool(PlaywrightControllerTool())
