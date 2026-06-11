"""
Visual Reasoning & Image Analysis Tools — Image Describer.

image_describer → Send an image to a Vision-capable LLM and receive a
    detailed text description of its contents.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
VISION_TIMEOUT = int(os.getenv("VISION_TIMEOUT", "90"))
DEFAULT_MAX_TOKENS = int(os.getenv("VISION_MAX_TOKENS", "1024"))

_DEFAULT_SYSTEM_PROMPT = (
    "You are a precise image description assistant. Describe the image in detail, "
    "covering: the main subject(s), setting, colors, composition, text if any, "
    "and notable details. Be factual and thorough."
)


# ── Input ─────────────────────────────────────────────────────────────


class ImageDescriberInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded image data (data URI prefix optional)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the image from",
    )
    prompt: str | None = Field(
        None,
        description="Custom prompt to guide the description (overrides default system prompt)",
    )
    detail: str = Field(
        "auto",
        description="Vision detail level: 'low', 'high', or 'auto'",
    )
    model: str | None = Field(
        None,
        description=f"Vision model to use (default: {DEFAULT_VISION_MODEL})",
    )
    max_tokens: int = Field(
        DEFAULT_MAX_TOKENS,
        ge=1,
        le=4096,
        description="Maximum tokens in the response",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class ImageDescriberTool(BaseTool):
    """Generate text descriptions of images using Vision-capable LLMs."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="image_describer",
            name="Image Describer",
            description=(
                "Send an image to a Vision language model and receive a "
                "detailed text description of its contents. Supports custom "
                "prompts and detail levels."
            ),
            category="visual-reasoning-and-image-analysis",
            input_schema=ImageDescriberInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["vision", "image", "description", "llm", "multimodal"],
            requires_auth=True,
            timeout_seconds=VISION_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ImageDescriberInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if not validated.data and not validated.url:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'data' (base64) or 'url' must be provided",
            )

        if validated.detail not in ("low", "high", "auto"):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Invalid detail level: '{validated.detail}'. Use 'low', 'high', or 'auto'.",
            )

        if not OPENAI_API_KEY:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="OPENAI_API_KEY not configured — set the environment variable",
            )

        try:
            result = await self._describe_image(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.warning("image_describer failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _describe_image ──────────────────────────────────────────

    async def _describe_image(self, validated: ImageDescriberInput) -> dict[str, Any]:
        """Fetch image bytes and send to the Vision API."""
        image_bytes = await resolve_input(validated.data, validated.url, label="image", fetch_timeout=30)

        # Encode as base64 data URI
        media_type = self._detect_media_type(image_bytes)
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{media_type};base64,{b64}"

        model = validated.model or DEFAULT_VISION_MODEL
        prompt = validated.prompt or _DEFAULT_SYSTEM_PROMPT

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_uri,
                            "detail": validated.detail,
                        },
                    },
                ],
            },
        ]

        url = f"{OPENAI_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": validated.max_tokens,
        }

        async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        description = choice["message"]["content"].strip()
        usage = data.get("usage", {})

        return {
            "description": description,
            "model": model,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "finish_reason": choice.get("finish_reason", "unknown"),
            "image_size_bytes": len(image_bytes),
        }

    @staticmethod
    def _detect_media_type(image_bytes: bytes) -> str:
        """Detect image media type from magic bytes."""
        if image_bytes[:4] == b"\x89PNG":
            return "image/png"
        if image_bytes[:2] == b"\xff\xd8":
            return "image/jpeg"
        if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if image_bytes[:4] in (b"RIFF",) and image_bytes[8:12] == b"WEBP":
            return "image/webp"
        return "image/png"  # fallback


# ── Register ──────────────────────────────────────────────────────────

register_tool(ImageDescriberTool())
