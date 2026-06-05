"""
Finance & Data Analysis Tools — Expense Receipt Parser.

expense_receipt_parser → Extract vendor, date, line items, tax, and totals
    from scanned receipts using OpenAI Vision (GPT-4o-mini by default).
    Accepts base64-encoded images or publicly-accessible image URLs.
    ⭐ Differentiator tool — no other agent platform offers this natively.
"""

from __future__ import annotations

import base64
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

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")
RECEIPT_TIMEOUT = int(os.getenv("RECEIPT_TIMEOUT", "60"))


def _media_type_for(header_bytes: bytes) -> str:
    """Detect image media type from magic bytes."""
    if header_bytes[:4] == b"\x89PNG":
        return "image/png"
    if header_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if header_bytes[:3] == b"GIF":
        return "image/gif"
    if (
        len(header_bytes) >= 12
        and header_bytes[:4] == b"RIFF"
        and header_bytes[8:12] == b"WEBP"
    ):
        return "image/webp"
    return "image/jpeg"  # default


# ── Input ─────────────────────────────────────────────────────────────


class ExpenseReceiptParserInput(ToolInput):
    image_data: str | None = Field(
        None,
        description="Base64-encoded receipt image data (raw bytes or data URI). Required if image_url not provided.",
    )
    image_url: str | None = Field(
        None,
        description="Publicly-accessible URL to the receipt image. Required if image_data not provided.",
    )
    pdf_data: str | None = Field(
        None,
        description="Base64-encoded PDF receipt data. At least one of image_data, image_url, or pdf_data must be provided.",
    )
    detail: str = Field(
        "high",
        description="Vision API detail level: 'low', 'high', or 'auto'. Use 'high' for receipts.",
    )
    model: str | None = Field(
        None,
        description=f"OpenAI Vision model override (default: {VISION_MODEL})",
    )
    language: str = Field(
        "en",
        description="Receipt language for OCR (ISO 639-1 code, e.g. 'en', 'fr', 'de')",
    )
    extract_line_items: bool = Field(
        True,
        description="Whether to extract individual line items from the receipt",
    )
    categorize: bool = Field(
        True,
        description="Whether to auto-categorize the expense",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class ExpenseReceiptParserTool(BaseTool):
    """Extract structured data from receipt images via OpenAI Vision."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="expense_receipt_parser",
            name="Expense Receipt Parser",
            description=(
                "Extract vendor, date, totals, line items, tax, and currency from "
                "scanned receipt images or photos using OpenAI Vision. Accepts "
                "base64-encoded images or public image URLs. Requires OPENAI_API_KEY "
                "env var. ⭐ Differentiator tool."
            ),
            category="finance-data-analysis",
            input_schema=ExpenseReceiptParserInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "date": {"type": "string"},
                    "total": {"type": "number"},
                    "tax": {"type": "number"},
                    "currency": {"type": "string"},
                    "line_items": {"type": "array"},
                    "raw_text": {"type": "string"},
                },
            },
            tags=[
                "receipt",
                "ocr",
                "finance",
                "expense",
                "vision",
                "differentiator",
                "accounting",
                "bookkeeping",
            ],
            requires_auth=True,
            timeout_seconds=RECEIPT_TIMEOUT + 20,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ExpenseReceiptParserInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if (
            not validated.image_data
            and not validated.image_url
            and not validated.pdf_data
        ):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="At least one of 'image_data' (base64 image), 'image_url' (image URL), or 'pdf_data' (base64 PDF) must be provided.",
            )

        api_key = os.getenv("OPENAI_API_KEY", "")

        if not api_key:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="OpenAI not configured. Set OPENAI_API_KEY env var.",
            )

        if is_placeholder(api_key):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="OpenAI not configured. Replace placeholder value for "
                "OPENAI_API_KEY with a real API key from https://platform.openai.com/api-keys",
            )

        if validated.detail not in ("low", "high", "auto"):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="detail must be 'low', 'high', or 'auto'",
            )

        try:
            result = await self._parse_receipt(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("OpenAI Vision API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"OpenAI Vision API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("expense_receipt_parser failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _parse_receipt ───────────────────────────────────────────

    async def _parse_receipt(
        self, validated: ExpenseReceiptParserInput
    ) -> dict[str, Any]:
        """Build the vision API payload and call it."""
        # Resolve image to a data URI
        data_uri = await self._resolve_data_uri(validated)

        # Build the structured extraction prompt
        prompt = (
            "You are a precise receipt data extractor. Analyze this receipt image "
            "and return ONLY a JSON object (no markdown, no explanation) with these keys:\n"
            "- vendor: string — the merchant/store name\n"
            "- date: string — receipt date in YYYY-MM-DD format (infer if ambiguous)\n"
            "- total: number — the total amount paid (after tax/tip)\n"
            "- subtotal: number — pre-tax amount (null if not shown)\n"
            "- tax: number — tax amount (null if not shown)\n"
            "- tip: number — tip/gratuity (null if not shown)\n"
            "- currency: string — 3-letter ISO code (e.g. USD, EUR) or symbol (e.g. $, €)\n"
            "- line_items: array of {description: string, quantity: number, unit_price: number, amount: number}\n"
            "- payment_method: string — last 4 digits if card, or 'cash', 'unknown'\n"
            "- category: string — best guess at expense category (meals, travel, office supplies, etc.)\n"
            "\n"
            "Rules:\n"
            "- If you cannot read a field, set it to null (not 'N/A' or empty string)\n"
            "- For multi-currency receipts, note the primary currency\n"
            "- If totals are handwritten and ambiguous, make your best guess and set a "
            "'confidence' field: 'high', 'medium', or 'low'\n"
            "- Return valid JSON only. No other text."
        )

        model = validated.model or VISION_MODEL
        payload = {
            "model": model,
            "messages": [
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
                }
            ],
            "max_tokens": 1024,
            "temperature": 0,
        }

        # Call OpenAI Vision API
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=RECEIPT_TIMEOUT) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            try:
                api_result = resp.json()
                content = api_result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                logger.error("Unexpected OpenAI Vision response shape: %s", api_result)
                return {
                    "parse_error": True,
                    "raw_response": str(api_result)[:500],
                    "error": f"Unexpected API response: {e}",
                }

        # Parse the JSON from the response
        import json

        try:
            # Strip any markdown fences if present
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()
                if clean.startswith("json"):
                    clean = clean[4:].strip()
            receipt_data = json.loads(clean)
        except json.JSONDecodeError:
            # Return raw text as fallback
            receipt_data = {"raw_text": content, "parse_error": True}

        return {
            **receipt_data,
            "model": api_result.get("model", model),
            "usage": api_result.get("usage", {}),
        }

    # ── _resolve_data_uri ────────────────────────────────────────

    async def _resolve_data_uri(self, validated: ExpenseReceiptParserInput) -> str:
        """Convert input to a data: URI for the Vision API."""
        if validated.image_url:
            # Fetch image from URL
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(validated.image_url)
                resp.raise_for_status()
                image_bytes = resp.content
            media_type = _media_type_for(image_bytes[:16])
        elif validated.pdf_data:
            # Use PDF directly as data URI
            raw = validated.pdf_data
            if raw.startswith("data:"):
                return raw
            image_bytes = base64.b64decode(raw.strip())
            return f"data:application/pdf;base64,{base64.b64encode(image_bytes).decode('ascii')}"
        elif validated.image_data:
            # Decode base64
            raw = validated.image_data
            # Handle data URI prefix
            if raw.startswith("data:"):
                return raw
            # Clean base64 padding
            raw = raw.strip().rstrip("=")
            # Add padding back
            padding = 4 - len(raw) % 4
            if padding != 4:
                raw += "=" * padding
            try:
                image_bytes = base64.b64decode(raw)
            except Exception:
                # Try with standard padding
                image_bytes = base64.b64decode(validated.image_data.strip())
            media_type = _media_type_for(image_bytes[:16])
        else:
            raise ValueError("No image data provided")

        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{media_type};base64,{b64}"


# ── Register ──────────────────────────────────────────────────────────

register_tool(ExpenseReceiptParserTool())
