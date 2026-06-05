"""
Web Scraping Tools — Dynamic JS Renderer.

dynamic_js_renderer → Render SPA/JavaScript-heavy sites to extract dynamic content.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class DynamicJsRendererInput(ToolInput):
    url: str = Field(..., description="URL of the JavaScript-heavy page to render")
    wait_for_selector: str | None = Field(
        None,
        description="CSS selector to wait for before extracting content (e.g., '#app', '.content')",
    )
    wait_time_ms: int = Field(
        3000,
        ge=500,
        le=30000,
        description="Additional wait time in milliseconds after page load",
    )
    extract_text: bool = Field(
        True,
        description="Extract visible text content after rendering",
    )
    extract_html: bool = Field(
        False,
        description="Extract the full rendered HTML",
    )
    screenshot: bool = Field(
        False,
        description="Take a screenshot of the rendered page (returns Base64 PNG)",
    )
    viewport_width: int = Field(1280, ge=320, le=3840)
    viewport_height: int = Field(800, ge=240, le=2160)
    timeout_ms: int = Field(30000, ge=5000, le=120000)


class DynamicJsRendererTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="dynamic_js_renderer",
            name="Dynamic JS Renderer",
            description="Render SPA/JavaScript-heavy sites to extract dynamic content",
            category="web-scraping",
            input_schema=DynamicJsRendererInput.schema_extra(),
            tags=["javascript", "spa", "render", "playwright", "dynamic"],
            requires_auth=False,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = DynamicJsRendererInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.url.strip():
            return ToolResult.error_result(tool_id=self.tool_id, error="URL is empty")

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={
                        "width": validated.viewport_width,
                        "height": validated.viewport_height,
                    },
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()

                try:
                    await page.goto(
                        validated.url,
                        wait_until="networkidle",
                        timeout=validated.timeout_ms,
                    )

                    # Wait for specific selector
                    if validated.wait_for_selector:
                        await page.wait_for_selector(
                            validated.wait_for_selector,
                            timeout=validated.timeout_ms,
                        )

                    # Extra wait for any animations/async rendering
                    if validated.wait_time_ms > 0:
                        await page.wait_for_timeout(validated.wait_time_ms)

                    result: dict[str, Any] = {
                        "url": validated.url,
                        "title": await page.title(),
                        "final_url": page.url,
                    }

                    if validated.extract_text:
                        text = await page.evaluate(
                            """
                            () => {
                                // Remove script and style content
                                const clone = document.body.cloneNode(true);
                                clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                                return clone.innerText || '';
                            }
                        """
                        )
                        result["text"] = text.strip()
                        result["text_length"] = len(text.strip())

                    if validated.extract_html:
                        html = await page.content()
                        result["html"] = html
                        result["html_length"] = len(html)

                    if validated.screenshot:
                        import base64

                        screenshot_bytes = await page.screenshot(full_page=True)
                        result["screenshot_base64"] = base64.b64encode(
                            screenshot_bytes
                        ).decode()

                finally:
                    await browser.close()

            return ToolResult.success_result(tool_id=self.tool_id, result=result)

        except ImportError:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Playwright is not installed. Install with: pip install playwright && playwright install chromium",
            )
        except Exception as e:
            logger.exception("dynamic_js_renderer failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(DynamicJsRendererTool())
