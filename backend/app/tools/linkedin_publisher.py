"""
Social Media & Content Publishing Tools — LinkedIn Publisher.

linkedin_publisher → Post updates and articles to LinkedIn personal
    or company pages using the LinkedIn REST API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import (
    BaseTool,
    ToolInput,
    ToolMetadata,
    ToolResult,
    is_placeholder,
    register_tool,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_ORG_ID = os.getenv("LINKEDIN_ORG_ID", "")
LINKEDIN_USER_ID = os.getenv("LINKEDIN_USER_ID", "urn:li:person:me")
LINKEDIN_TIMEOUT = int(os.getenv("LINKEDIN_TIMEOUT", "30"))

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"

LINKEDIN_MAX_UPDATE_LENGTH = 3000
LINKEDIN_MAX_ARTICLE_LENGTH = 125000


# ── Input ─────────────────────────────────────────────────────────────


class LinkedinPublisherInput(ToolInput):
    message: str = Field(
        ...,
        description="Content to post. Up to 3000 chars for updates, 125K for articles.",
    )
    visibility: str = Field(
        "PUBLIC",
        description="Post visibility: 'PUBLIC', 'CONNECTIONS', or 'LOGGED_IN'",
    )
    post_type: str = Field(
        "update",
        description="Type: 'update' (short post) or 'article' (long-form with title)",
    )
    article_title: str | None = Field(
        None,
        description="Title for article posts (required when post_type='article')",
    )
    article_description: str | None = Field(
        None,
        description="Short description/summary for article posts",
    )
    post_as_organization: bool = Field(
        False,
        description="Post as organization page instead of personal profile",
    )
    share_url: str | None = Field(
        None,
        description="URL to share as an attachment",
    )
    share_url_title: str | None = Field(
        None,
        description="Title for the shared URL attachment",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class LinkedinPublisherTool(BaseTool):
    """Post updates and articles to LinkedIn using the REST API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="linkedin_publisher",
            name="LinkedIn Publisher",
            description=(
                "Post updates and articles to LinkedIn personal or company pages. "
                "Supports text updates, URL sharing, and long-form articles. "
                "Requires LinkedIn API access token with appropriate scopes."
            ),
            category="social-media-content-publishing",
            input_schema=LinkedinPublisherInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["social", "linkedin", "publish", "article"],
            requires_auth=True,
            timeout_seconds=LINKEDIN_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = LinkedinPublisherInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.message.strip():
            return ToolResult.error_result(
                tool_id=self.tool_id, error="Message must not be empty"
            )

        valid_vis = ("PUBLIC", "CONNECTIONS", "LOGGED_IN")
        if validated.visibility not in valid_vis:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Invalid visibility: '{validated.visibility}'. Use: {', '.join(valid_vis)}",
            )

        if validated.post_type == "article" and not validated.article_title:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="article_title is required when post_type='article'",
            )

        max_len = (
            LINKEDIN_MAX_ARTICLE_LENGTH
            if validated.post_type == "article"
            else LINKEDIN_MAX_UPDATE_LENGTH
        )
        if len(validated.message) > max_len:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Content too long: {len(validated.message)} chars (max {max_len})",
            )

        try:
            result = await self._publish(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("linkedin_publisher failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _publish(self, validated: LinkedinPublisherInput) -> dict[str, Any]:
        """Post to LinkedIn API."""
        if not LINKEDIN_ACCESS_TOKEN:
            return {
                "status": "not_configured",
                "message": (
                    "LinkedIn access token not configured. Set LINKEDIN_ACCESS_TOKEN "
                    "environment variable. You'll need an app with rw_organization_admin "
                    "or w_member_social scope. Preview:"
                ),
                "preview": {
                    "type": validated.post_type,
                    "visibility": validated.visibility,
                    "length": len(validated.message),
                    "truncated": validated.message[:200]
                    + ("..." if len(validated.message) > 200 else ""),
                    "has_attachment": bool(validated.share_url),
                },
            }

        if is_placeholder(LINKEDIN_ACCESS_TOKEN):
            return {
                "status": "not_configured",
                "message": (
                    "LINKEDIN_ACCESS_TOKEN is a placeholder. "
                    "Replace placeholder in .env with a real LinkedIn access token. "
                    "Requires an app with rw_organization_admin or w_member_social scope. "
                    "Preview:"
                ),
                "preview": {
                    "type": validated.post_type,
                    "visibility": validated.visibility,
                    "length": len(validated.message),
                    "truncated": validated.message[:200]
                    + ("..." if len(validated.message) > 200 else ""),
                    "has_attachment": bool(validated.share_url),
                },
            }

        if validated.post_type == "article":
            return await self._publish_article(validated)
        return await self._publish_update(validated)

    async def _publish_update(
        self, validated: LinkedinPublisherInput
    ) -> dict[str, Any]:
        """Create a share/update post on LinkedIn."""
        author = self._resolve_author(validated.post_as_organization)
        headers = self._auth_headers()

        body: dict[str, Any] = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": validated.message},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": validated.visibility
            },
        }

        # Add URL attachment if provided
        if validated.share_url:
            body["specificContent"]["com.linkedin.ugc.ShareContent"][
                "shareMediaCategory"
            ] = "ARTICLE"
            body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                {
                    "status": "READY",
                    "originalUrl": validated.share_url,
                    "title": {"text": validated.share_url_title or validated.share_url},
                }
            ]

        async with httpx.AsyncClient(timeout=LINKEDIN_TIMEOUT) as client:
            resp = await client.post(
                f"{LINKEDIN_API_BASE}/ugcPosts", headers=headers, json=body
            )
            return self._handle_response(resp, "update")

    async def _publish_article(
        self, validated: LinkedinPublisherInput
    ) -> dict[str, Any]:
        """Create a long-form article on LinkedIn."""
        author = self._resolve_author(validated.post_as_organization)
        headers = self._auth_headers()

        body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": validated.article_description
                        or validated.article_title
                        or ""
                    },
                    "shareMediaCategory": "ARTICLE",
                    "media": [
                        {
                            "status": "READY",
                            "description": {
                                "text": validated.article_description or ""
                            },
                            "title": {"text": validated.article_title or "Untitled"},
                        }
                    ],
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": validated.visibility
            },
        }

        # NOTE: LinkedIn long-form articles use a separate Articles API endpoint
        # (not UGC Posts). This implementation uses the UGC Posts endpoint with
        # ARTICLE media category as a pragmatic approach for shorter articles.
        # For full long-form article support, integrate with LinkedIn's Articles API.

        async with httpx.AsyncClient(timeout=LINKEDIN_TIMEOUT) as client:
            resp = await client.post(
                f"{LINKEDIN_API_BASE}/ugcPosts", headers=headers, json=body
            )
            return self._handle_response(resp, "article")

    def _resolve_author(self, as_org: bool) -> str:
        """Resolve the author URN for the post."""
        if as_org and LINKEDIN_ORG_ID:
            return f"urn:li:organization:{LINKEDIN_ORG_ID}"
        return (
            LINKEDIN_USER_ID
            if LINKEDIN_USER_ID.startswith("urn:li:")
            else f"urn:li:person:{LINKEDIN_USER_ID}"
        )

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202405",
        }

    def _handle_response(self, resp: httpx.Response, post_type: str) -> dict[str, Any]:
        if resp.status_code in (200, 201):
            data = resp.json()
            post_id = data.get("id", "unknown")
            return {
                "status": "published",
                "message_id": post_id,
                "type": post_type,
                "activity_url": (
                    f"https://www.linkedin.com/feed/update/{post_id}"
                    if post_id != "unknown"
                    else None
                ),
            }

        try:
            err = resp.json()
            error_msg = str(err.get("message", err))
        except (json.JSONDecodeError, KeyError):
            error_msg = resp.text[:500]

        logger.error("LinkedIn API error %s: %s", resp.status_code, error_msg)
        return {
            "status": "error",
            "error": f"LinkedIn API returned {resp.status_code}: {error_msg}",
            "type": post_type,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(LinkedinPublisherTool())
