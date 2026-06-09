"""
LLM Tools — Agent-callable tools for text processing via the local LLM.

llm_summarize   → concise summary of input text
llm_translate   → translate text to a target language
llm_classify    → classify text into one of the provided categories

All tools call the local llama.cpp server via its OpenAI-compatible API.
"""

from __future__ import annotations

import logging

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared LLM caller
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "Qwen3.6-27B-Q5_K_M-mtp.gguf"
_TIMEOUT_SECONDS = 60


async def _call_llm(messages: list[dict], temperature: float = 0.3) -> str:
    """Send a chat-completion request to the local llama.cpp server."""
    from app.config import settings

    url = f"{settings.LLAMACPP_URL}/v1/chat/completions"
    payload = {
        "model": _DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    return data["choices"][0]["message"]["content"].strip()


# ── llm_summarize ────────────────────────────────────────────────────


class LLMSummarizeInput(ToolInput):
    text: str = Field(..., description="Text to summarize")
    max_sentences: int = Field(
        3, description="Maximum number of sentences in the summary"
    )


class LLMSummarizeTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="llm_summarize",
            name="LLM Summarize",
            description="Produce a concise summary of the given text",
            category="llm",
            input_schema=LLMSummarizeInput.schema_extra(),
            tags=["llm", "summarize", "text"],
            requires_auth=True,
            timeout_seconds=90,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = LLMSummarizeInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a precise summarization assistant. "
                        "Produce a clear, factual summary in at most the requested number of sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Summarize the following text in at most {validated.max_sentences} sentences:\n\n"
                        f"{validated.text}"
                    ),
                },
            ]
            summary = await _call_llm(messages)
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={"summary": summary},
            )
        except Exception as e:
            logger.exception("llm_summarize failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── llm_translate ────────────────────────────────────────────────────


class LLMTranslateInput(ToolInput):
    text: str = Field(..., description="Text to translate")
    target_language: str = Field(
        ..., description="Target language name or code (e.g. 'French', 'ja', 'German')"
    )


class LLMTranslateTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="llm_translate",
            name="LLM Translate",
            description="Translate text to a target language",
            category="llm",
            input_schema=LLMTranslateInput.schema_extra(),
            tags=["llm", "translate", "text"],
            requires_auth=True,
            timeout_seconds=90,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = LLMTranslateInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a professional translator. "
                        "Translate the user's text into the requested language. "
                        "Return ONLY the translated text, nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Translate the following text to {validated.target_language}:\n\n{validated.text}"
                    ),
                },
            ]
            translation = await _call_llm(messages)
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "translation": translation,
                    "target_language": validated.target_language,
                },
            )
        except Exception as e:
            logger.exception("llm_translate failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── llm_classify ─────────────────────────────────────────────────────


class LLMClassifyInput(ToolInput):
    text: str = Field(..., description="Text to classify")
    categories: list[str] = Field(
        ..., description="List of possible category labels", min_length=2
    )


class LLMClassifyTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="llm_classify",
            name="LLM Classify",
            description="Classify text into one of the provided categories",
            category="llm",
            input_schema=LLMClassifyInput.schema_extra(),
            tags=["llm", "classify", "text"],
            requires_auth=True,
            timeout_seconds=90,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = LLMClassifyInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            cat_list = ", ".join(validated.categories)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a text classifier. "
                        "Classify the user's text into exactly one of the provided categories. "
                        "Return ONLY the category label, nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Categories: [{cat_list}]\n\nClassify the following text:\n\n{validated.text}"
                    ),
                },
            ]
            label = await _call_llm(messages, temperature=0.0)

            # Normalise: strip quotes / whitespace, match against original list
            label_clean = label.strip().strip('"').strip("'")
            matched = next(
                (c for c in validated.categories if c.lower() == label_clean.lower()),
                label_clean,
            )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "category": matched,
                    "raw_response": label,
                },
            )
        except Exception as e:
            logger.exception("llm_classify failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── Register ─────────────────────────────────────────────────────────

register_tool(LLMSummarizeTool())
register_tool(LLMTranslateTool())
register_tool(LLMClassifyTool())
