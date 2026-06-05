"""
Writing & Content Generation Tools — Blog Post Expander.

blog_post_expander → Expand short outlines into complete, formatted blog sections.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class BlogPostExpanderInput(ToolInput):
    outline: str = Field(
        ...,
        description="A short outline or bullet list of topics to expand into full sections",
    )
    tone: str = Field(
        "professional",
        description="Writing tone: 'professional', 'casual', 'technical', 'thought-leadership'",
    )
    target_audience: str = Field(
        "general",
        description="Target audience: 'general', 'technical', 'executive', 'beginner'",
    )
    section_count: int = Field(
        3,
        ge=1,
        le=10,
        description="Number of sections to generate",
    )
    include_intro: bool = Field(
        True,
        description="Include an introductory paragraph",
    )
    include_conclusion: bool = Field(
        True,
        description="Include a concluding paragraph",
    )
    include_seo_title: bool = Field(
        True,
        description="Generate an SEO-optimized title",
    )


AUDIENCE_CONTEXT: dict[str, str] = {
    "general": "Write for a general audience. Use clear language, avoid jargon, and explain concepts simply.",
    "technical": "Write for a technical audience. Use precise terminology, include implementation details, and assume domain knowledge.",
    "executive": "Write for executives and decision-makers. Focus on business value, strategy, and high-level impact.",
    "beginner": "Write for beginners. Explain everything from first principles, use analogies, and avoid assuming prior knowledge.",
}

TONE_CONTEXT: dict[str, str] = {
    "professional": "Professional, polished, and authoritative.",
    "casual": "Relaxed, conversational, and approachable.",
    "technical": "Precise, detailed, and data-driven.",
    "thought-leadership": "Insightful, visionary, and opinionated with original perspectives.",
}


class BlogPostExpanderTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="blog_post_expander",
            name="Blog Post Expander",
            description="Expand short outlines into complete, formatted blog sections",
            category="writing-content",
            input_schema=BlogPostExpanderInput.schema_extra(),
            tags=["writing", "blog", "expand", "content", "seo"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = BlogPostExpanderInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.outline.strip():
            return ToolResult.error_result(
                tool_id=self.tool_id, error="Outline is empty"
            )

        audience_context = AUDIENCE_CONTEXT.get(
            validated.target_audience.lower(), AUDIENCE_CONTEXT["general"]
        )
        tone_context = TONE_CONTEXT.get(
            validated.tone.lower(), TONE_CONTEXT["professional"]
        )

        try:
            import openai

            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL")
            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = openai.AsyncOpenAI(**client_kwargs)

            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

            # Build the prompt
            parts = []
            parts.append(f"Expand the following outline into {validated.section_count} full blog sections.")
            if validated.include_intro:
                parts.append("Include an engaging introductory paragraph.")
            if validated.include_conclusion:
                parts.append("Include a strong concluding paragraph.")
            parts.append(f"Tone: {tone_context}")
            parts.append(f"Audience: {audience_context}")
            if validated.include_seo_title:
                parts.append("Also generate an SEO-optimized title for this blog post.")
            parts.append("Format the output in Markdown with proper headings (## for sections).")
            parts.append(f"\nOutline:\n{validated.outline}")

            system_prompt = (
                "You are an expert blog writer. Expand outlines into well-structured, "
                "engaging blog posts. Use Markdown formatting. Each section should be "
                "substantive with 2-4 paragraphs."
            )

            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n".join(parts)},
                ],
                temperature=0.7,
                max_tokens=4096,
            )

            content = response.choices[0].message.content or ""

            # Extract title if SEO title was requested
            seo_title = None
            if validated.include_seo_title and content:
                lines = content.strip().split("\n")
                # First line might be the title
                first_line = lines[0].strip()
                if first_line.startswith("# "):
                    seo_title = first_line[2:].strip()
                elif first_line and not first_line.startswith("##"):
                    seo_title = first_line

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "outline": validated.outline,
                    "tone": validated.tone,
                    "target_audience": validated.target_audience,
                    "sections": validated.section_count,
                    "has_intro": validated.include_intro,
                    "has_conclusion": validated.include_conclusion,
                    "seo_title": seo_title,
                    "content": content,
                    "word_count": len(content.split()),
                    "model": model,
                    "tokens_used": response.usage.total_tokens if response.usage else 0,
                },
            )

        except Exception as e:
            logger.exception("blog_post_expander failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

register_tool(BlogPostExpanderTool())
