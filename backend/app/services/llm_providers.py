from __future__ import annotations

"""LLM provider resolution — pure leaf module extracted from chat_service.py.

Phase 0.1 of the Chat Wiring Sprint (Round 2).  Every function here is a
pure lookup / normalisation — no back-references to the chat_service
orchestrator.  chat_service.py imports these symbols instead of defining
them inline.

Moved functions (all signatures + return shapes preserved exactly):
  - PROVIDER_MAP
  - OPENAI_PROVIDER_FAMILIES
  - _normalize_provider
  - _get_base_url_for_provider
  - _get_provider_for_model
  - _get_upstream_model_name
  - _resolve_provider
  - _detect_provider_from_key
  - _providers_compatible
"""

import os

from app.config import settings

# ── LLM defaults (shared by provider resolution and chat_service client creation) ──
_LLM_API_KEY = os.getenv("LLM_API_KEY")
_LLM_API_BASE = os.getenv("LLM_API_BASE") or os.getenv("LLM_BASE_URL") or "https://api.deepseek.com/v1"
_LLM_MODEL = os.getenv("LLM_MODEL_NAME", "deepseek/deepseek-v4-flash")

PROVIDER_MAP: dict[str, tuple[str, str | None]] = {
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "zhipuai": ("https://open.bigmodel.cn/api/paas/v4", "ZHIPUAI_API_KEY"),
    "llamacpp": (f"{settings.LLAMACPP_URL}/v1", None),
    "llamacpp_light": (f"{settings.LLAMACPP_LIGHT_URL}/v1", None),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
    "deepinfra": ("https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "google": ("https://generativelanguage.googleapis.com/v1beta", "GOOGLE_API_KEY"),
    "openai_compatible": ("https://api.openai.com/v1", None),
    "glennguilloux": ("https://ai.glennguilloux.com:9443/v1", None),
}

OPENAI_PROVIDER_FAMILIES = frozenset(("openai", "openai_compatible"))


def _normalize_provider(provider: str) -> str:
    """Normalize provider name to canonical form.

    Handles both underscore and hyphen variants:
    - openai_compatible -> openai_compatible
    - openai-compatible -> openai_compatible
    - openai -> openai
    """
    if not provider:
        return provider
    return provider.lower().replace("-", "_")


def _get_base_url_for_provider(provider: str) -> str:
    """Get base URL for a normalized provider."""
    normalized = _normalize_provider(provider)

    if normalized == "openai_compatible":
        return "https://api.openai.com/v1"

    base_url, _ = PROVIDER_MAP.get(normalized, (None, None))
    if base_url:
        return base_url

    return _LLM_API_BASE


def _get_provider_for_model(model_id: str) -> str | None:
    """Extract normalized provider from model ID (e.g., 'llamacpp/qwen' -> 'llamacpp')."""
    if "/" not in model_id:
        return None
    return _normalize_provider(model_id.split("/", 1)[0])


def _get_upstream_model_name(model_id: str) -> str:
    """Extract the upstream model name to send to the API.

    Strips provider prefix but preserves nested paths:
    - openai/gpt-4o-mini -> gpt-4o-mini
    - openai_compatible/gpt-4o-mini-2024-07-18 -> gpt-4o-mini-2024-07-18
    - openai-compatible/gpt-4o-mini -> gpt-4o-mini
    - openrouter/anthropic/claude-3.5-sonnet -> anthropic/claude-3.5-sonnet
    - gpt-4o-mini -> gpt-4o-mini (no prefix)
    """
    if "/" not in model_id:
        return model_id
    return model_id.split("/", 1)[1]


def _resolve_provider(model_id: str) -> tuple[str, str, str]:
    """Resolve provider details for a model ID.

    Returns (base_url, api_key, upstream_model_name)
    """
    upstream_model = _get_upstream_model_name(model_id)
    provider = _get_provider_for_model(model_id)

    if not provider:
        return _LLM_API_BASE, _LLM_API_KEY, upstream_model

    normalized = _normalize_provider(provider)

    if normalized == "openai_compatible":
        return "https://api.openai.com/v1", None, upstream_model

    base_url, key_env = PROVIDER_MAP.get(normalized, (None, None))
    if not base_url:
        return _LLM_API_BASE, _LLM_API_KEY, upstream_model

    api_key = os.getenv(key_env) if key_env else "not-needed"
    return base_url, api_key, upstream_model


def _detect_provider_from_key(api_key: str) -> str | None:
    """Detect provider from BYOK key format.

    Covers distinct key-prefix families across 11 providers.
    Generic / ambiguous prefixes return None (no mismatch enforced).
    """
    if not api_key:
        return None
    key_lower = api_key.lower()
    if key_lower.startswith("sk-or-"):
        return "openrouter"
    if key_lower.startswith("sk-ds-"):
        return "deepseek"
    if key_lower.startswith("sk-ant-"):
        return "anthropic"
    if key_lower.startswith("sk-proj-"):
        return "openai"
    if key_lower.startswith("aiza"):
        return "google"
    if key_lower.startswith("gsk_"):
        return "groq"
    if key_lower.startswith("fw_"):
        return "fireworks"
    if key_lower.startswith("xai-"):
        return "xai"
    # Generic "sk-" is shared by OpenAI, Together, DeepInfra, and others.
    # Returning None avoids false mismatch errors.
    return None


def _providers_compatible(key_provider: str | None, model_provider: str | None) -> bool:
    """Check if a key provider is compatible with a model provider family."""
    if not key_provider or not model_provider:
        return True
    key_p = _normalize_provider(key_provider)
    model_p = _normalize_provider(model_provider) if model_provider else None
    if not model_p:
        return True
    if model_p in ("llamacpp", "ollama"):
        return True
    if key_p == model_p:
        return True
    return bool(model_p in OPENAI_PROVIDER_FAMILIES and key_p in OPENAI_PROVIDER_FAMILIES)
