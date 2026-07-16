#!/usr/bin/env python3
"""Model Router Service — AsyncOpenAI-based with BYOK support.

Routes LLM requests to the appropriate provider/model:
1. If model_preference specified, use that model
2. Otherwise check user's BYOK keys in DB
3. Fall back to system default provider (ZhipuAI GLM-4-Flash)
4. Support both dict-return (mission_executor) and LLMRouteResult (llm.py) interfaces
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from app.services.chat_service import (
    PROVIDER_MAP,
    _get_provider_for_model,
    _normalize_provider,
    _resolve_provider,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMRouteResult:
    model: str = ""
    provider: str = ""
    content: str = ""
    success: bool = False
    usage: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class ProviderStatus:
    name: str
    healthy: bool = True
    error_count: int = 0


def _make_client(base_url: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


class ModelRouter:
    def __init__(self, db_session=None, user_id: str | None = None):
        self.db = db_session
        self.user_id = user_id
        self._last_messages: list[dict[str, Any]] = []

    @staticmethod
    def _is_native_anthropic(model_id: str) -> bool:
        """Comment 6: route Anthropic-API-style models to the native adapter."""
        try:
            from app.services.providers.anthropic_adapter import is_native_anthropic

            return is_native_anthropic(model_id)
        except Exception:
            return False

    async def _route_native_anthropic(
        self,
        raw_model: str,
        messages: list[dict[str, Any]],
        *,
        reasoning=None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        user_id: str = "system",
        is_admin: bool = False,
    ) -> Any:
        """Dispatch a native-Anthropic model through the Anthropic adapter.

        Comment 6: Opus (and other native Anthropic models) require a real
        Anthropic key or an approved OpenRouter Anthropic route, and are gated
        by the catalog + feature flags. We never silently fall back to the
        OpenAI-compatible path for these models.
        """
        from app.config import settings
        from app.services.model_catalog import get_model_catalog
        from app.services.providers.anthropic_adapter import (
            AnthropicAdapter,
            OpenAICompatibleAdapter,
            ProviderCallResult,
            ReasoningOptions,
        )

        catalog = get_model_catalog()
        spec = catalog.get(raw_model)
        upstream = spec.upstream_model_name if spec else raw_model

        # Opus hard gate (Comment 6).
        if raw_model == "claude-3-opus":
            from app.services.providers.anthropic_adapter import opus_enabled

            if not opus_enabled():
                result = LLMRouteResult(
                    model=raw_model,
                    content="",
                    success=False,
                    error=(
                        "Opus is disabled: set ENABLE_NATIVE_ANTHROPIC, "
                        "ENABLE_PREMIUM_MODELS, and provide ANTHROPIC_API_KEY "
                        "(or an approved OpenRouter Anthropic route)."
                    ),
                )
                return self._maybe_dict_result(result, 0, user_id, is_admin)

        if reasoning is None:
            reasoning = ReasoningOptions()
        elif not isinstance(reasoning, ReasoningOptions):
            reasoning = ReasoningOptions(**(reasoning if isinstance(reasoning, dict) else {}))

        # Prefer native Anthropic when a real key exists; otherwise an approved
        # OpenRouter Anthropic route is allowed as a fallback.
        adapter: Any = None
        if os.getenv("ANTHROPIC_API_KEY"):
            adapter = AnthropicAdapter(api_key=os.getenv("ANTHROPIC_API_KEY"))
        elif settings.ALLOW_ANTHROPIC_VIA_OPENROUTER and os.getenv("OPENROUTER_API_KEY"):
            adapter = OpenAICompatibleAdapter(
                base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                api_key=os.getenv("OPENROUTER_API_KEY"),
                upstream_model=upstream,
            )

        if adapter is None:
            result = LLMRouteResult(
                model=raw_model,
                content="",
                success=False,
                error="No Anthropic credentials available for native Anthropic model",
            )
            return self._maybe_dict_result(result, 0, user_id, is_admin)

        res: ProviderCallResult = await adapter.complete(
            model=upstream,
            messages=messages,
            reasoning=reasoning,
            max_tokens=max_tokens or 4096,
            temperature=temperature if temperature is not None else 1.0,
        )

        result = LLMRouteResult(
            model=raw_model,
            provider="anthropic",
            content=res.content,
            success=res.success,
            usage={
                "prompt_tokens": res.input_tokens,
                "completion_tokens": res.output_tokens,
                "total_tokens": res.input_tokens + res.output_tokens,
            },
            error=res.error or "",
        )
        payload = self._maybe_dict_result(result, 0, user_id, is_admin)
        if isinstance(payload, dict):
            payload["reasoning_tokens"] = res.reasoning_tokens
            payload["degraded"] = res.degraded
            payload["degradation_note"] = res.degradation_note
            if res.thinking:
                payload["thinking"] = res.thinking
        return payload

    async def route_request(
        self,
        messages: list[dict[str, Any]],
        model_preference: str | None = None,
        *,
        user_id: str | None = None,
        db_session=None,
        is_admin: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        reasoning=None,
        **kwargs,
    ) -> Any:
        effective_user_id = user_id or self.user_id or "system"
        # Use the db_session passed per-request if constructor didn't have one
        effective_db = db_session or self.db
        self._last_messages = list(messages or [])
        raw_model = model_preference or os.getenv("LLM_MODEL_NAME", "deepseek/deepseek-v4-flash")

        # Comment 6: native Anthropic models (claude-3-5-sonnet, claude-3-opus)
        # must NOT go through the OpenAI-compatible path. Route them to the
        # native Anthropic adapter, which uses the correct messages API, key,
        # headers, thinking-block parsing, and prompt-cache controls.
        if self._is_native_anthropic(raw_model):
            return await self._route_native_anthropic(
                raw_model,
                kwargs.get("messages_for_anthropic") or self._last_messages,  # populated below for local builds
                reasoning=reasoning,
                max_tokens=max_tokens,
                temperature=temperature,
                user_id=effective_user_id,
                is_admin=is_admin,
            )

        base_url, api_key, _model_name = _resolve_provider(raw_model)

        # Check for per-request BYOK key override
        byok_key_override = kwargs.pop("byok_key_override", None)
        byok_base_url_override = kwargs.pop("byok_base_url_override", None)

        if byok_key_override:
            logger.info(
                "BYOK llm_router: using per-request override key for model=%s",
                raw_model,
            )
            api_key = byok_key_override
            if byok_base_url_override:
                base_url = byok_base_url_override
        else:
            model_provider = _get_provider_for_model(raw_model)
            logger.debug(
                "BYOK llm_router: looking up keys for user=%s model=%s",
                effective_user_id,
                raw_model,
            )
            byok_key, byok_base = await self._get_byok_key(
                effective_user_id, provider_hint=model_provider, db=effective_db
            )
            if byok_key:
                logger.info(
                    "BYOK llm_router: using stored key for user=%s model=%s",
                    effective_user_id,
                    raw_model,
                )
                api_key = byok_key
                if byok_base:
                    base_url = byok_base
            else:
                logger.debug(
                    "BYOK llm_router: no stored key, using platform key for model=%s",
                    raw_model,
                )

        # ── Hard validation: refuse to call with empty or placeholder API key ──
        # "not-needed" is a valid sentinel for local providers (llamacpp) that
        # don't require API keys. Only reject truly empty or placeholder keys.
        if not api_key or api_key in ("", "sk-xxx", "sk-no-key-required"):
            logger.error(
                "llm_router: no usable API key for model=%s user=%s provider_key=%s",
                raw_model,
                effective_user_id,
                "BYOK" if byok_key_override else "platform",
            )
            result = LLMRouteResult(
                model=raw_model,
                content="",
                success=False,
                error=(
                    f"No API key available for model '{raw_model}'. "
                    f"Add a BYOK key in Settings or set the DEEPSEEK_API_KEY environment variable."
                ),
            )
            return self._maybe_dict_result(result, 0, effective_user_id, is_admin)

        try:
            start = time.time()
            client = _make_client(base_url, api_key)

            create_kwargs: dict[str, Any] = {
                "model": _model_name,
                "messages": messages,
            }
            if max_tokens is not None:
                create_kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                create_kwargs["temperature"] = temperature

            response = await client.chat.completions.create(**create_kwargs)
            duration = time.time() - start

            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": (response.usage.completion_tokens if response.usage else 0),
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }

            provider = raw_model.split("/", 1)[0] if "/" in raw_model else "system"

            result = LLMRouteResult(
                model=raw_model,
                provider=provider,
                content=content,
                success=True,
                usage=usage,
            )

            return self._maybe_dict_result(result, duration, effective_user_id, is_admin)

        except Exception as e:
            logger.error("route_request failed for %s: %s", raw_model, e)
            result = LLMRouteResult(
                model=raw_model,
                content="",
                success=False,
                error=str(e),
            )

            if kwargs.get("_fallback", False) and "No models available" not in str(e):
                fallback = await self._try_fallback(
                    messages,
                    raw_model,
                    effective_user_id,
                    is_admin,
                    max_tokens,
                    temperature,
                )
                if fallback is not None:
                    return fallback

            return self._maybe_dict_result(result, 0, effective_user_id, is_admin)

    def _maybe_dict_result(self, result: LLMRouteResult, duration: float, user_id: str, is_admin: bool) -> Any:
        if self.db is not None:
            return result

        return {
            "success": result.success,
            "response": result.content,
            "content": result.content,
            "model": result.model,
            "model_name": result.model,
            "error": result.error if not result.success else None,
            "cost": {
                "usd": 0.0,
                "input_tokens": result.usage.get("prompt_tokens", 0),
                "output_tokens": result.usage.get("completion_tokens", 0),
            },
            "duration": duration,
            "metadata": {
                "user_id": user_id,
                "is_admin": is_admin,
                "provider": result.provider,
            },
        }

    async def _try_fallback(
        self,
        messages,
        failed_model,
        user_id,
        is_admin,
        max_tokens,
        temperature,
    ):
        fallback_order = []
        if os.getenv("LLAMACPP_URL"):
            fallback_order.append("llamacpp/Qwen3.6-27B")
        if os.getenv("DEEPSEEK_API_KEY"):
            fallback_order.append("deepseek/deepseek-v4-flash")
        fallback_order.append("glennguilloux/demo-llm")

        for model_id in fallback_order:
            if model_id == failed_model:
                continue

            base_url, api_key, model_name = _resolve_provider(model_id)

            try:
                client = _make_client(base_url, api_key)

                create_kwargs: dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
                }
                if max_tokens is not None:
                    create_kwargs["max_tokens"] = max_tokens
                if temperature is not None:
                    create_kwargs["temperature"] = temperature

                response = await client.chat.completions.create(**create_kwargs)

                content = response.choices[0].message.content or ""
                usage = {
                    "prompt_tokens": (response.usage.prompt_tokens if response.usage else 0),
                    "completion_tokens": (response.usage.completion_tokens if response.usage else 0),
                    "total_tokens": (response.usage.total_tokens if response.usage else 0),
                }
                provider = model_id.split("/", 1)[0]

                result = LLMRouteResult(
                    model=model_id,
                    provider=provider,
                    content=content,
                    success=True,
                    usage=usage,
                )

                logger.info("Fallback to %s succeeded after %s failed", model_id, failed_model)

                return self._maybe_dict_result(result, 0, user_id, is_admin)

            except Exception:
                continue

        return None

    async def check_all_providers_health(self) -> dict[str, ProviderStatus]:
        results = {}
        for provider_id, (base_url, key_env) in PROVIDER_MAP.items():
            api_key = os.getenv(key_env) if key_env else "not-needed"
            if key_env and (
                not api_key
                or api_key
                in (
                    "",
                    "sk-no-key-required",
                    "sk-xxx",
                    "sk-or-v1-your-openrouter-api-key",
                )
            ):
                results[provider_id] = ProviderStatus(name=provider_id, healthy=False, error_count=1)
                continue

            test_models = {
                "deepseek": "deepseek-v4-flash",
                "llamacpp": "Qwen3.6-27B-Q5_K_M-mtp.gguf",
                "llamacpp_light": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
            }

            model_name = test_models.get(provider_id)
            if not model_name:
                continue

            try:
                client = _make_client(base_url, api_key)
                await client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=5,
                )
                results[provider_id] = ProviderStatus(name=provider_id, healthy=True)
            except Exception as e:
                logger.warning("Provider %s health check failed: %s", provider_id, e)
                results[provider_id] = ProviderStatus(name=provider_id, healthy=False, error_count=1)

        return results

    async def _is_model_available(
        self,
        model_id: str,
        *,
        user_id: str | None = None,
        db=None,
        is_admin: bool = False,
    ) -> bool:
        """Check if a model can be routed to (has API key or BYOK).

        This is a lightweight pre-flight check used by callers that need
        to know whether a model is usable before attempting a full request.

        Args:
            model_id: The model identifier (e.g. "deepseek/deepseek-v4-flash")
            user_id: User ID for BYOK key lookup
            db: Database session for BYOK key lookup
            is_admin: Whether the user has admin privileges

        Returns:
            True if the model has a usable API key (platform or BYOK),
            False otherwise.
        """
        raw_model = model_id or os.getenv("LLM_MODEL_NAME", "deepseek/deepseek-v4-flash")

        # 1. Check for platform API key
        try:
            _base_url, api_key, _model_name = _resolve_provider(raw_model)
            if api_key and api_key not in ("", "sk-xxx", "sk-no-key-required"):
                return True
        except Exception as e:
            logger.debug("model_availability_resolve_provider_failed raw_model=%s error=%s", raw_model, str(e))

        # 2. Check for BYOK key
        effective_user_id = user_id or self.user_id or "system"
        effective_db = db or self.db
        if effective_user_id != "system" and effective_db:
            try:
                byok_key, _ = await self._get_byok_key(
                    effective_user_id,
                    provider_hint=_get_provider_for_model(raw_model),
                    db=effective_db,
                )
                if byok_key:
                    return True
            except Exception as e:
                logger.debug("BYOK check in _is_model_available failed for %s: %s", raw_model, e)

        return False

    async def _get_byok_key(
        self, user_id: str, provider_hint: str | None = None, db=None
    ) -> tuple[str | None, str | None]:
        """Look up user's BYOK API key from UserAPIKey table.

        Returns (api_key, base_url) or (None, None) if not found.
        If provider_hint is given, prefers a key whose stored provider matches.
        Falls back to any active key if no provider match.
        """
        effective_db = db or self.db
        if not effective_db or not user_id or user_id == "system":
            return None, None

        try:
            from sqlalchemy import select

            from app.models.byok_models import UserAPIKey

            uid = int(user_id) if str(user_id).isdigit() else None
            if uid is None:
                return None, None

            stmt = select(UserAPIKey).where(UserAPIKey.user_id == uid).where(UserAPIKey.is_active == True)
            result = await effective_db.execute(stmt)
            keys = list(result.scalars().all())
            if not keys:
                logger.debug(
                    "BYOK key select: user=%s target=%s no active keys",
                    uid,
                    provider_hint,
                )
                return None, None

            logger.debug(
                "BYOK key select: user=%s target=%s checking %d keys",
                uid,
                provider_hint,
                len(keys),
            )
            # Prefer a key whose stored provider matches the requested model provider
            if provider_hint:
                normalized_hint = _normalize_provider(provider_hint)
                for k in keys:
                    if _normalize_provider(k.provider) == normalized_hint:
                        logger.info(
                            "BYOK key select: MATCH user=%s provider=%s key_id=%s",
                            uid,
                            provider_hint,
                            k.id,
                        )
                        return k.get_api_key(), k.base_url

            logger.warning(
                "BYOK key select: NO MATCH user=%s target=%s available_providers=%s",
                uid,
                provider_hint,
                [k.provider for k in keys],
            )
            # Fall back to the first active key
            return keys[0].get_api_key(), keys[0].base_url
        except Exception as e:
            logger.error("BYOK key select: ERROR user=%s error=%s", user_id, e, exc_info=True)

        return None, None
