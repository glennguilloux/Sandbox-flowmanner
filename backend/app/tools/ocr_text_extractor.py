"""
Visual Reasoning & Image Analysis Tools — OCR Text Extractor.

ocr_text_extractor → Extract text, bounding boxes, and confidence scores
    from images using Tesseract OCR.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

import pytesseract
from PIL import Image
from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
DEFAULT_LANGUAGE = os.getenv("OCR_DEFAULT_LANGUAGE", "eng")
DEFAULT_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "30.0"))
OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "60"))

# Configure tesseract binary path if set
if TESSERACT_CMD != "tesseract":
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


# ── Input ─────────────────────────────────────────────────────────────


class OcrTextExtractorInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded image data (data URI prefix optional)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the image from",
    )
    language: str = Field(
        DEFAULT_LANGUAGE,
        description="Tesseract language code(s), e.g. 'eng', 'eng+fra', 'jpn'",
    )
    confidence_threshold: float = Field(
        DEFAULT_CONFIDENCE,
        ge=0.0,
        le=100.0,
        description="Minimum confidence score (0-100) for returned words",
    )
    include_boxes: bool = Field(
        True,
        description="Include bounding box coordinates for each word",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class OcrTextExtractorTool(BaseTool):
    """Extract text and word-level data from images using Tesseract OCR."""

    def __init__(self):
        metadata = ToolMetadata(
            visibility="opt_in",
            tool_id="ocr_text_extractor",
            name="OCR Text Extractor",
            description=(
                "Extract raw text, word-level bounding boxes, and confidence "
                "scores from images using Tesseract OCR. Supports multiple "
                "languages and configurable confidence filtering."
            ),
            category="visual-reasoning-and-image-analysis",
            input_schema=OcrTextExtractorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["ocr", "image", "text", "tesseract", "extraction"],
            requires_auth=False,
            timeout_seconds=OCR_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = OcrTextExtractorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if not validated.data and not validated.url:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'data' (base64) or 'url' must be provided",
            )

        try:
            result = await self._extract_text(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.warning("ocr_text_extractor failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _extract_text ────────────────────────────────────────────

    async def _extract_text(self, validated: OcrTextExtractorInput) -> dict[str, Any]:
        """Run Tesseract OCR on the image and return structured results."""
        image_bytes = await resolve_input(validated.data, validated.url, label="image", fetch_timeout=30)

        image = Image.open(io.BytesIO(image_bytes))

        # Get full text
        full_text = pytesseract.image_to_string(image, lang=validated.language).strip()

        # Get word-level data with bounding boxes
        data = pytesseract.image_to_data(
            image,
            lang=validated.language,
            output_type=pytesseract.Output.DICT,
        )

        words = []
        total_confidence = 0.0
        word_count = 0

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:
                continue

            conf = float(data["conf"][i])
            if conf < validated.confidence_threshold:
                continue

            entry: dict[str, Any] = {
                "text": text,
                "confidence": round(conf, 1),
            }

            if validated.include_boxes:
                entry["bbox"] = {
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                }
                entry["block_num"] = data["block_num"][i]
                entry["line_num"] = data["line_num"][i]
                entry["word_num"] = data["word_num"][i]

            words.append(entry)
            total_confidence += conf
            word_count += 1

        img_width = image.width
        img_height = image.height
        image.close()

        avg_confidence = round(total_confidence / word_count, 1) if word_count > 0 else 0.0

        return {
            "full_text": full_text,
            "word_count": word_count,
            "average_confidence": avg_confidence,
            "language": validated.language,
            "words": words,
            "image_size": {"width": img_width, "height": img_height},
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(OcrTextExtractorTool())
