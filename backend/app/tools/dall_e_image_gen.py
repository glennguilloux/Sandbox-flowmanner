"""
Multimedia Generation Tools — DALL-E Image Generator.

dall_e_image_gen → Generate images via OpenAI DALL-E 2/3 API with configurable
    size, quality, style, negative prompt engineering, and optional storage.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from typing import Any, Literal

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DALLE_TIMEOUT = int(os.getenv("DALLE_TIMEOUT", "120"))
DALLE_STORAGE_DIR = os.getenv("DALLE_STORAGE_DIR", "/tmp/flowmanner/images")
DALLE_MODELS = ("dall-e-3", "dall-e-2")
DALLE_SIZES = {
    "dall-e-3": ("1024x1024", "1792x1024", "1024x1792"),
    "dall-e-2": ("256x256", "512x512", "1024x1024"),
}
DALLE_COST = {
    "dall-e-3": {"1024x1024": 0.040, "1792x1024": 0.080, "1024x1792": 0.080},
    "dall-e-2": {"1024x1024": 0.020, "512x512": 0.018, "256x256": 0.016},
}


class DallEImageGenInput(ToolInput):
    """Input schema: prompt, model, size, quality, style, n, negative_prompt, seed, save_to_storage."""

    prompt: str = Field(
        ..., min_length=1, max_length=4000,
        description="Image generation prompt",
    )
    model: Literal["dall-e-3", "dall-e-2"] = Field(
        "dall-e-3",
        description="DALL-E model to use",
    )
    size: Literal["1024x1024", "1792x1024", "1024x1792", "256x256", "512x512"] | None = Field(
        None,
        description="Image size. DALL-E 3: 1024x1024, 1792x1024, 1024x1792. DALL-E 2: 256x256, 512x512, 1024x1024.",
    )
    quality: Literal["standard", "hd"] = Field(
        "standard",
        description="Image quality. 'hd' is DALL-E 3 only.",
    )
    style: Literal["vivid", "natural"] = Field(
        "vivid",
        description="Image style. 'vivid' for hyper-real, 'natural' for more realistic.",
    )
    n: int = Field(
        1, ge=1, le=10,
        description="Number of images to generate (DALL-E 2 supports up to 10; DALL-E 3 supports 1)",
    )
    negative_prompt: str | None = Field(
        None,
        description="Elements to avoid (engineered into the prompt for DALL-E).",
    )
    seed: int | None = Field(
        None,
        description="Seed for reproducible generation (DALL-E 3 only for OpenAI tier 5+)",
    )
    api_key: str | None = Field(
        None,
        description="OpenAI API key. Uses OPENAI_API_KEY env var if omitted.",
    )
    save_to_storage: bool = Field(
        True,
        description="Download and save images to local storage",
    )
    output_prefix: str | None = Field(
        None, max_length=100,
        description="Prefix for saved image filenames",
    )


class DallEImageGenTool(BaseTool):
    """Generate images via OpenAI DALL-E API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="dall_e_image_gen",
            name="DALL-E Image Generator",
            description=(
                "Generate images via OpenAI DALL-E 2/3 API with configurable "
                "size, quality, style, negative prompt engineering, and "
                "optional local storage. Includes cost tracking and metadata "
                "preservation."
            ),
            category="multimedia-generation",
            input_schema=DallEImageGenInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "images": {"type": "array", "items": {"type": "object"}},
                    "model": {"type": "string"},
                    "cost_usd": {"type": "number"},
                    "generation_time_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["image", "dall-e", "openai", "generation", "multimedia"],
            requires_auth=True,
            timeout_seconds=DALLE_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = DallEImageGenInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        api_key = validated.api_key or OPENAI_API_KEY
        if not api_key:
            return ToolResult.error_result(tool_id=self.tool_id, error="OpenAI API key required")

        size = validated.size or (DALLE_SIZES.get(validated.model, ("1024x1024",))[0])

        start = time.monotonic()

        try:
            # Build prompt with negative prompt engineering
            enhanced_prompt = validated.prompt
            if validated.negative_prompt:
                enhanced_prompt = f"{validated.prompt}. Avoid: {validated.negative_prompt}"

            body: dict[str, Any] = {
                "model": validated.model,
                "prompt": enhanced_prompt,
                "n": validated.n if validated.model == "dall-e-2" else 1,
                "size": size,
                "response_format": "b64_json" if validated.save_to_storage else "url",
            }

            if validated.model == "dall-e-3":
                body["quality"] = validated.quality
                body["style"] = validated.style

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

            async with httpx.AsyncClient(timeout=DALLE_TIMEOUT) as client:
                resp = await client.post("https://api.openai.com/v1/images/generations", json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            images = []
            for i, img in enumerate(data.get("data", [])):
                image_entry: dict[str, Any] = {
                    "index": i,
                    "revised_prompt": img.get("revised_prompt", enhanced_prompt),
                }
                if "b64_json" in img:
                    image_entry["b64_json"] = img["b64_json"][:200] + "..."
                    if validated.save_to_storage:
                        path = self._save_image(img["b64_json"], validated.model, i, validated.output_prefix)
                        image_entry["local_path"] = path
                elif "url" in img:
                    image_entry["url"] = img["url"]

                images.append(image_entry)

            cost = DALLE_COST.get(validated.model, {}).get(size, 0.04) * len(images)
            gen_time = int((time.monotonic() - start) * 1000)

            return ToolResult.success_result(tool_id=self.tool_id, result={
                "images": images,
                "model": validated.model,
                "prompt": validated.prompt,
                "size": size,
                "cost_usd": round(cost, 4),
                "generation_time_ms": gen_time,
                "success": True,
            })
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(tool_id=self.tool_id, error=f"DALL-E API error: {detail}")
        except Exception as e:
            logger.exception("dall_e_image_gen failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    def _save_image(self, b64_data: str, model: str, index: int, prefix: str | None = None) -> str:
        os.makedirs(DALLE_STORAGE_DIR, exist_ok=True)
        digest = hashlib.sha256(b64_data.encode()).hexdigest()[:16]
        prefix_part = f"{prefix}_" if prefix else ""
        filename = f"{prefix_part}{model}_{index}_{digest}.png"
        path = os.path.join(DALLE_STORAGE_DIR, filename)
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64_data))
        return path


register_tool(DallEImageGenTool())
