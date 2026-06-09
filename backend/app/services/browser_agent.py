"""
Browser Agent — LLM-powered browser automation agent.

Replaces the simple keyword router with an AI agent that:
1. Takes a natural language request
2. Captures current page state (elements with refs)
3. Calls an LLM to decide the next action
4. Executes browser actions (navigate, click, type, scroll, snapshot)
5. Loops until task complete or max iterations reached

H1.4 Hardening:
- Per-iteration logging (iteration_idx, url, action, tokens_used)
- Hard time budget per iteration (default 30s)
- Hard total cost budget (default $0.50)
- Screenshot artefacts persisted to user storage namespace
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

from app.services.browser_service import get_browser_service

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15
PER_ITERATION_TIMEOUT_SECONDS = 30
MAX_TOTAL_COST_USD = float(os.getenv("BROWSER_AGENT_MAX_COST_USD", "0.50"))
BROWSER_LLM_INPUT_COST_PER_1M = float(
    os.getenv("BROWSER_LLM_INPUT_COST_PER_1M", "0.14")
)
BROWSER_LLM_OUTPUT_COST_PER_1M = float(
    os.getenv("BROWSER_LLM_OUTPUT_COST_PER_1M", "0.28")
)
# Use actual per-call cost from LLM response when available;
# fall back to this estimate when the response doesn't report token counts.
ESTIMATED_COST_PER_LLM_CALL = 0.005

SYSTEM_PROMPT = """You are a browser automation agent. Help users accomplish tasks on the web.

You have these tools:
- navigate(url) — go to a URL
- snapshot() — get list of clickable/typeable elements on the page (with ref numbers like e1, e2)
- click(ref) — click an element by its ref number (e.g., click("e5"))
- type(ref, text) — type text into an input field and submit with Enter
- scroll(y) — scroll the page up (negative y) or down (positive y)
- done(message) — finish the task with a summary for the user

RULES:
1. Start by navigating to the website the user wants
2. Take a snapshot to see what's on the page
3. Use click/type/scroll to interact — use EXACT ref numbers from the snapshot
4. When done or stuck after 3 attempts, call done() with what you achieved
5. NEVER invent URLs — only use URLs the user specified or search engine results you've actually navigated to
6. Respond with exactly ONE JSON object per turn, no extra text

Valid JSON formats:
{"action": "navigate", "url": "https://example.com"}
{"action": "snapshot"}
{"action": "click", "ref": "e5"}
{"action": "type", "ref": "e3", "text": "search term"}
{"action": "scroll", "y": 300}
{"action": "done", "message": "Task completed successfully"}

