"""
Browser Automation Tools — Cookie Manager.

cookie_manager → Inject, extract, and manage browser cookies for
    authentication persistence across sessions.
"""

from __future__ import annotations

import logging

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Input ─────────────────────────────────────────────────────────────


class CookieManagerInput(ToolInput):
    action: str = Field(
        ...,
        description=(
            "Action: 'get' (list all cookies for current page), "
            "'set' (add/replace cookies), "
            "'delete' (remove specific cookies by name), or "
            "'clear' (remove all cookies)"
        ),
    )
    cookies: list[dict] | None = Field(
        None,
        description=(
            "Cookie objects for 'set' action. Each dict should have at minimum "
            "'name' and 'value'. Optional: 'domain', 'path', 'httpOnly', "
            "'secure', 'sameSite', 'expires'."
        ),
    )
    names: list[str] | None = Field(
        None,
        description="Cookie names to delete (for 'delete' action)",
    )
    urls: list[str] | None = Field(
        None,
        description="URLs to scope cookie operations to (defaults to current page URL)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class CookieManagerTool(BaseTool):
    """Manage browser cookies for authentication persistence."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="cookie_manager",
            name="Cookie Manager",
            description=(
                "Inject or extract authentication cookies for browser sessions. "
                "Supports get, set, delete, and clear operations."
            ),
            category="browser-automation",
            input_schema=CookieManagerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["browser", "cookies", "authentication"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        from app.services.browser_manager import get_browser_manager

        try:
            validated = CookieManagerInput(**input_data)
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

        # Resolve URLs — default to current page URL(s)
        urls = validated.urls
        if not urls:
            try:
                urls = [session.page.url]
            except Exception:
                urls = []

        action = validated.action

        try:
            if action == "get":
                return await self._get_cookies(session, urls)
            elif action == "set":
                return await self._set_cookies(session, validated)
            elif action == "delete":
                return await self._delete_cookies(session, validated, urls)
            elif action == "clear":
                return await self._clear_cookies(session)
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"Unknown action: '{action}'. "
                        "Use 'get', 'set', 'delete', or 'clear'."
                    ),
                )
        except Exception as e:
            logger.exception("cookie_manager failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── get ─────────────────────────────────────────────────────

    async def _get_cookies(self, session, urls: list[str]) -> ToolResult:
        try:
            all_cookies = await session.context.cookies(urls)

            # Classify cookies
            auth_cookies = []
            session_cookies = []
            analytics_cookies = []

            auth_names = {
                "session",
                "token",
                "auth",
                "jwt",
                "sid",
                "csrf",
                "access_token",
                "refresh_token",
                "id_token",
                "bearer",
                "JSESSIONID",
                "PHPSESSID",
                "connect.sid",
            }

            for cookie in all_cookies:
                cookie_info = {
                    "name": cookie["name"],
                    "value": (
                        cookie["value"][:20] + "..."
                        if len(cookie.get("value", "")) > 20
                        else cookie.get("value", "")
                    ),
                    "domain": cookie.get("domain", ""),
                    "path": cookie.get("path", "/"),
                    "httpOnly": cookie.get("httpOnly", False),
                    "secure": cookie.get("secure", False),
                    "sameSite": cookie.get("sameSite", "Lax"),
                    "expires": (
                        cookie.get("expires", -1)
                        if cookie.get("expires", -1) != -1
                        else None
                    ),
                }
                name_lower = cookie["name"].lower()
                if any(auth in name_lower for auth in auth_names):
                    auth_cookies.append(cookie_info)
                elif "session" in name_lower or "sid" in name_lower:
                    session_cookies.append(cookie_info)
                elif any(
                    g in name_lower
                    for g in ("ga", "gtm", "analytics", "pixel", "track")
                ):
                    analytics_cookies.append(cookie_info)
                else:
                    session_cookies.append(cookie_info)

            session.touch()
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "action": "get",
                    "total": len(all_cookies),
                    "authentication": auth_cookies,
                    "other": session_cookies,
                    "analytics": analytics_cookies,
                    "urls": urls,
                },
            )
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Failed to get cookies: {e}",
            )

    # ── set ─────────────────────────────────────────────────────

    async def _set_cookies(self, session, validated: CookieManagerInput) -> ToolResult:
        if not validated.cookies:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="'cookies' list is required for 'set' action",
            )

        try:
            await session.context.add_cookies(validated.cookies)
            session.touch()

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "action": "set",
                    "cookies_set": len(validated.cookies),
                    "names": [c.get("name", "?") for c in validated.cookies],
                },
            )
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Failed to set cookies: {e}",
            )

    # ── delete ──────────────────────────────────────────────────

    async def _delete_cookies(
        self,
        session,
        validated: CookieManagerInput,
        urls: list[str],
    ) -> ToolResult:
        if not validated.names:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="'names' list is required for 'delete' action",
            )

        try:
            # Get existing cookies to find matching domains/paths
            existing = await session.context.cookies(urls)
            deleted_count = 0

            for name in validated.names:
                for cookie in existing:
                    if cookie["name"] == name:
                        # Delete by clearing value and setting expiry in past
                        await session.context.add_cookies(
                            [
                                {
                                    "name": name,
                                    "value": "",
                                    "domain": cookie.get("domain", ""),
                                    "path": cookie.get("path", "/"),
                                    "expires": 0,
                                }
                            ]
                        )
                        deleted_count += 1
                        break

            session.touch()
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "action": "delete",
                    "requested": len(validated.names),
                    "deleted": deleted_count,
                    "names": validated.names,
                },
            )
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Failed to delete cookies: {e}",
            )

    # ── clear ───────────────────────────────────────────────────

    async def _clear_cookies(self, session) -> ToolResult:
        try:
            await session.context.clear_cookies()
            session.touch()

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "action": "clear",
                    "detail": "All cookies cleared from browser context",
                },
            )
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Failed to clear cookies: {e}",
            )


# ── Register ──────────────────────────────────────────────────────────

register_tool(CookieManagerTool())
