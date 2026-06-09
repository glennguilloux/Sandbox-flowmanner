"""
Writing & Content Generation Tools — Tone Adjuster.

tone_adjuster → Rewrite paragraphs to be more professional, casual, or urgent.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# Available tones with descriptions
TONES: dict[str, str] = {
    "professional": "Formal, polished, business-appropriate language",
    "casual": "Relaxed, conversational, friendly tone",
    "urgent": "Direct, time-sensitive, action-oriented language",
    "empathetic": "Warm, understanding, supportive tone",
    "persuasive": "Compelling, convincing, sales-oriented language",
    "technical": "Precise, detail-focused, expert terminology",
    "simplified": "Clear, accessible language for a general audience",
    "enthusiastic": "Energetic, excited, upbeat tone",
    "diplomatic": "Tactful, balanced, politically sensitive language",
    "humorous": "Light-hearted, witty, entertaining tone",
    "academic": "Scholarly, research-oriented, citation-appropriate tone",
    "authoritative": "Confident, commanding, expert-voice tone",
}


class ToneAdjusterInput(ToolInput):
    text: str = Field(
        ...,
        description="The text to rewrite",
    )
    target_tone: str = Field(
        "professional",
        description=f"Target tone for the rewrite. Options: {', '.join(sorted(TONES))}",
    )
    preserve_length: bool = Field(
        True,
        description="Keep the output roughly the same length as input",
    )
    custom_instructions: str | None = Field(
        None,
        description="Additional tone/style instructions to append",
    )


class ToneAdjusterTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="tone_adjuster",
            name="Tone Adjuster",
            description="Rewrite paragraphs to be more professional, casual, or urgent",
            category="writing-content",
            input_schema=ToneAdjusterInput.schema_extra(),
            tags=["writing", "tone", "rewrite", "style", "content"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ToneAdjusterInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        target_tone = validated.target_tone.lower().strip()
        if target_tone not in TONES:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown tone '{target_tone}'. Options: {', '.join(sorted(TONES))}",
            )

        tone_description = TONES[target_tone]
        text = validated.text.strip()
        if not text:
            return ToolResult.error_result(tool_id=self.tool_id, error="Text is empty")

        try:
            import openai

            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL")
            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = openai.AsyncOpenAI(**client_kwargs)

            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

            system_prompt = f"Rewrite the following text in a {target_tone} tone. {tone_description}. "
            if validated.preserve_length:
                system_prompt += (
                    "Keep the output approximately the same length as the input. "
                )
            if validated.custom_instructions:
                system_prompt += (
                    f"Additional instructions: {validated.custom_instructions}"
                )

            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.7,
                max_tokens=4096,
            )

            rewritten = response.choices[0].message.content or ""

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "original_tone": "original",
                    "target_tone": target_tone,
                    "tone_description": tone_description,
                    "original_text": text,
                    "rewritten_text": rewritten,
                    "original_length": len(text),
                    "rewritten_length": len(rewritten),
                    "model": model,
                    "tokens_used": response.usage.total_tokens if response.usage else 0,
                },
            )

        except Exception as e:
            logger.exception("tone_adjuster failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

register_tool(ToneAdjusterTool())