Respond ONLY with valid JSON. No markdown, no explanation, no backticks."""


class BrowserAgent:
    """LLM-powered browser agent for complex web tasks."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.service = get_browser_service()
        self.actions_taken: list[dict[str, str]] = []
        self.iteration = 0
        self.total_tokens_used = 0
        self.total_cost_estimate = 0.0
        self.iteration_metrics: list[dict[str, Any]] = []

    async def run(
        self,
        message: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
        byok_key: str | None = None,
        byok_base_url: str | None = None,
    ) -> dict[str, Any]:
        """Run the agent loop and return final response dict."""
        from app.services.llm_router import ModelRouter

        router = ModelRouter()

        effective_system = system_prompt or SYSTEM_PROMPT
        messages: list[dict[str, str]] = [
            {"role": "system", "content": effective_system},
            {"role": "user", "content": message},
        ]

        for self.iteration in range(MAX_ITERATIONS):
            iter_start = time.time()
            logger.info(
                "[BrowserAgent %s] Iteration %d/%d (tokens: %d, cost_est: $%.4f)",
                self.user_id,
                self.iteration + 1,
                MAX_ITERATIONS,
                self.total_tokens_used,
                self.total_cost_estimate,
            )

            # Enforce total cost budget
            if self.total_cost_estimate >= MAX_TOTAL_COST_USD:
                logger.warning(
                    "[BrowserAgent %s] Cost budget exhausted: $%.4f >= $%.2f",
                    self.user_id,
                    self.total_cost_estimate,
                    MAX_TOTAL_COST_USD,
                )
                return await self._done(
                    "Cost budget reached. I've done as much as I could within budget."
                )

            # Touch session to prevent timeout during this iteration
            self._touch_session()

            # Append current page context
            page_ctx = await self._get_page_context()
            current_url = self._extract_url_from_context(page_ctx)
            if page_ctx:
                messages.append(
                    {"role": "user", "content": "[Page context] " + page_ctx}
                )

            # Call LLM with per-iteration timeout
            route_kwargs = {
                "messages": messages,
                "model_preference": model or "deepseek-chat",
                "max_tokens": max_tokens or 1000,
                "temperature": temperature if temperature is not None else 0.3,
            }
            if byok_key:
                route_kwargs["byok_key_override"] = byok_key
            if byok_base_url:
                route_kwargs["byok_base_url_override"] = byok_base_url

            try:
                result = await asyncio.wait_for(
                    router.route_request(**route_kwargs),
                    timeout=PER_ITERATION_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning(
                    "[BrowserAgent %s] Iteration %d timed out after %ds",
                    self.user_id,
                    self.iteration + 1,
                    PER_ITERATION_TIMEOUT_SECONDS,
                )
                self.iteration_metrics.append(
                    {
                        "iteration_idx": self.iteration,
                        "url": current_url,
                        "action": "timeout",
                        "tokens_used": 0,
                        "duration_ms": int((time.time() - iter_start) * 1000),
                        "screenshot_path": None,
                        "error": f"Timed out after {PER_ITERATION_TIMEOUT_SECONDS}s",
                    }
                )
                return await self._done(
                    "A step took too long. I'll stop here — please try again."
                )

            llm_content = (
                result.get("content", "")
                if isinstance(result, dict)
                else result.content
            )
            iter_tokens = 0
            if isinstance(result, dict):
                iter_tokens = result.get("usage", {}).get("total_tokens", 0)
                if iter_tokens == 0:
                    cost_info = result.get("cost", {})
                    iter_tokens = cost_info.get("input_tokens", 0) + cost_info.get(
                        "output_tokens", 0
                    )
            self.total_tokens_used += iter_tokens
            # Use actual token cost from LLM response when available
            actual_cost = 0.0
            if isinstance(result, dict):
                cost_info = result.get("cost", {})
                if cost_info:
                    prompt_tok = cost_info.get("input_tokens", 0)
                    completion_tok = cost_info.get("output_tokens", 0)
                    # Pricing from env vars (default: DeepSeek $0.14/M input, $0.28/M output)
                    actual_cost = (
                        prompt_tok / 1_000_000
                    ) * BROWSER_LLM_INPUT_COST_PER_1M + (
                        completion_tok / 1_000_000
                    ) * BROWSER_LLM_OUTPUT_COST_PER_1M
            if actual_cost <= 0:
                actual_cost = ESTIMATED_COST_PER_LLM_CALL
            self.total_cost_estimate += actual_cost

            llm_content = (
                result.get("content", "")
                if isinstance(result, dict)
                else result.content
            )
            if not llm_content or not result.get("success", False):
                self.iteration_metrics.append(
                    {
                        "iteration_idx": self.iteration,
                        "url": current_url,
                        "action": "llm_failure",
                        "tokens_used": iter_tokens,
                        "duration_ms": int((time.time() - iter_start) * 1000),
                        "screenshot_path": None,
                        "error": "LLM returned empty or failed response",
                    }
                )
                return await self._done("I encountered a problem. Please try again.")

            # Parse action
            action = self._parse_action(llm_content)
            if not action:
                messages.append({"role": "assistant", "content": llm_content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Invalid JSON. Respond with valid JSON only — no markdown, no backticks.",
                    }
                )
                continue

            action_type = action.get("action", "")

            if action_type == "done":
                ss_path = await self._screenshot_and_persist(current_url)
                self.iteration_metrics.append(
                    {
                        "iteration_idx": self.iteration,
                        "url": current_url,
                        "action": "done",
                        "tokens_used": iter_tokens,
                        "duration_ms": int((time.time() - iter_start) * 1000),
                        "screenshot_path": ss_path,
                    }
                )
                return await self._done(
                    action.get("message", "Task completed."), screenshot_path=ss_path
                )

            elif action_type == "navigate":
                url = action.get("url", "").rstrip("']})\".,;:!? ")
                if not url:
                    return await self._done("I need a URL to navigate to.")
                if not url.startswith("http"):
                    url = "https://" + url
                nav = await self.service.navigate(self.user_id, url)
                self._record("browser_navigate", f"Navigated to {url}")
                ss_path = await self._screenshot_and_persist(url)
                self.iteration_metrics.append(
                    {
                        "iteration_idx": self.iteration,
                        "url": url,
                        "action": "navigate",
                        "tokens_used": iter_tokens,
                        "duration_ms": int((time.time() - iter_start) * 1000),
                        "screenshot_path": ss_path,
                    }
                )
                messages.append({"role": "assistant", "content": json.dumps(action)})
                if nav.get("success"):
                    messages.append(
                        {
                            "role": "user",
                            "content": f"OK. URL: {nav.get('url')}. Title: {nav.get('title')}",
                        }
                    )
                else:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Navigation failed: {nav.get('error')}",
                        }
                    )

            elif action_type == "snapshot":
                ss = await self.service.snapshot(self.user_id)
                if ss.get("success"):
                    count = len(ss.get("elements", []))
                    self._record("browser_snapshot", f"Found {count} elements")
                    ss_path = await self._screenshot_and_persist(
                        ss.get("url", current_url)
                    )
                    self.iteration_metrics.append(
                        {
                            "iteration_idx": self.iteration,
                            "url": ss.get("url", current_url),
                            "action": "snapshot",
                            "tokens_used": iter_tokens,
                            "duration_ms": int((time.time() - iter_start) * 1000),
                            "element_count": count,
                            "screenshot_path": ss_path,
                        }
                    )
                    elements_text = self._format_elements(ss.get("elements", []))
                    messages.append(
                        {"role": "assistant", "content": json.dumps(action)}
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": f'Page: {ss.get("url")} — "{ss.get("title")}". Elements:\n{elements_text}',
                        }
                    )
                else:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Snapshot failed: {ss.get('error')}",
                        }
                    )

            elif action_type == "click":
                ref = action.get("ref", "")
                if not ref:
                    messages.append(
                        {"role": "user", "content": "click needs 'ref' parameter"}
                    )
                    continue
                if ref.startswith("e"):
                    ref = ref[1:]
                click = await self.service.click(self.user_id, ref)
                self._record("browser_click", f"Clicked element e{ref}")
                self.iteration_metrics.append(
                    {
                        "iteration_idx": self.iteration,
                        "url": current_url,
                        "action": "click",
                        "tokens_used": iter_tokens,
                        "duration_ms": int((time.time() - iter_start) * 1000),
                        "ref": f"e{ref}",
                        "screenshot_path": None,
                    }
                )
                messages.append({"role": "assistant", "content": json.dumps(action)})
                if click.get("success"):
                    healed = " (healed via coordinates)" if click.get("healed") else ""
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Clicked e{ref}{healed}. Consider taking a new snapshot if page changed.",
                        }
                    )
                else:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Click failed: {click.get('error')}. Try snapshot to refresh elements.",
                        }
                    )

            elif action_type == "type":
                ref = action.get("ref", "")
                text = action.get("text", "")
                if not ref or not text:
                    messages.append(
                        {
                            "role": "user",
                            "content": "type needs 'ref' and 'text' params",
                        }
                    )
                    continue
                if ref.startswith("e"):
                    ref = ref[1:]
                typed = await self.service.type_text(
                    self.user_id, ref, text, submit=True
                )
                self._record("browser_type", f"Typed '{text}' into e{ref}")
                self.iteration_metrics.append(
                    {
                        "iteration_idx": self.iteration,
                        "url": current_url,
                        "action": "type",
                        "tokens_used": iter_tokens,
                        "duration_ms": int((time.time() - iter_start) * 1000),
                        "ref": f"e{ref}",
                        "screenshot_path": None,
                    }
                )
                messages.append({"role": "assistant", "content": json.dumps(action)})
                if typed.get("success"):
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Typed '{text}' and submitted. Take a snapshot to see results.",
                        }
                    )
                else:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Type failed: {typed.get('error')}",
                        }
                    )

            elif action_type == "scroll":
                y = action.get("y", 300)
                await self.service.scroll(self.user_id, y=y)
                self._record("browser_scroll", f"Scrolled by {y}px")
                self.iteration_metrics.append(
                    {
                        "iteration_idx": self.iteration,
                        "url": current_url,
                        "action": "scroll",
                        "tokens_used": iter_tokens,
                        "duration_ms": int((time.time() - iter_start) * 1000),
                        "scroll_y": y,
                        "screenshot_path": None,
                    }
                )
                messages.append({"role": "assistant", "content": json.dumps(action)})
                messages.append({"role": "user", "content": f"Scrolled {y}px."})

            else:
                self.iteration_metrics.append(
                    {
                        "iteration_idx": self.iteration,
                        "url": current_url,
                        "action": "unknown",
                        "tokens_used": iter_tokens,
                        "duration_ms": int((time.time() - iter_start) * 1000),
                        "raw_action": action_type,
                        "screenshot_path": None,
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"Unknown action: {action_type}. Use navigate, snapshot, click, type, scroll, or done.",
                    }
                )

        # Max iterations reached
        return await self._done(
            "I've done as much as I could. Let me know if you need anything else."
        )

    def _extract_url_from_context(self, page_ctx: str) -> str | None:
        """Extract current URL from page context string."""
        if not page_ctx:
            return None
        match = re.search(r"Currently on:\s*(\S+)", page_ctx)
        return match.group(1) if match else None

    async def _get_page_context(self) -> str:
        from app.services.browser_manager import get_browser_manager

        mgr = get_browser_manager()
        session = mgr.get_user_session(self.user_id)
        if session and session.is_active():
            try:
                url = session.page.url
                title = await session.page.title()
                return f"Currently on: {url}\nPage title: {title}"
            except Exception as e:
                logger.debug(
                    "browser_agent_page_context_failed",
                    user_id=self.user_id,
                    error=str(e),
                )
        return ""

    def _touch_session(self) -> None:
        """Reset the session inactivity timer so it doesn't time out during agent work."""
        from app.services.browser_manager import get_browser_manager

        mgr = get_browser_manager()
        session = mgr.get_user_session(self.user_id)
        if session and session.is_active():
            session.touch_user_interaction()

    def _format_elements(self, elements: list[dict]) -> str:
        lines = []
        for el in elements[:30]:  # max 30 elements to limit context
            ref = el.get("ref", "?")
            tag = el.get("tag", "")
            text = (el.get("text") or "")[:60]
            role = el.get("role", "")
            bbox = el.get("bbox")
            label = f" [{role}]" if role and role != "none" else ""
            coord = (
                f" at ({bbox['center_x']:.0f},{bbox['center_y']:.0f})" if bbox else ""
            )
            lines.append(f"  e{ref}: <{tag}>{label} {text}{coord}")
        return "\n".join(lines) if lines else "No interactive elements found."

    def _parse_action(self, llm_response: str) -> dict | None:
        try:
            return json.loads(llm_response.strip())
        except json.JSONDecodeError:
            match = re.search(r"\{[^{}]*\}", llm_response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError as e:
                    logger.debug(
                        "browser_agent_json_extraction_failed",
                        snippet=llm_response[:100],
                        error=str(e),
                    )
        logger.warning('Could not parse LLM response: %s', llm_response[:200])
        return None

    def _record(self, tool: str, result: str) -> None:
        self.actions_taken.append({"tool": tool, "result": result})

    async def _screenshot_and_persist(
        self, current_url: str | None = None
    ) -> str | None:
        """Take a screenshot and persist it to user storage namespace (H1.4).

        Returns the filesystem path on success, or None on failure.
        Screenshots are captured on key milestones (navigate, snapshot, done)
        to keep the iteration log self-documenting without overwhelming storage.
        """
        try:
            ss = await self.service.screenshot(self.user_id)
            if ss.get("success") and ss.get("screenshot"):
                return self._persist_screenshot(ss["screenshot"])
        except Exception as e:
            logger.debug(
                "[BrowserAgent %s] Screenshot capture skipped: %s", self.user_id, e
            )
        return None

    async def _done(
        self, message: str, screenshot_path: str | None = None
    ) -> dict[str, Any]:
        from app.services.browser_manager import get_browser_manager

        mgr = get_browser_manager()
        session = mgr.get_user_session(self.user_id)

        final_url = None
        screenshot_data = None

        if session and session.is_active():
            try:
                final_url = session.page.url
                # Only take a screenshot if one wasn't already captured upstream
                if screenshot_path is None:
                    ss = await self.service.screenshot(self.user_id)
                    if ss.get("success"):
                        screenshot_data = ss.get("screenshot")
                        screenshot_path = self._persist_screenshot(screenshot_data)
            except Exception as e:
                logger.debug(
                    "browser_agent_final_screenshot_failed",
                    user_id=self.user_id,
                    error=str(e),
                )

        return {
            "response": message,
            "actions": self.actions_taken,
            "final_url": final_url,
            "screenshot": screenshot_data,
            "screenshot_path": screenshot_path,
            "success": True,
            "metrics": {
                "iterations": self.iteration + 1,
                "max_iterations": MAX_ITERATIONS,
                "total_tokens_used": self.total_tokens_used,
                "total_cost_estimate": self.total_cost_estimate,
                "iteration_details": self.iteration_metrics,
            },
        }

    def _persist_screenshot(self, screenshot_data: str) -> str | None:
        """Persist screenshot to user storage namespace (H1.4).

        Saves the base64 screenshot to a timestamped file under
        the user's browser screenshots directory.
        """
        if not screenshot_data:
            return None
        try:
            storage_dir = os.path.join(
                "/opt/flowmanner/static",
                "browser_screenshots",
                str(self.user_id),
            )
            os.makedirs(storage_dir, exist_ok=True)
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"browser_{timestamp}_{self.iteration}.png"
            filepath = os.path.join(storage_dir, filename)

            # Decode base64 and write to disk
            if "," in screenshot_data:
                # Strip data:image/png;base64, prefix
                screenshot_data = screenshot_data.split(",", 1)[1]
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(screenshot_data))

            logger.info(
                "[BrowserAgent %s] Screenshot saved: %s",
                self.user_id,
                filepath,
            )
            return filepath
        except Exception as e:
            logger.warning(
                "[BrowserAgent %s] Failed to persist screenshot: %s",
                self.user_id,
                e,
            )
            return None


async def run_browser_agent(
    user_id: str,
    message: str,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    system_prompt: str | None = None,
    byok_key: str | None = None,
    byok_base_url: str | None = None,
) -> dict[str, Any]:
    """Convenience function to run the browser agent."""
    agent = BrowserAgent(user_id)
    return await agent.run(
        message=message,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
        byok_key=byok_key,
        byok_base_url=byok_base_url,
    )
