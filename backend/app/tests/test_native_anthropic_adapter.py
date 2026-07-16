"""Comment 6: native Anthropic/Opus path cannot go through OpenAI-compatible."""

import os

import pytest

from app.services.providers.anthropic_adapter import (
    AnthropicAdapter,
    OpenAICompatibleAdapter,
    ReasoningOptions,
    is_native_anthropic,
    opus_enabled,
)


def test_native_anthropic_detection():
    # catalog-based
    assert is_native_anthropic("claude-3-5-sonnet") is True
    assert is_native_anthropic("deepseek-v4-flash") is False
    # heuristic fallback
    assert is_native_anthropic("anthropic/claude-3-opus-20240229") is True


def test_opus_disabled_without_credentials_and_flags(monkeypatch):
    monkeypatch.setattr(os, "environ", {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_NATIVE_ANTHROPIC", False)
    monkeypatch.setattr(settings, "ENABLE_PREMIUM_MODELS", False)
    monkeypatch.setattr(settings, "ALLOW_ANTHROPIC_VIA_OPENROUTER", False)
    assert opus_enabled() is False


def test_opus_enabled_requires_flags_and_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from app.config import settings
    from app.services.model_catalog import get_model_catalog

    monkeypatch.setattr(settings, "ENABLE_NATIVE_ANTHROPIC", True)
    monkeypatch.setattr(settings, "ENABLE_PREMIUM_MODELS", True)
    # The catalog caches claude-3-opus as disabled; enable it in-memory so the
    # gate (env + flags + catalog) can return True.
    spec = get_model_catalog().get("claude-3-opus")
    object.__setattr__(spec, "enabled", True)
    assert opus_enabled() is True


def test_reasoning_options_anthropic_params():
    ro = ReasoningOptions(depth="deep", reasoning_budget=2048, expose_chain_of_thought=False)
    params = ro.as_anthropic_params()
    assert params["thinking"]["type"] == "enabled"
    assert params["thinking"]["budget_tokens"] == 2048


def test_anthropic_adapter_parses_thinking_blocks():
    # No SDK / no key -> graceful failure path (not OpenAI fallback).
    adapter = AnthropicAdapter(api_key=None)
    res = adapter  # ensure class imports
    assert hasattr(res, "complete")
    # Simulate parsing of Anthropic-style content blocks.
    content, thinking, _ = AnthropicAdapter._extract_blocks(
        [
            {"type": "thinking", "thinking": "let me reason"},
            {"type": "text", "text": "final answer"},
        ]
    )
    assert content == "final answer"
    assert thinking == "let me reason"


@pytest.mark.asyncio
async def test_openai_compatible_adapter_degrades_reasoning(monkeypatch):
    # Decouple from real network by stubbing AsyncOpenAI.
    import app.services.providers.anthropic_adapter as mod

    class _Usage:
        prompt_tokens = 10
        completion_tokens = 5

    class _Msg:
        content = "ok"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    class _Completions:
        async def create(self, **kwargs):
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    import openai as _openai

    monkeypatch.setattr(_openai, "AsyncOpenAI", lambda **kw: _Client(), raising=True)
    adapter = OpenAICompatibleAdapter(
        base_url="http://x", api_key="not-needed", upstream_model="deepseek/deepseek-v4-flash"
    )
    res = await adapter.complete(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "hi"}],
        reasoning=ReasoningOptions(depth="deep", reasoning_budget=1024),
    )
    assert res.success is True
    # Unsupported reasoning options degrade to safe no-ops, recorded.
    assert res.degraded is True
    assert "reasoning" in (res.degradation_note or "")
