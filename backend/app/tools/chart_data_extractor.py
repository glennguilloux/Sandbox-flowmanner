"""
Visual Reasoning & Image Analysis Tools — Chart Data Extractor (DIFFERENTIATOR).

chart_data_extractor → Reverse-engineer data tables from bar charts, line
    graphs, and pie charts using computer vision.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

import numpy as np
from PIL import Image
from pydantic import Field

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

CHART_TIMEOUT = int(os.getenv("CHART_TIMEOUT", "60"))


# ── Input ─────────────────────────────────────────────────────────────


class ChartDataExtractorInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded chart image (data URI prefix optional)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the chart image from",
    )
    chart_type: str = Field(
        "auto",
        description="Chart type hint: 'bar', 'line', 'pie', or 'auto'",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class ChartDataExtractorTool(BaseTool):
    """Extract numerical data from chart images using computer vision.

    Detects bar charts, line graphs, and pie charts. Uses contour analysis
    and color segmentation to identify data series and extract approximate
    numerical values.
    """

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="chart_data_extractor",
            name="Chart Data Extractor",
            description=(
                "Reverse-engineer data tables from bar charts, line graphs, "
                "and pie charts. Extracts labels, values, and data series "
                "from chart images using computer vision. ⭐ DIFFERENTIATOR"
            ),
            category="visual-reasoning-and-image-analysis",
            input_schema=ChartDataExtractorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["chart", "data", "extraction", "vision", "differentiator"],
            requires_auth=False,
            timeout_seconds=CHART_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ChartDataExtractorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if not validated.data and not validated.url:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'data' (base64) or 'url' must be provided",
            )

        if validated.chart_type not in ("auto", "bar", "line", "pie"):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown chart_type: '{validated.chart_type}'. Use 'auto', 'bar', 'line', or 'pie'.",
            )

        try:
            result = await self._extract_chart(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.warning("chart_data_extractor failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _extract_chart ───────────────────────────────────────────

    async def _extract_chart(self, validated: ChartDataExtractorInput) -> dict[str, Any]:
        """Load image and delegate to the appropriate chart extractor."""
        image_bytes = await resolve_input(validated.data, validated.url, label="chart image", fetch_timeout=30)

        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(pil_image)
        pil_image.close()

        chart_type = validated.chart_type
        if chart_type == "auto":
            chart_type = self._detect_chart_type(img_array)

        if chart_type == "bar":
            result = self._extract_bar_chart(img_array)
        elif chart_type == "line":
            result = self._extract_line_chart(img_array)
        elif chart_type == "pie":
            result = self._extract_pie_chart(img_array)
        else:
            chart_type = "unknown"
            result = {"error": "Could not determine chart type"}

        result["detected_type"] = chart_type
        result["image_size"] = {
            "width": img_array.shape[1],
            "height": img_array.shape[0],
        }
        return result

    # ── Chart type detection ─────────────────────────────────────

    def _detect_chart_type(self, img: np.ndarray) -> str:
        """Heuristic: analyze shape and color distribution to guess chart type."""
        gray = np.mean(img, axis=2).astype(np.uint8)

        # Compute gradients to detect edges
        gy = np.abs(np.diff(gray.astype(np.int16), axis=0))
        gx = np.abs(np.diff(gray.astype(np.int16), axis=1))

        # Bar charts have many vertical edges along the top of bars
        vertical_edge_ratio = np.mean(gy > 30) if gy.size > 0 else 0.0
        horizontal_edge_ratio = np.mean(gx > 30) if gx.size > 0 else 0.0

        # Pie charts are more radial / have curved edges
        # Simple heuristic: look at edge distribution uniformity
        h, w = gray.shape
        center_region = gray[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
        center_brightness = np.mean(center_region) if center_region.size > 0 else 128

        # Color variance — pie charts tend to have more distinct color regions
        color_var = np.std(img, axis=(0, 1)).mean()

        if vertical_edge_ratio > horizontal_edge_ratio * 2:
            return "bar"
        elif color_var > 60:
            return "pie"
        else:
            return "line"

    # ── Bar chart extraction ─────────────────────────────────────

    def _extract_bar_chart(self, img: np.ndarray) -> dict[str, Any]:
        """Extract bar heights and relative values from a bar chart."""
        gray = np.mean(img, axis=2).astype(np.uint8)
        h, w = gray.shape

        # Find the baseline (darkest horizontal region in bottom third)
        bottom = gray[2 * h // 3 :, :]
        row_means = np.mean(bottom, axis=1)
        baseline_row = 2 * h // 3 + int(np.argmin(row_means))

        # Find vertical columns by looking for dark-to-light transitions
        # above the baseline in horizontal projection
        above_baseline = gray[:baseline_row, :]
        col_means = np.mean(above_baseline, axis=0)

        # Detect bars: columns with brightness above background
        bg_level = np.median(col_means)
        threshold = bg_level + 0.05 * (255 - bg_level)

        # Find contiguous bright regions (bars)
        in_bar = False
        bar_regions: list[tuple[int, int]] = []
        start = 0
        for x in range(w):
            is_bright = col_means[x] > threshold
            if is_bright and not in_bar:
                start = x
                in_bar = True
            elif not is_bright and in_bar:
                if x - start >= 5:  # minimum bar width
                    bar_regions.append((start, x))
                in_bar = False
        if in_bar and w - start >= 5:
            bar_regions.append((start, w))

        # Compute bar heights as bright pixel count above baseline
        bars = []
        max_height = 0.0

        for x1, x2 in bar_regions:
            bar_slice = gray[:baseline_row, x1:x2]
            # Brightness level of the bar region
            bar_brightness = np.mean(bar_slice)
            # Estimate height: how much of this column is bar vs background
            bright_pixels = np.sum(bar_slice > bg_level + 20)
            bar_area = bar_slice.size
            height_ratio = bright_pixels / max(bar_area, 1)
            bars.append(
                {
                    "x_start": x1,
                    "x_end": x2,
                    "center_x": (x1 + x2) // 2,
                    "relative_value": round(height_ratio, 4),
                    "brightness": round(float(bar_brightness), 1),
                }
            )
            max_height = max(max_height, height_ratio)

        # Normalize to 0-100 scale
        for bar in bars:
            bar["normalized_value"] = round((bar["relative_value"] / max_height) * 100, 1) if max_height > 0 else 0.0

        return {
            "chart_type": "bar",
            "bars_count": len(bars),
            "bars": bars,
            "baseline_y": baseline_row,
            "method": "column-projection",
            "confidence": "medium",
        }

    # ── Line chart extraction ────────────────────────────────────

    def _extract_line_chart(self, img: np.ndarray) -> dict[str, Any]:
        """Extract data points from a line chart using edge detection."""
        gray = np.mean(img, axis=2).astype(np.uint8)
        h, w = gray.shape

        # Detect line pixels using horizontal gradient
        gy = np.abs(np.diff(gray.astype(np.int16), axis=0))
        gy = np.pad(gy, ((1, 0), (0, 0)), mode="edge")

        # Find the line: for each x, find the y with the most edges
        points = []
        for x in range(w):
            col = gy[:, x]
            # Find peaks in gradient (line edges)
            threshold = np.percentile(col, 95)
            strong_edges = np.where(col > threshold)[0]
            if len(strong_edges) > 0:
                y = int(np.median(strong_edges))
                points.append({"x": x, "y": y, "intensity": float(col[y])})

        if not points:
            return {"chart_type": "line", "points": [], "error": "No line detected"}

        # Normalize y values (invert since image coordinates go down)
        y_values = np.array([p["y"] for p in points])
        y_min, y_max = y_values.min(), y_values.max()
        y_range = y_max - y_min or 1

        for p in points:
            p["normalized_value"] = round((1.0 - (p["y"] - y_min) / y_range) * 100, 1)

        # Downsample to ~20 representative points
        if len(points) > 20:
            step = len(points) // 20
            points = [points[i] for i in range(0, len(points), step)]

        return {
            "chart_type": "line",
            "points_count": len(points),
            "points": points,
            "method": "gradient-peak-detection",
            "confidence": "low",
        }

    # ── Pie chart extraction ─────────────────────────────────────

    def _extract_pie_chart(self, img: np.ndarray) -> dict[str, Any]:
        """Extract segment proportions from a pie chart using color segmentation."""
        h, w = img.shape[:2]

        # Find pie center and radius
        gray = np.mean(img, axis=2).astype(np.uint8)

        # Threshold to find the pie (bright region on dark bg)
        if cv2 is None:
            return {
                "chart_type": "pie",
                "segments": [],
                "error": "OpenCV not available",
            }

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Find contours to locate the pie circle
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return {
                "chart_type": "pie",
                "segments": [],
                "error": "No pie contour found",
            }

        # Use largest contour as pie outline
        largest = max(contours, key=cv2.contourArea)
        center, radius = cv2.minEnclosingCircle(largest)
        cx, cy = int(center[0]), int(center[1])
        radius = int(radius * 0.8)  # shrink slightly to avoid edges

        # Sample colors around the pie center at different angles
        segments = []
        num_samples = 72  # every 5 degrees
        current_color = None
        segment_start = 0
        segment_pixels = 0
        total_pixels = 0

        for i in range(num_samples):
            angle = (i / num_samples) * 2 * np.pi - np.pi / 2
            sx = int(cx + radius * 0.6 * np.cos(angle))
            sy = int(cy + radius * 0.6 * np.sin(angle))

            if 0 <= sx < w and 0 <= sy < h:
                pixel = tuple(img[sy, sx] // 32 * 32)  # quantize color
                total_pixels += 1

                if pixel != current_color:
                    if current_color is not None and segment_pixels > 0:
                        pct = round(segment_pixels / max(total_pixels, 1) * 100, 1)
                        segments.append(
                            {
                                "start_angle": round(segment_start * 5, 1),
                                "end_angle": round(i * 5, 1),
                                "percentage": pct,
                                "color_rgb": list(current_color),
                            }
                        )
                    current_color = pixel
                    segment_start = i
                    segment_pixels = 1
                else:
                    segment_pixels += 1

        # Final segment
        if current_color is not None and segment_pixels > 0:
            pct = round(segment_pixels / max(total_pixels, 1) * 100, 1)
            segments.append(
                {
                    "start_angle": round(segment_start * 5, 1),
                    "end_angle": 360.0,
                    "percentage": pct,
                    "color_rgb": list(current_color),
                }
            )

        return {
            "chart_type": "pie",
            "segments_count": len(segments),
            "segments": segments,
            "center": {"x": cx, "y": cy},
            "radius": radius,
            "method": "color-segmentation",
            "confidence": "medium",
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(ChartDataExtractorTool())
