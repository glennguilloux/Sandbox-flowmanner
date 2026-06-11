"""
Multimedia Generation Tools — HeyGen Video Avatar.

heygen_video_avatar → Generate talking-head avatar videos via HeyGen API with
    configurable avatar, voice, resolution, polling, and local storage.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any, Literal

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY", "")
HEYGEN_BASE_URL = "https://api.heygen.com/v2"
HEYGEN_TIMEOUT = int(os.getenv("HEYGEN_TIMEOUT", "600"))
HEYGEN_STORAGE_DIR = os.getenv("HEYGEN_STORAGE_DIR", "/tmp/flowmanner/videos")
HEYGEN_POLL_INTERVAL = int(os.getenv("HEYGEN_POLL_INTERVAL", "3"))

HEYGEN_RESOLUTIONS = ("480p", "720p", "1080p")

RESOLUTION_COST_CREDITS = {
    "480p": 1,
    "720p": 2,
    "1080p": 4,
}


class HeyGenVideoAvatarInput(ToolInput):
    """Input schema: text, avatar_id, voice_id, video_format, resolution, poll.*, save_to_storage."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Script text for the avatar to speak",
    )
    avatar_id: str = Field(
        ...,
        description="HeyGen avatar ID to use as the presenter",
    )
    voice_id: str | None = Field(
        None,
        description="HeyGen voice ID. Uses avatar default if omitted.",
    )
    video_format: Literal["mp4", "webm"] = Field(
        "mp4",
        description="Output video format",
    )
    resolution: Literal["480p", "720p", "1080p"] = Field(
        "720p",
        description="Output video resolution",
    )
    background: str | None = Field(
        None,
        description="Background color hex (e.g., '#00ff00') or image URL",
    )
    caption: bool = Field(
        False,
        description="Generate captions/subtitles",
    )
    avatar_position: Literal["center", "left", "right"] = Field(
        "center",
        description="Avatar position in the video frame",
    )
    voice_speed: float = Field(
        1.0,
        ge=0.5,
        le=2.0,
        description="Voice speaking speed multiplier (0.5 = half speed, 2.0 = double speed)",
    )
    poll_for_completion: bool = Field(
        True,
        description="Poll for video completion; if False, returns video_id immediately",
    )
    poll_timeout_seconds: int = Field(
        300,
        ge=30,
        le=600,
        description="Maximum time to wait for video generation",
    )
    api_key: str | None = Field(
        None,
        description="HeyGen API key. Uses HEYGEN_API_KEY env var if omitted.",
    )
    save_to_storage: bool = Field(
        True,
        description="Download and save generated video to local storage",
    )


