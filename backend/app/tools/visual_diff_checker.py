"""
Visual Reasoning & Image Analysis Tools — Visual Diff Checker.

visual_diff_checker → Compare two images pixel-by-pixel, generate a diff
    heatmap, and report the percentage of changed pixels.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from typing import Any

import numpy as np
from PIL import Image
from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

DIFF_DEFAULT_THRESHOLD = float(os.getenv("DIFF_THRESHOLD", "10.0"))
DIFF_TIMEOUT = int(os.getenv("DIFF_TIMEOUT", "60"))


# ── Input ─────────────────────────────────────────────────────────────


class VisualDiffCheckerInput(ToolInput):
    image1_data: str | None = Field(
        None,
        description="Base64-encoded first image (data URI prefix optional)",
    )
    image1_url: str | None = Field(
        None,
        description="URL to fetch the first image from",
    )
    image2_data: str | None = Field(
        None,
        description="Base64-encoded second image (data URI prefix optional)",
    )
    image2_url: str | None = Field(
        None,
        description="URL to fetch the second image from",
    )
    threshold: float = Field(
        DIFF_DEFAULT_THRESHOLD,
        ge=0.0,
        le=255.0,
        description="Pixel difference threshold (0 = exact match, higher = more tolerant)",
    )
    include_diff_image: bool = Field(
        True,
        description="Include the diff heatmap image as base64 in the result",
    )
    diff_color: str = Field(
        "#FF0000",
        description="Highlight color for changed pixels in the diff image (hex or color name)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class VisualDiffCheckerTool(BaseTool):
    """Compare two images and highlight visual differences."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="visual_diff_checker",
            name="Visual Diff Checker",
            description=(
                "Compare two images for visual regressions or changes. "
                "Generates a heatmap overlay highlighting differences and "
                "reports the percentage of changed pixels."
            ),
            category="visual-reasoning-and-image-analysis",
            input_schema=VisualDiffCheckerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["image", "diff", "comparison", "visual", "regression"],
            requires_auth=False,
            timeout_seconds=DIFF_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = VisualDiffCheckerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.image1_data and not validated.image1_url:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'image1_data' or 'image1_url' must be provided",
            )
        if not validated.image2_data and not validated.image2_url:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'image2_data' or 'image2_url' must be provided",
            )

        try:
            result = await self._compute_diff(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.warning("visual_diff_checker failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _compute_diff ────────────────────────────────────────────

    async def _compute_diff(self, validated: VisualDiffCheckerInput) -> dict[str, Any]:
        """Load both images, compute diff, and return analysis."""
        bytes1 = await resolve_input(
            validated.image1_data, validated.image1_url,
            label="image1", fetch_timeout=30,
        )
        bytes2 = await resolve_input(
            validated.image2_data, validated.image2_url,
            label="image2", fetch_timeout=30,
        )

        img1 = Image.open(io.BytesIO(bytes1)).convert("RGB")
        img2 = Image.open(io.BytesIO(bytes2)).convert("RGB")

        size1 = {"width": img1.width, "height": img1.height}
        size2 = {"width": img2.width, "height": img2.height}

        # Resize if dimensions differ
        dimensions_match = size1 == size2
        if not dimensions_match:
            img2 = img2.resize((img1.width, img1.height), Image.LANCZOS)

        # Convert to numpy arrays for pixel-wise comparison
        arr1 = np.array(img1, dtype=np.float32)
        arr2 = np.array(img2, dtype=np.float32)

        # Compute per-pixel absolute difference
        diff = np.abs(arr1 - arr2)

        # Create binary mask of changed pixels (above threshold)
        changed_mask = np.max(diff, axis=2) > validated.threshold
        changed_pixels = int(np.sum(changed_mask))
        total_pixels = img1.width * img1.height
        diff_percentage = round(changed_pixels / total_pixels * 100, 2)

        # Analyze by channel
        channel_diff = {
            "red": round(float(np.mean(diff[:, :, 0])), 2),
            "green": round(float(np.mean(diff[:, :, 1])), 2),
            "blue": round(float(np.mean(diff[:, :, 2])), 2),
        }
        overall_mean_diff = round(float(np.mean(diff)), 2)

        # Generate diff image with highlights
        result_data: dict[str, Any] = {
            "diff_percentage": diff_percentage,
            "changed_pixels": changed_pixels,
            "total_pixels": total_pixels,
            "mean_pixel_difference": overall_mean_diff,
            "channel_differences": channel_diff,
            "threshold": validated.threshold,
            "dimensions_match": dimensions_match,
            "image1_size": size1,
            "image2_size": size2,
        }

        if validated.include_diff_image:
            diff_image = self._generate_diff_overlay(img1, changed_mask)
            buf = io.BytesIO()
            diff_image.save(buf, format="PNG")
            result_data["diff_image_base64"] = base64.b64encode(
                buf.getvalue()
            ).decode("ascii")
            diff_image.close()

        img1.close()
        img2.close()

        return result_data

    # ── _generate_diff_overlay ───────────────────────────────────

    def _generate_diff_overlay(
        self, base_image: Image.Image, changed_mask: np.ndarray
    ) -> Image.Image:
        """Overlay a semi-transparent red highlight on changed regions."""
        result = base_image.copy().convert("RGBA")

        # Create red overlay with alpha based on change mask
        overlay = np.zeros(
            (base_image.height, base_image.width, 4), dtype=np.uint8
        )
        overlay[changed_mask] = [255, 0, 0, 128]  # semi-transparent red

        overlay_img = Image.fromarray(overlay, "RGBA")
        result = Image.alpha_composite(result, overlay_img)
        overlay_img.close()

        return result


# ── Register ──────────────────────────────────────────────────────────

register_tool(VisualDiffCheckerTool())
