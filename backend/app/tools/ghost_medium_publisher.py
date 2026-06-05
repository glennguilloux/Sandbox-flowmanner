"""
Social Media & Content Publishing Tools — Ghost/Medium Publisher.

ghost_medium_publisher → Push draft or published long-form articles to
    Ghost CMS and Medium platforms via their REST APIs.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from pydantic import Field

try:
    from jwcrypto import jwk
    from jwcrypto import jwt as jw_jwt
except ImportError:
    jwk = None  # type: ignore[assignment]
    jw_jwt = None  # type: ignore[assignment]

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

# Ghost CMS
GHOST_URL = os.getenv("GHOST_URL", "")
GHOST_ADMIN_API_KEY = os.getenv("GHOST_ADMIN_API_KEY", "")
GHOST_CONTENT_API_KEY = os.getenv("GHOST_CONTENT_API_KEY", "")

# Medium
MEDIUM_ACCESS_TOKEN = os.getenv("MEDIUM_ACCESS_TOKEN", "")

CMS_TIMEOUT = int(os.getenv("CMS_TIMEOUT", "30"))

MEDIUM_API_BASE = "https://api.medium.com/v1"
GHOST_API_PATH = "/ghost/api/admin/posts/"


# ── Input ─────────────────────────────────────────────────────────────


class GhostMediumPublisherInput(ToolInput):
    title: str = Field(
        ...,
        description="Article title",
    )
    content: str = Field(
        ...,
        description="Article body. For Medium: HTML. For Ghost: mobiledoc or HTML.",
    )
    platform: str = Field(
        ...,
        description="Target platform: 'ghost', 'medium', or 'both'",
    )
    status: str = Field(
        "draft",
        description="Publication status: 'draft' or 'published'",
    )
    tags: list[str] | None = Field(
        None,
        description="Tags/categories for the article",
    )
    excerpt: str | None = Field(
        None,
        description="Short excerpt or description",
    )
    featured_image_url: str | None = Field(
        None,
        description="URL of featured image",
    )
    canonical_url: str | None = Field(
        None,
        description="Canonical URL (for cross-posting attribution)",
    )
    content_format: str = Field(
        "html",
        description="Content format: 'html' or 'markdown'",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class GhostMediumPublisherTool(BaseTool):
    """Push articles to Ghost CMS and Medium with a single call."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="ghost_medium_publisher",
            name="Ghost/Medium Publisher",
            description=(
                "Push draft or published long-form articles to Ghost CMS and/or "
                "Medium. Supports HTML and Markdown content, tags, excerpts, "
                "featured images, and canonical cross-posting URLs."
            ),
            category="social-media-content-publishing",
            input_schema=GhostMediumPublisherInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["social", "cms", "ghost", "medium", "publish"],
            requires_auth=True,
            timeout_seconds=CMS_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GhostMediumPublisherInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        valid_platforms = ("ghost", "medium", "both")
        if validated.platform not in valid_platforms:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Invalid platform: '{validated.platform}'. "
                f"Use: {', '.join(valid_platforms)}",
            )

        valid_statuses = ("draft", "published")
        if validated.status not in valid_statuses:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Invalid status: '{validated.status}'. Use: {', '.join(valid_statuses)}",
            )

        try:
            result = await self._publish(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("ghost_medium_publisher failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _publish(
        self, validated: GhostMediumPublisherInput
    ) -> dict[str, Any]:
        """Publish to selected platform(s)."""
        results: dict[str, Any] = {"title": validated.title, "platforms": {}}
        has_any_creds = False

        # Ghost
        if validated.platform in ("ghost", "both"):
            if GHOST_URL and GHOST_ADMIN_API_KEY:
                has_any_creds = True
                results["platforms"]["ghost"] = await self._publish_ghost(validated)
            else:
                results["platforms"]["ghost"] = {
                    "status": "not_configured",
                    "message": (
                        "Ghost not configured. Set GHOST_URL and GHOST_ADMIN_API_KEY."
                    ),
                }

        # Medium
        if validated.platform in ("medium", "both"):
            if MEDIUM_ACCESS_TOKEN:
                has_any_creds = True
                results["platforms"]["medium"] = await self._publish_medium(validated)
            else:
                results["platforms"]["medium"] = {
                    "status": "not_configured",
                    "message": (
                        "Medium not configured. Set MEDIUM_ACCESS_TOKEN."
                    ),
                }

        if not has_any_creds:
            results["status"] = "not_configured"
            results["message"] = (
                "No CMS platforms configured. Set GHOST_URL/GHOST_ADMIN_API_KEY "
                "for Ghost, or MEDIUM_ACCESS_TOKEN for Medium."
            )
        else:
            results["status"] = "complete"

        return results

    async def _publish_ghost(
        self, validated: GhostMediumPublisherInput
    ) -> dict[str, Any]:
        """Publish to Ghost Admin API."""
        # Ghost uses JWT-like key: split the key into id:secret
        try:
            key_id, key_secret = GHOST_ADMIN_API_KEY.split(":", 1)
        except ValueError:
            return {"status": "error", "error": "Invalid GHOST_ADMIN_API_KEY format (expected 'id:secret')"}

        if jwk is None or jw_jwt is None:
            return {"status": "error", "error": "jwcrypto is not installed. Install with: pip install jwcrypto"}

        import time as _time

        # Create JWT for Ghost Admin API
        iat = int(_time.time())
        header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
        claims = {
            "iat": iat,
            "exp": iat + 300,  # 5 min
            "aud": "/admin/",
        }

        key = jwk.JWK(k=key_secret, kty="oct")
        token = jw_jwt.JWT(header=header, claims=claims)
        token.make_signed_token(key)

        body: dict[str, Any] = {
            "posts": [{
                "title": validated.title,
                "mobiledoc": json.dumps({
                    "version": "0.3.1",
                    "markups": [],
                    "atoms": [],
                    "cards": [[
                        "html",
                        {"html": validated.content if validated.content_format == "html" else f"<p>{validated.content}</p>"}
                    ]],
                    "sections": [[1, "p", [[0, [], 0, validated.content[:5000]]]]] if validated.content_format != "html" else [[10, 0]],
                }),
                "status": validated.status,
                "feature_image": validated.featured_image_url or None,
                "excerpt": validated.excerpt or None,
                "tags": [{"name": t} for t in (validated.tags or [])] if validated.tags else None,
                "canonical_url": validated.canonical_url or None,
            }]
        }

        async with httpx.AsyncClient(timeout=CMS_TIMEOUT) as client:
            resp = await client.post(
                f"{GHOST_URL.rstrip('/')}{GHOST_API_PATH}",
                headers={
                    "Authorization": f"Ghost {token.serialize()}",
                    "Content-Type": "application/json",
                    "Accept-Version": "v5.0",
                },
                json=body,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                post = data.get("posts", [{}])[0]
                return {
                    "status": "published" if validated.status == "published" else "draft",
                    "message_id": post.get("id", "unknown"),
                    "url": post.get("url"),
                    "ghost_url": GHOST_URL,
                }
            return {
                "status": "error",
                "error": f"Ghost API returned {resp.status_code}: {resp.text[:500]}",
            }

    async def _publish_medium(
        self, validated: GhostMediumPublisherInput
    ) -> dict[str, Any]:
        """Publish to Medium via REST API."""
        headers = {
            "Authorization": f"Bearer {MEDIUM_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        # Get user ID first
        async with httpx.AsyncClient(timeout=CMS_TIMEOUT) as client:
            resp = await client.get(
                f"{MEDIUM_API_BASE}/me", headers=headers
            )
            if resp.status_code != 200:
                return {
                    "status": "error",
                    "error": f"Medium auth failed: {resp.status_code} {resp.text[:300]}",
                }
            user_id = resp.json()["data"]["id"]

            # Create post
            body: dict[str, Any] = {
                "title": validated.title,
                "contentFormat": validated.content_format,
                "content": validated.content,
                "publishStatus": validated.status,
            }
            if validated.tags:
                body["tags"] = validated.tags
            if validated.canonical_url:
                body["canonicalUrl"] = validated.canonical_url

            resp = await client.post(
                f"{MEDIUM_API_BASE}/users/{user_id}/posts",
                headers=headers,
                json=body,
            )
            if resp.status_code in (200, 201):
                data = resp.json()["data"]
                return {
                    "status": "published" if validated.status == "published" else "draft",
                    "message_id": data.get("id", "unknown"),
                    "url": data.get("url"),
                }
            return {
                "status": "error",
                "error": f"Medium API returned {resp.status_code}: {resp.text[:500]}",
            }


# ── Register ──────────────────────────────────────────────────────────

register_tool(GhostMediumPublisherTool())