class HeyGenVideoAvatarTool(BaseTool):
    """Generate talking-head avatar videos via HeyGen API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="heygen_video_avatar",
            name="HeyGen Video Avatar",
            description=(
                "Generate talking-head avatar videos via HeyGen API with "
                "configurable avatar, voice, resolution, background, captions, "
                "and async polling for completion. Includes local video storage."
            ),
            category="multimedia-generation",
            input_schema=HeyGenVideoAvatarInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "video_id": {"type": "string"},
                    "status": {"type": "string"},
                    "video_url": {"type": "string"},
                    "video_path": {"type": "string"},
                    "duration_seconds": {"type": "number"},
                    "resolution": {"type": "string"},
                    "avatar_id": {"type": "string"},
                    "text_length": {"type": "integer"},
                    "file_size_bytes": {"type": "integer"},
                    "credit_cost": {"type": "integer"},
                    "generation_time_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["video", "avatar", "heygen", "generation", "multimedia"],
            requires_auth=True,
            timeout_seconds=HEYGEN_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = HeyGenVideoAvatarInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        api_key = validated.api_key or HEYGEN_API_KEY
        if not api_key:
            return ToolResult.error_result(tool_id=self.tool_id, error="HeyGen API key required")

        start = time.monotonic()

        try:
            # --- Step 1: Create the video generation job ---
            headers = {
                "X-Api-Key": api_key,
                "Content-Type": "application/json",
            }

            body: dict[str, Any] = {
                "video_inputs": [
                    {
                        "character": {
                            "type": "avatar",
                            "avatar_id": validated.avatar_id,
                            "scale": 1.0,
                        },
                        "voice": {
                            "type": "text",
                            "voice_id": validated.voice_id,
                            "input_text": validated.text,
                            "speed": validated.voice_speed,
                        },
                    }
                ],
                "dimension": {
                    "width": self._resolution_width(validated.resolution),
                    "height": self._resolution_height(validated.resolution),
                },
                "aspect_ratio": "16:9",
            }

            if validated.video_format == "webm":
                body["output_format"] = "webm"

            if validated.background:
                if validated.background.startswith("#"):
                    body["background"] = {
                        "type": "color",
                        "value": validated.background,
                    }
                else:
                    body["background"] = {"type": "image", "url": validated.background}

            if validated.caption:
                body["caption"] = True

            if validated.avatar_position != "center":
                body["avatar_style"] = {
                    "horizontal_align": validated.avatar_position,
                }

            async with httpx.AsyncClient(timeout=60) as client:
                create_resp = await client.post(
                    f"{HEYGEN_BASE_URL}/video/generate",
                    headers=headers,
                    json=body,
                )
                create_resp.raise_for_status()
                create_data = create_resp.json()

            video_id = create_data.get("data", {}).get("video_id", "")
            if not video_id:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Failed to create video: {create_data}",
                )

            credit_cost = RESOLUTION_COST_CREDITS.get(validated.resolution, 2)

            if not validated.poll_for_completion:
                gen_time = int((time.monotonic() - start) * 1000)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "video_id": video_id,
                        "status": "processing",
                        "video_url": "",
                        "video_path": "",
                        "duration_seconds": 0,
                        "resolution": validated.resolution,
                        "avatar_id": validated.avatar_id,
                        "text_length": len(validated.text),
                        "file_size_bytes": 0,
                        "credit_cost": credit_cost,
                        "generation_time_ms": gen_time,
                        "success": True,
                    },
                )

            # --- Step 2: Poll for completion ---
            video_url = ""
            video_path = ""
            duration = 0.0
            file_size = 0

            async with httpx.AsyncClient(timeout=30) as client:
                deadline = time.monotonic() + validated.poll_timeout_seconds
                while time.monotonic() < deadline:
                    await asyncio.sleep(HEYGEN_POLL_INTERVAL)
                    status_resp = await client.get(
                        f"{HEYGEN_BASE_URL}/video/generate/status",
                        headers={"X-Api-Key": api_key},
                        params={"video_id": video_id},
                    )
                    status_resp.raise_for_status()
                    status_data = status_resp.json()
                    status = status_data.get("data", {}).get("status", "")

                    if status == "completed":
                        video_url = status_data.get("data", {}).get("video_url", "")
                        duration = status_data.get("data", {}).get("duration", 0.0)

                        # Download if saving
                        if video_url and validated.save_to_storage:
                            try:
                                dl_resp = await client.get(video_url, follow_redirects=True)
                                video_data = dl_resp.content
                                file_size = len(video_data)
                                video_path = self._save_video(
                                    video_data,
                                    video_id,
                                    validated.video_format,
                                )
                            except Exception as dl_err:
                                logger.warning("Failed to download video: %s", dl_err)

                        gen_time = int((time.monotonic() - start) * 1000)
                        return ToolResult.success_result(
                            tool_id=self.tool_id,
                            result={
                                "video_id": video_id,
                                "status": "completed",
                                "video_url": video_url,
                                "video_path": video_path,
                                "duration_seconds": duration,
                                "resolution": validated.resolution,
                                "avatar_id": validated.avatar_id,
                                "text_length": len(validated.text),
                                "file_size_bytes": file_size,
                                "credit_cost": credit_cost,
                                "generation_time_ms": gen_time,
                                "success": True,
                            },
                        )

                    elif status == "failed":
                        error_msg = status_data.get("data", {}).get("error", "Unknown error")
                        return ToolResult.error_result(
                            tool_id=self.tool_id,
                            error=f"Video generation failed: {error_msg}",
                        )

                # Timeout
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Polling timed out after {validated.poll_timeout_seconds}s. Video ID: {video_id}",
                )

        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(tool_id=self.tool_id, error=f"HeyGen API error: {detail}")
        except Exception as e:
            logger.exception("heygen_video_avatar failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    @staticmethod
    def _resolution_width(resolution: str) -> int:
        return {"480p": 854, "720p": 1280, "1080p": 1920}.get(resolution, 1280)

    @staticmethod
    def _resolution_height(resolution: str) -> int:
        return {"480p": 480, "720p": 720, "1080p": 1080}.get(resolution, 720)

    @staticmethod
    def _save_video(video_data: bytes, video_id: str, fmt: str) -> str:
        """Save video bytes to local storage with metadata sidecar."""
        os.makedirs(HEYGEN_STORAGE_DIR, exist_ok=True)
        digest = hashlib.sha256(video_data).hexdigest()[:16]
        filename = f"avatar_{video_id}_{digest}.{fmt}"
        path = os.path.join(HEYGEN_STORAGE_DIR, filename)
        with open(path, "wb") as f:
            f.write(video_data)

        sidecar = {
            "video_id": video_id,
            "format": fmt,
            "file_size": len(video_data),
            "digest": digest,
        }
        sidecar_path = path + ".meta.json"
        with open(sidecar_path, "w") as f:
            json.dump(sidecar, f, indent=2)

        return path


register_tool(HeyGenVideoAvatarTool())
