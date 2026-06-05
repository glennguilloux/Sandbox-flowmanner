"""
Social Media & Content Publishing Tools — Instagram Media Publisher.

instagram_media_publisher → Publish photos and carousels directly to
    Instagram using the Instagram Graph API.
"""

from __future__ import annotations

import asyncio
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

INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_USER_ID = os.getenv("INSTAGRAM_USER_ID", "")
INSTAGRAM_TIMEOUT = int(os.getenv("INSTAGRAM_TIMEOUT", "60"))

INSTAGRAM_API_BASE = "https://graph.instagram.com/v21.0"

INSTAGRAM_MAX_CAPTION = 2200
INSTAGRAM_MAX_CAROUSEL_ITEMS = 10
INSTAGRAM_POLL_INTERVAL = 3  # seconds between status checks
INSTAGRAM_MAX_POLLS = 20  # max status check iterations

# Supported media kinds
_VALID_MEDIA_TYPES = ("photo", "video", "carousel")


# ── Input ─────────────────────────────────────────────────────────────


class InstagramMediaPublisherInput(ToolInput):
    caption: str | None = Field(
        None,
        description=f"Caption text (max {INSTAGRAM_MAX_CAPTION} chars)",
    )
    media_urls: list[str] | None = Field(
        None,
        description="List of publicly accessible media URLs to post",
    )
    media_data: list[str] | None = Field(
        None,
        description="List of base64-encoded media files (data URIs optional)",
    )
    media_type: str = Field(
        "photo",
        description="Post type: 'photo', 'video', or 'carousel' (requires 2-10 items)",
    )
    hashtags: list[str] | None = Field(
        None,
        description="List of hashtags to append (without # symbol)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class InstagramMediaPublisherTool(BaseTool):
    """Publish photos and carousels to Instagram via the Graph API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="instagram_media_publisher",
            name="Instagram Media Publisher",
            description=(
                "Publish photos, videos, and carousels directly to Instagram "
                "using the Instagram Graph API. Requires a Facebook App with "
                "Instagram Basic Display and Content Publishing permissions."
            ),
            category="social-media-content-publishing",
            input_schema=InstagramMediaPublisherInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["social", "instagram", "media", "publish", "photo"],
            requires_auth=True,
            timeout_seconds=INSTAGRAM_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = InstagramMediaPublisherInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.media_type not in _VALID_MEDIA_TYPES:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Invalid media_type: '{validated.media_type}'. "
                f"Use: {', '.join(_VALID_MEDIA_TYPES)}",
            )

        if not validated.media_urls and not validated.media_data:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'media_urls' or 'media_data' must be provided",
            )

        if validated.caption and len(validated.caption) > INSTAGRAM_MAX_CAPTION:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Caption too long: {len(validated.caption)} chars "
                f"(max {INSTAGRAM_MAX_CAPTION})",
            )

        if validated.media_type == "carousel":
            total_items = len(validated.media_urls or []) + len(
                validated.media_data or []
            )
            if total_items < 2:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error="Carousel requires at least 2 media items",
                )
            if total_items > INSTAGRAM_MAX_CAROUSEL_ITEMS:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Carousel max items: {INSTAGRAM_MAX_CAROUSEL_ITEMS}",
                )

        try:
            result = await self._publish(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("instagram_media_publisher failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _publish(self, validated: InstagramMediaPublisherInput) -> dict[str, Any]:
        """Validate credentials and publish to Instagram."""
        if not INSTAGRAM_ACCESS_TOKEN:
            media_count = len(validated.media_urls or []) + len(
                validated.media_data or []
            )
            return {
                "status": "not_configured",
                "message": (
                    "Instagram access token not configured. Set INSTAGRAM_ACCESS_TOKEN "
                    "and INSTAGRAM_USER_ID environment variables. Requires a Facebook App "
                    "with instagram_basic, instagram_content_publish, and pages_read_engagement."
                ),
                "preview": {
                    "type": validated.media_type,
                    "media_count": media_count,
                    "caption": (validated.caption or "")[:200]
                    + (
                        "..."
                        if validated.caption and len(validated.caption) > 200
                        else ""
                    ),
                },
            }

        if is_placeholder(INSTAGRAM_ACCESS_TOKEN):
            media_count = len(validated.media_urls or []) + len(
                validated.media_data or []
            )
            return {
                "status": "not_configured",
                "message": (
                    "INSTAGRAM_ACCESS_TOKEN is a placeholder. "
                    "Replace placeholder in .env with a real Instagram access token. "
                    "Requires a Facebook App with instagram_basic, instagram_content_publish, "
                    "and pages_read_engagement permissions. Preview:"
                ),
                "preview": {
                    "type": validated.media_type,
                    "media_count": media_count,
                    "caption": (validated.caption or "")[:200]
                    + (
                        "..."
                        if validated.caption and len(validated.caption) > 200
                        else ""
                    ),
                },
            }

        # Resolve media sources (prioritize URLs)
        media_sources = list(validated.media_urls or [])
        if validated.media_data:
            media_sources.extend(validated.media_data)

        if validated.media_type == "carousel":
            return await self._publish_carousel(
                media_sources, validated.caption or "", validated.hashtags
            )
        return await self._publish_single(
            validated.media_type,
            media_sources[0],
            validated.caption or "",
            validated.hashtags,
        )

    async def _publish_single(
        self,
        media_type: str,
        media_source: str,
        caption: str,
        hashtags: list[str] | None,
    ) -> dict[str, Any]:
        """Publish a single photo or video."""
        full_caption = self._build_caption(caption, hashtags)

        # Step 1: Create media container
        container_id = await self._create_media_container(
            media_type, media_source, full_caption
        )
        if not container_id:
            return {"status": "error", "error": "Failed to create media container"}

        # Step 2: Publish the container
        creation_id = await self._publish_container(container_id)
        if not creation_id:
            return {"status": "error", "error": "Failed to publish media container"}

        # Step 3: Wait for processing
        media_url = await self._wait_for_ready(creation_id)
        return {
            "status": "published",
            "message_id": creation_id,
            "media_type": media_type,
            "permalink": media_url or f"https://www.instagram.com/p/{creation_id}/",
        }

    async def _publish_carousel(
        self,
        media_sources: list[str],
        caption: str,
        hashtags: list[str] | None,
    ) -> dict[str, Any]:
        """Publish a carousel (multiple media items)."""
        full_caption = self._build_caption(caption, hashtags)
        container_ids: list[str] = []

        # Step 1: Create individual media containers
        for i, source in enumerate(media_sources):
            is_url = source.startswith("http://") or source.startswith("https://")
            media_type = (
                "video"
                if is_url and source.lower().rsplit("?", 1)[0].endswith(".mp4")
                else "photo"
            )
            container_id = await self._create_media_container(media_type, source, "")
            if not container_id:
                return {
                    "status": "partial",
                    "error": f"Failed at item {i}",
                    "created_items": len(container_ids),
                    "containers": container_ids,
                }
            container_ids.append(container_id)

        # Step 2: Create carousel container
        carousel_id = await self._create_carousel_container(container_ids, full_caption)
        if not carousel_id:
            return {"status": "error", "error": "Failed to create carousel container"}

        # Step 3: Publish
        creation_id = await self._publish_container(carousel_id)
        if not creation_id:
            return {"status": "error", "error": "Failed to publish carousel"}

        # Step 4: Wait for ready
        media_url = await self._wait_for_ready(creation_id)
        return {
            "status": "published",
            "message_id": creation_id,
            "media_type": "carousel",
            "item_count": len(container_ids),
            "permalink": media_url or f"https://www.instagram.com/p/{creation_id}/",
        }

    async def _create_media_container(
        self, media_type: str, source: str, caption: str
    ) -> str | None:
        """Step 1: Create a media object container."""
        is_url = source.startswith("http://") or source.startswith("https://")
        if not is_url:
            # Instagram Graph API only supports publicly accessible URLs.
            # Base64 data cannot be uploaded directly; host the media first.
            logger.error("Instagram only supports public URLs, not base64 data")
            return None

        params: dict[str, str] = {
            "image_url" if media_type == "photo" else "video_url": source,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
        if caption:
            params["caption"] = caption

        async with httpx.AsyncClient(timeout=INSTAGRAM_TIMEOUT) as client:
            resp = await client.post(
                f"{INSTAGRAM_API_BASE}/{INSTAGRAM_USER_ID}/media",
                params=params,
            )
            if resp.status_code in (200, 201):
                return resp.json().get("id")
            logger.error(
                f"Instagram container error: {resp.status_code} {resp.text[:300]}"
            )
            return None

    async def _create_carousel_container(
        self, children_ids: list[str], caption: str
    ) -> str | None:
        """Step 2 (carousel): Create a carousel container."""
        params: dict[str, str] = {
            "media_type": "CAROUSEL",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
        if caption:
            params["caption"] = caption
        for i, cid in enumerate(children_ids):
            params[f"children[{i}]"] = cid

        async with httpx.AsyncClient(timeout=INSTAGRAM_TIMEOUT) as client:
            resp = await client.post(
                f"{INSTAGRAM_API_BASE}/{INSTAGRAM_USER_ID}/media",
                params=params,
            )
            if resp.status_code in (200, 201):
                return resp.json().get("id")
            logger.error(
                f"Instagram carousel error: {resp.status_code} {resp.text[:300]}"
            )
            return None

    async def _publish_container(self, container_id: str) -> str | None:
        """Step 2/3: Publish a media container."""
        async with httpx.AsyncClient(timeout=INSTAGRAM_TIMEOUT) as client:
            resp = await client.post(
                f"{INSTAGRAM_API_BASE}/{INSTAGRAM_USER_ID}/media_publish",
                params={
                    "creation_id": container_id,
                    "access_token": INSTAGRAM_ACCESS_TOKEN,
                },
            )
            if resp.status_code in (200, 201):
                return resp.json().get("id")
            logger.error(
                f"Instagram publish error: {resp.status_code} {resp.text[:300]}"
            )
            return None

    async def _wait_for_ready(self, creation_id: str) -> str | None:
        """Poll for media processing completion."""
        for _attempt in range(INSTAGRAM_MAX_POLLS):
            await asyncio.sleep(INSTAGRAM_POLL_INTERVAL)
            async with httpx.AsyncClient(timeout=INSTAGRAM_TIMEOUT) as client:
                resp = await client.get(
                    f"{INSTAGRAM_API_BASE}/{creation_id}",
                    params={
                        "fields": "status,permalink",
                        "access_token": INSTAGRAM_ACCESS_TOKEN,
                    },
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                status = data.get("status", "UNKNOWN")
                if status == "FINISHED":
                    return data.get("permalink")
                if status == "ERROR":
                    logger.error(f"Instagram processing error: {data}")
                    return None
        logger.warning(
            f"Instagram media {creation_id} still processing after {INSTAGRAM_MAX_POLLS} polls"
        )
        return None

    def _build_caption(self, caption: str, hashtags: list[str] | None) -> str:
        """Append hashtags to caption."""
        if not hashtags:
            return caption
        tag_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags)
        if caption:
            return f"{caption}\n\n{tag_str}"
        return tag_str


# ── Register ──────────────────────────────────────────────────────────

register_tool(InstagramMediaPublisherTool())
