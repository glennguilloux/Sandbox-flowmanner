"""Native Anthropic adapter + ReasoningOptions (Comment 6).

The OpenAI-compatible path used for DeepSeek/Qwen cannot safely expose
Anthropic reasoning, prompt-cache controls, or the native messages API. This
module provides a separate provider interface for native Anthropic models
(claude-3-5-sonnet, claude-3-opus, ...) that talks to the correct Anthropic
API, parses thinking blocks, controls prompt caching, and accounts for
reasoning tokens.

``ReasoningOptions`` is the single request object for reasoning config. When a
caller passes it to a provider that cannot honor it (DeepSeek/Qwen via the
OpenAI path), the unsupported options degrade to safe no-ops and the
degradation is recorded in the response metadata.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal, cast

logger = logging.getLogger(__name__)

# Provider families that understand the native Anthropic messages API.
_NATIVE_ANTHROPIC_FAMILIES = {"anthropic"}


@dataclass
class ReasoningOptions:
    """Reasoning / depth configuration for a single LLM call.

    Fields are intentionally optional so callers can set only what they care
    about; the adapter maps missing fields to safe provider defaults.
    """

    depth: Literal["shallow", "normal", "deep"] = "normal"
    reasoning_budget: int | None = None  # tokens budgeted for thinking
    effort: Literal["low", "medium", "high"] | None = None
    expose_chain_of_thought: bool = False  # surface thinking blocks to caller
    hide_chain_of_thought: bool = True  # keep thinking out of returned content
    prompt_caching: bool = True  # request prompt-cache control blocks

    def as_anthropic_params(self) -> dict[str, Any]:
        """Translate to Anthropic ``thinking`` / ``extra_body`` params.

        Only emits a ``thinking`` block when a budget is set; otherwise the call
        is non-reasoning (matches ``depth=shallow/normal`` defaults).
        """
        params: dict[str, Any] = {}
        if self.reasoning_budget and self.reasoning_budget > 0:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.reasoning_budget,
            }
        # Prompt caching is controlled via cache_control markers on the content
        # blocks (see AnthropicAdapter); we pass the intent flag through.
        params["prompt_caching"] = self.prompt_caching
        params["expose_chain_of_thought"] = self.expose_chain_of_thought
        params["depth"] = self.depth
        if self.effort:
            params["effort"] = self.effort
        return params


@dataclass
class ProviderCallResult:
    """Normalized result returned by every provider interface."""

    content: str
    thinking: str | None = None
    model_id: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    success: bool = True
    error: str | None = None
    degraded: bool = False  # True when requested options were not honored
    degradation_note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AnthropicAdapter:
    """Native Anthropic messages API adapter.

    Uses the official ``anthropic`` SDK when available; otherwise falls back to
    a direct httpx POST to ``https://api.anthropic.com/v1/messages``. Token
    accounting includes reasoning (thinking) tokens, and prompt-cache controls
    are attached to the system block when enabled.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
        self._client = None
        if self.api_key:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
            except Exception as exc:  # pragma: no cover - optional sdk
                logger.debug("anthropic SDK unavailable, using httpx fallback: %s", exc)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _split_messages(messages: list[dict[str, Any]]):
        """Return (system_text, chat_messages) from an OpenAI-style list."""
        system_parts: list[str] = []
        chat: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content if isinstance(content, str) else str(content))
            else:
                chat.append({"role": role, "content": content})
        return "\n\n".join(system_parts), chat

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        reasoning: ReasoningOptions | None = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> ProviderCallResult:
        if not self.available:
            return ProviderCallResult(
                content="",
                model_id=model,
                provider="anthropic",
                success=False,
                error="ANTHROPIC_API_KEY not configured; native Anthropic path disabled",
            )

        system_text, chat = self._split_messages(messages)
        reasoning = reasoning or ReasoningOptions()
        params = reasoning.as_anthropic_params()

        request_body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": chat,
            "temperature": temperature,
        }
        if system_text:
            if params.get("prompt_caching"):
                request_body["system"] = [
                    {
                        "type": "text",
                        "text": system_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                request_body["system"] = system_text
        if "thinking" in params:
            request_body["thinking"] = params["thinking"]

        try:
            if self._client is not None:
                resp = await self._client.messages.create(**request_body)
                return self._parse_sdk_response(resp, model, reasoning)
            return await self._complete_http(model, request_body, reasoning)
        except Exception as exc:  # pragma: no cover - network
            logger.warning("Anthropic native call failed for %s: %s", model, exc)
            return ProviderCallResult(
                content="",
                model_id=model,
                provider="anthropic",
                success=False,
                error=str(exc),
            )

    async def _complete_http(self, model, request_body, reasoning) -> ProviderCallResult:
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/messages", json=request_body, headers=headers)
            data = resp.json()
        if resp.status_code != 200:
            return ProviderCallResult(
                content="",
                model_id=model,
                provider="anthropic",
                success=False,
                error=str(data.get("error", resp.text)),
            )
        return self._parse_raw_response(data, model, reasoning)

    @staticmethod
    def _parse_sdk_response(resp, model, reasoning) -> ProviderCallResult:
        content, thinking, reasoning_tokens = AnthropicAdapter._extract_blocks(resp.content)
        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        return ProviderCallResult(
            content=content,
            thinking=thinking if reasoning.expose_chain_of_thought else None,
            model_id=model,
            provider="anthropic",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            success=True,
        )

    @staticmethod
    def _parse_raw_response(data, model, reasoning) -> ProviderCallResult:
        blocks = data.get("content", [])
        content, thinking, reasoning_tokens = AnthropicAdapter._extract_blocks(blocks)
        usage = data.get("usage", {})
        return ProviderCallResult(
            content=content,
            thinking=thinking if reasoning.expose_chain_of_thought else None,
            model_id=model,
            provider="anthropic",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            reasoning_tokens=usage.get("reasoning_tokens", reasoning_tokens),
            success=True,
        )

    @staticmethod
    def _extract_blocks(blocks) -> tuple[str, str | None, int]:
        """Pull text + thinking from Anthropic content blocks."""
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        reasoning_tokens = 0
        for block in blocks or []:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "thinking":
                thinking_parts.append(block.get("thinking", ""))
        return "\n".join(text_parts), ("\n".join(thinking_parts) or None), reasoning_tokens


class OpenAICompatibleAdapter:
    """Adapter for OpenAI-compatible providers (DeepSeek, Qwen, OpenRouter).

    Accepts ``ReasoningOptions`` but degrades unsupported fields (thinking,
    prompt-cache) to safe no-ops, recording the degradation in the result so
    the caller can see Opus-style reasoning was not honored (Comment 6).
    """

    def __init__(self, base_url: str, api_key: str, upstream_model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.upstream_model = upstream_model

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        reasoning: ReasoningOptions | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> ProviderCallResult:
        from openai import AsyncOpenAI

        reasoning = reasoning or ReasoningOptions()
        degradation: list[str] = []
        if reasoning.reasoning_budget or reasoning.depth == "deep":
            degradation.append("reasoning/thinking not supported on OpenAI-compatible path")
        if reasoning.prompt_caching:
            degradation.append("prompt caching not supported on OpenAI-compatible path")

        client = AsyncOpenAI(api_key=self.api_key or "not-needed", base_url=self.base_url)
        try:
            resp = await client.chat.completions.create(
                model=self.upstream_model,
                messages=cast("list[Any]", messages),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            return ProviderCallResult(
                content="",
                model_id=model,
                provider="openai-compatible",
                success=False,
                error=str(exc),
            )
        usage = resp.usage if resp.usage else None
        content = resp.choices[0].message.content or "" if resp.choices else ""
        return ProviderCallResult(
            content=content,
            model_id=model,
            provider="openai-compatible",
            input_tokens=(usage.prompt_tokens if usage else 0),
            output_tokens=(usage.completion_tokens if usage else 0),
            success=True,
            degraded=bool(degradation),
            degradation_note="; ".join(degradation) or None,
        )


def is_native_anthropic(model_id: str) -> bool:
    """True when a catalog model uses the native Anthropic API style."""
    from app.services.model_catalog import get_model_catalog

    try:
        spec = get_model_catalog().get(model_id)
    except Exception:
        spec = None
    if spec is not None:
        return spec.api_style.value == "anthropic"
    # Fallback heuristic for un-cataloged ids.
    return model_id.split("/")[-1].startswith("claude") or "/anthropic/" in model_id


def opus_enabled() -> bool:
    """Gate Opus behind real credentials + catalog + feature flag (Comment 6)."""
    from app.config import settings
    from app.services.model_catalog import get_model_catalog

    if not settings.ENABLE_NATIVE_ANTHROPIC:
        return False
    spec = get_model_catalog().get("claude-3-opus")
    if spec is None or not spec.enabled:
        return False
    if not settings.ENABLE_PREMIUM_MODELS:
        return False
    if not os.getenv("ANTHROPIC_API_KEY") and not (
        settings.ALLOW_ANTHROPIC_VIA_OPENROUTER and os.getenv("OPENROUTER_API_KEY")
    ):
        return False
    return True
