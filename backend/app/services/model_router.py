#!/usr/bin/env python3
"""
Model Router Service

Routes LLM requests based on:
1. Cost optimization (80% local, 20% cloud)
2. Permission controls (admin approval for paid models)
3. Fallback chains (local -> free cloud -> paid cloud)
4. Load balancing and health checks
5. BYOK (Bring Your Own Key) support
"""

import ipaddress
import logging
import os
import socket
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .langgraph.llm_config import get_llm_manager

logger = logging.getLogger(__name__)

# ── SSRF protection for user-supplied BYOK base_url ──────────────────────────
# Default-deny: a custom base_url is only allowed when it uses an http(s)
# scheme and resolves to a PUBLIC (globally routable) IP. This mirrors the
# contract in app/api/v1/api_keys.py:_is_safe_outbound_url so the two BYOK
# key-resolution paths agree (services AGENTS.md rule 4).
_BLOCKED_SCHEMES = frozenset({"file", "ftp", "data", "javascript", "gopher", "dict"})
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "0.0.0.0",
        "::1",
        "127.0.0.1",
        "::",
        "169.254.169.254",
    }
)
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::1/128",
        "::/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)


def _is_safe_outbound_url(url: str) -> tuple[bool, str | None]:
    """Validate a custom BYOK base_url against SSRF rules (default-deny).

    Mirrors ``app.api.v1.api_keys._is_safe_outbound_url`` so the two BYOK
    key-resolution paths agree (services AGENTS.md rule 4). The destination
    must use http/https, must not be a blocked hostname, and must resolve to a
    publicly routable IP address (rejecting private/loopback/link-local/
    reserved/multicast ranges). On a literal-IP host we check the IP directly;
    for hostnames we resolve via ``socket.getaddrinfo`` and reject any address
    that is not global.
    """
    if not url:
        return False, "base_url is required"
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        return False, f"Invalid base_url: {exc}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"base_url scheme '{scheme}://' is not allowed (http/https only)"
    if scheme in _BLOCKED_SCHEMES:
        return False, f"base_url scheme '{scheme}://' is blocked"

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "base_url has no valid hostname"
    if hostname in _BLOCKED_HOSTNAMES:
        return False, f"base_url host '{hostname}' is blocked"

    # Reject a literal private/loopback/link-local/reserved/multicast IP.
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        pass  # Not a literal IP — resolve it below.
    else:
        if not addr.is_global or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            return False, f"base_url host '{hostname}' is not a public address"
        return True, None

    # Hostname: resolve and reject names that point at non-public ranges.
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        return False, f"base_url host '{hostname}' could not be resolved: {exc}"

    if not infos:
        return False, f"base_url host '{hostname}' resolved to no addresses"

    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            resolved = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"base_url host '{hostname}' resolved to an invalid address '{ip_str}'"
        if (
            not resolved.is_global
            or resolved.is_loopback
            or resolved.is_link_local
            or resolved.is_reserved
            or resolved.is_multicast
        ):
            return False, (f"base_url host '{hostname}' resolves to a non-public address '{ip_str}'")
    return True, None


class RoutingStrategy(Enum):
    """Routing strategy options"""

    LOCAL_FIRST = "local-first"  # 80% local, 20% cloud with permission
    COST_OPTIMIZED = "cost-optimized"  # Cheapest available model
    PERFORMANCE = "performance"  # Best model regardless of cost


tracer = trace.get_tracer(__name__)


class ModelRouter:
    """Route LLM requests to appropriate provider based on user context and model availability."""

    _db_backend: str = "postgresql"

    # Model category lists
    LOCAL_MODELS = [
        "llamacpp-qwen3.6-27b",
        "llamacpp-qwen2.5-1.5b",
    ]

    FREE_CLOUD_MODELS: list[str] = []

    PAID_CLOUD_MODELS = [
        "deepseek-v4-flash",
        "glennguilloux-demo-llm",
    ]

    def __init__(self):
        self.llm_manager = None  # Lazy load to avoid circular import
        self.model_health = {}  # Model health tracking
        self._model_status = {}  # Internal status tracking
        self.routing_strategy: str = os.getenv("LLM_ROUTING_STRATEGY", "local-first")
        self.local_model_ratio: float = 0.8
        self.max_retries: int = 3
        self.retry_delay: float = 1.0

    @property
    def local_models(self) -> list[str]:
        return self.LOCAL_MODELS

    @property
    def free_cloud_models(self) -> list[str]:
        return self.FREE_CLOUD_MODELS

    @property
    def paid_cloud_models(self) -> list[str]:
        return self.PAID_CLOUD_MODELS

    def _get_llm_manager(self):
        """Lazy load LLM manager to avoid circular imports"""
        if self.llm_manager is None:
            try:
                self.llm_manager = get_llm_manager()
                logger.info("LLMManager loaded successfully")
            except Exception as e:
                logger.warning("Could not load LLMManager: %s", e)
                self.llm_manager = None
        return self.llm_manager

    def _get_db_backend(self) -> str:
        """Determine database backend type"""
        if hasattr(self, "_db_backend"):
            return self._db_backend
        db_url = os.getenv("DATABASE_URL", "")
        if "sqlite" in db_url.lower():
            self._db_backend = "sqlite"
        else:
            self._db_backend = "postgresql"
        return self._db_backend

    def _get_model_name(self, model_id: str) -> str:
        """Get display name for a model."""
        # Comment 5: prefer the catalog's canonical upstream model name.
        try:
            from app.services.model_catalog import get_model_catalog

            spec = get_model_catalog().get(model_id)
            if spec is not None:
                return spec.upstream_model_name
        except Exception:
            pass
        if self.llm_manager:
            mapped = self.llm_manager.MODEL_MAP.get(model_id, model_id)
            if mapped.startswith("llamacpp/"):
                return mapped[len("llamacpp/") :]
            if "/" in mapped:
                # Extract model name from provider/model format
                parts = mapped.rsplit("/", 1)
                return parts[-1]
        return model_id

    def get_routing_info(self) -> dict[str, Any]:
        """Get current routing configuration."""
        return {
            "strategy": self.routing_strategy,
            "local_model_ratio": self.local_model_ratio,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "total_models": len(self.LOCAL_MODELS) + len(self.FREE_CLOUD_MODELS) + len(self.PAID_CLOUD_MODELS),
            "local_count": len(self.LOCAL_MODELS),
            "free_cloud_count": len(self.FREE_CLOUD_MODELS),
            "paid_cloud_count": len(self.PAID_CLOUD_MODELS),
        }

    async def get_model_status(self, model_id: str, user_id: int = None, db_session: AsyncSession = None) -> dict[str, Any]:
        """Get current status of a model"""
        return self._model_status.get(
            model_id,
            {
                "available": await self._is_model_available(model_id, user_id=user_id, db_session=db_session),
                "health": self.model_health.get(model_id, "unknown"),
                "last_check": datetime.now(UTC).isoformat(),
            },
        )

    async def _is_model_available(self, model_id: str, user_id: int = None, db_session: AsyncSession = None) -> bool:
        """Check if a model is available (platform or BYOK).

        Args:
            model_id: The model identifier to check
            user_id: Optional user ID for BYOK key lookup
            db_session: Optional database session for BYOK key lookup
        """
        llm_manager = self._get_llm_manager()
        if not llm_manager:
            return False

        # 1. Try user's BYOK key first
        if user_id is not None and db_session is not None:
            try:
                byok_key = await self._get_byok_key(model_id, user_id, db_session)
                if byok_key:
                    model = llm_manager.get_model(model_id, user_id=user_id)
                    if model is not None:
                        return True
            except Exception as e:
                logger.warning("BYOK check failed for %s: %s", model_id, e)

        # 2. Fall back to platform key — always forward user context if available
        try:
            model = llm_manager.get_model(model_id, user_id=user_id)
            if model is not None:
                return not (model_id in self.model_health and not self.model_health[model_id])
        except Exception as e:
            logger.warning("Platform model check failed for %s: %s", model_id, e)

        return False

    async def _get_byok_key(self, model_id: str, user_id: int, db_session: AsyncSession):
        """Look up user's BYOK key for a specific model.

        Async — operates on an AsyncSession via ``select()``/``await``. Returns
        the matching ``UserAPIKey`` row, or ``None`` when no active key covers
        ``model_id`` (the falsy return satisfies the ``if byok_key:`` guards at
        the two call sites).
        """
        logger.debug("BYOK model_router lookup: user=%s model=%s", user_id, model_id)
        try:
            from app.models.byok_models import UserAPIKey as UserApiKey

            # Extract original model_id from BYOK format: byok_{user_id}_{model_id}
            original_model_id = model_id
            if model_id.startswith("byok_"):
                parts = model_id.split("_", 2)  # Split into ['byok', '{user_id}', '{model_id}']
                if len(parts) >= 3:
                    original_model_id = parts[2]
                    logger.info(
                        "BYOK lookup: parsed model_id=%s -> original=%s, user=%s",
                        model_id,
                        original_model_id,
                        user_id,
                    )

            logger.info(
                "BYOK lookup: searching for user_id=%s, original_model_id=%s",
                user_id,
                original_model_id,
            )

            # Single async path covering both PostgreSQL and SQLite: select the
            # active keys for the user, then match the model in Python. This
            # avoids the sync .query() call (AsyncSession has no .query) and the
            # PostgreSQL-specific JSON containment operator on the async path.
            stmt = select(UserApiKey).where(UserApiKey.user_id == user_id).where(UserApiKey.is_active == True)
            result = await db_session.execute(stmt)
            keys = result.scalars().all()

            logger.info("BYOK lookup: found %s active keys for user", len(keys))
            for key in keys:
                logger.info("BYOK lookup: checking key %s, models=%s", key.id, key.models)
                if key.models and original_model_id in key.get_models_list():
                    logger.info(
                        "BYOK model_router lookup: MATCH key_id=%s provider=%s",
                        key.id,
                        key.provider,
                    )
                    return key
            logger.info("BYOK lookup: NO MATCH found for %s", original_model_id)
            return None
        except SQLAlchemyError as e:
            logger.error(
                "Error looking up BYOK key for user=%s model=%s: %s",
                user_id,
                model_id,
                e,
                exc_info=True,
            )
            return None

    async def _execute_with_byok(
        self,
        messages: list,
        model_id: str,
        api_key: str,
        base_url: str,
        user_id: str = None,
        db_session: AsyncSession = None,
        api_key_id: int = None,
        request_type: str = "chat",
        **kwargs,
    ) -> dict:
        """Execute LLM with BYOK credentials, returning standard response format."""
        logger.info(
            "BYOK execute START: model=%s user=%s key_id=%s base_url=%s",
            model_id,
            user_id,
            api_key_id,
            base_url,
        )
        logger.debug("BYOK execute: messages=%d", len(messages))

        # Extract original model_id from BYOK format
        original_model_id = model_id
        if model_id.startswith("byok_"):
            parts = model_id.split("_", 2)
            if len(parts) >= 3:
                original_model_id = parts[2]
                logger.info("  Parsed original_model_id: %s", original_model_id)

        start_time = time.time()
        latency_ms = 0
        input_tokens = 0
        output_tokens = 0

        try:
            llm_manager = self._get_llm_manager()
            logger.info("  LLM manager: %s", llm_manager is not None)
            logger.info(
                "  Has get_model_with_user_key: %s",
                (hasattr(llm_manager, "get_model_with_user_key") if llm_manager else False),
            )
            if not llm_manager:
                return {
                    "success": False,
                    "error": "LLM manager not available",
                    "model_id": model_id,
                    "provider": "byok",
                }

            # SSRF guard: validate the (user-supplied) base_url before handing it
            # to the LLM client. On failure, fall back to the provider default so
            # execution still proceeds against the legitimate endpoint rather than
            # an internal/metadata address. Mirrors app/api/v1/api_keys.py.
            if base_url:
                ok, err = _is_safe_outbound_url(base_url)
                if not ok:
                    fallback = self._get_default_base_url(
                        original_model_id.split("/")[0] if "/" in original_model_id else ""
                    )
                    logger.warning(
                        "BYOK execute: rejecting unsafe base_url=%s (%s); falling back to provider default=%s",
                        base_url,
                        err,
                        fallback,
                    )
                    base_url = fallback

            llm = llm_manager.get_model_with_user_key(model_id=model_id, api_key=api_key, base_url=base_url)

            raw_response = await llm.ainvoke(messages, **kwargs)

            # Extract tokens with fallbacks
            input_tokens, output_tokens = self._extract_token_usage(raw_response, messages)
            cost = self._calculate_cost(model_id, input_tokens, output_tokens)
            latency_ms = int((time.time() - start_time) * 1000)

            # Phase 3: Log usage tracking
            if db_session and api_key_id and user_id:
                try:
                    from app.services.usage_tracking_service import UsageTrackingService

                    user_id_int = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else None
                    UsageTrackingService.log_usage(
                        db=db_session,
                        api_key_id=api_key_id,
                        user_id=user_id_int,
                        model_id=model_id,
                        request_type=request_type,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        success=True,
                    )
                except Exception as log_error:
                    logger.warning("Usage logging failed: %s", log_error)

            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "BYOK execute DONE: model=%s latency=%sms tokens_in=%d tokens_out=%d",
                model_id,
                latency_ms,
                input_tokens,
                output_tokens,
            )
            return {
                "success": True,
                "response": (raw_response.content if hasattr(raw_response, "content") else str(raw_response)),
                "model_id": model_id,
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                "cost": cost,
                "latency_ms": latency_ms,
                "provider": "byok",
            }
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "BYOK execute FAILED: model=%s latency=%sms error=%s",
                model_id,
                latency_ms,
                e,
                exc_info=True,
            )
            # Log failed usage
            if db_session and api_key_id and user_id:
                try:
                    from app.services.usage_tracking_service import UsageTrackingService

                    UsageTrackingService.log_usage(
                        db=db_session,
                        api_key_id=api_key_id,
                        user_id=(int(user_id) if isinstance(user_id, str) and user_id.isdigit() else user_id),
                        model_id=model_id,
                        request_type=request_type,
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=int((time.time() - start_time) * 1000),
                        success=False,
                        error_message=str(e),
                    )
                except Exception as log_error:
                    logger.warning("Usage logging failed: %s", log_error)
            return {
                "success": False,
                "error": str(e),
                "model_id": model_id,
                "provider": "byok",
            }

    def _extract_token_usage(self, raw_response, messages: list) -> tuple:
        """Extract tokens with multi-source fallback."""
        input_tokens = 0
        output_tokens = 0

        if hasattr(raw_response, "usage_metadata") and raw_response.usage_metadata:
            input_tokens = raw_response.usage_metadata.get("input_tokens", 0)
            output_tokens = raw_response.usage_metadata.get("output_tokens", 0)
        elif hasattr(raw_response, "response_metadata"):
            usage = raw_response.response_metadata.get("token_usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)

        if input_tokens == 0:
            input_tokens = self._estimate_tokens(messages)
            if hasattr(raw_response, "content"):
                output_tokens = self._estimate_tokens([{"content": raw_response.content}])

        return input_tokens, output_tokens

    def _estimate_tokens(self, messages: list) -> int:
        """Estimate token count for messages."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += len(part["text"]) // 4
        return max(total, 1)

    def _calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for token usage using PricingService."""
        try:
            from app.services.pricing_service import PricingService

            return float(PricingService.estimate_cost(model_id, input_tokens, output_tokens))
        except ImportError:
            # Fallback if PricingService not available
            return (input_tokens / 1_000_000) * 0.5 + (output_tokens / 1_000_000) * 1.5

    def _get_default_base_url(self, provider: str) -> str:
        """Get default base URL for a provider."""
        DEFAULT_URLS = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "glennguilloux": "https://ai.glennguilloux.com:9443/v1",
        }
        return DEFAULT_URLS.get(provider.lower(), "")

    async def route_request(
        self,
        messages: list,
        user_id: str | int | None = None,
        db_session: AsyncSession = None,
        model_id: str = None,
        model_preference: str = None,
        is_admin: bool = False,
        **kwargs,
    ) -> dict:
        """Route to platform or BYOK model."""

        with tracer.start_as_current_span("model.route") as span:
            span.set_attribute("model.user_id", str(user_id) if user_id else "anonymous")
            span.set_attribute("model.preference", model_preference or "auto")
            span.set_attribute("model.is_admin", is_admin)

        # Normalize user_id
        normalized_user_id = str(user_id) if isinstance(user_id, int) else user_id
        user_id_int = int(normalized_user_id) if normalized_user_id and str(normalized_user_id).isdigit() else None

        target_model = model_id or model_preference

        # Check BYOK first if we have user context
        if user_id_int and db_session and target_model:
            logger.debug(
                "BYOK model_router: checking for model=%s user=%s",
                target_model,
                user_id_int,
            )
            byok_key = await self._get_byok_key(target_model, user_id_int, db_session)
            if byok_key:
                try:
                    decrypted_key = byok_key.get_api_key()
                    base_url = byok_key.base_url or self._get_default_base_url(byok_key.provider)
                    return await self._execute_with_byok(
                        messages,
                        target_model,
                        decrypted_key,
                        base_url,
                        normalized_user_id,
                        db_session=db_session,
                        api_key_id=byok_key.id,
                        request_type="chat",
                        **kwargs,
                    )
                except Exception as e:
                    logger.error(
                        "BYOK model_router: execution FAILED model=%s user=%s error=%s",
                        target_model,
                        user_id_int,
                        e,
                        exc_info=True,
                    )

        # Platform model execution
        return await self._execute_with_platform_model(
            messages,
            target_model,
            normalized_user_id,
            is_admin,
            user_id_int=user_id_int,
            db_session=db_session,
            **kwargs,
        )

    async def _execute_with_platform_model(
        self,
        messages: list,
        model_id: str,
        user_id: str,
        is_admin: bool = False,
        user_id_int: int = None,
        db_session: AsyncSession = None,
        **kwargs,
    ) -> dict:
        """Execute using platform model with BYOK fallback."""
        start_time = time.time()

        llm_manager = self._get_llm_manager()
        if llm_manager:
            try:
                model = llm_manager.get_model(model_id, user_id=user_id_int) if model_id else None
                if model:
                    raw_response = await model.ainvoke(messages, **kwargs)
                    input_tokens, output_tokens = self._extract_token_usage(raw_response, messages)
                    cost = self._calculate_cost(model_id or "default", input_tokens, output_tokens)
                    return {
                        "success": True,
                        "response": (raw_response.content if hasattr(raw_response, "content") else str(raw_response)),
                        "model_id": model_id,
                        "usage": {
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                        },
                        "cost": cost,
                        "latency_ms": int((time.time() - start_time) * 1000),
                        "provider": "platform",
                    }
            except Exception as e:
                logger.error("Platform model %s failed: %s", model_id, e)

            # Fallback: try any available platform model via fallback chain
            try:
                fallback_model = (
                    llm_manager.get_model(model_id, user_id=user_id_int, use_fallback=True)
                    if model_id
                    else llm_manager.get_model(user_id=user_id_int)
                )
                if fallback_model:
                    raw_response = await fallback_model.ainvoke(messages, **kwargs)
                    input_tokens, output_tokens = self._extract_token_usage(raw_response, messages)
                    used_model_id = model_id or llm_manager.default_model_id
                    cost = self._calculate_cost(used_model_id, input_tokens, output_tokens)
                    return {
                        "success": True,
                        "response": (raw_response.content if hasattr(raw_response, "content") else str(raw_response)),
                        "model_id": used_model_id,
                        "usage": {
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                        },
                        "cost": cost,
                        "latency_ms": int((time.time() - start_time) * 1000),
                        "provider": "platform",
                    }
            except Exception as fallback_err:
                logger.error("Platform fallback also failed: %s", fallback_err)

        # Last resort: try BYOK with user's any available key if user context present
        if user_id_int and db_session:
            try:
                from app.models.byok_models import UserAPIKey as UserApiKey

                stmt = select(UserApiKey).where(UserApiKey.user_id == user_id_int).where(UserApiKey.is_active == True)
                result = await db_session.execute(stmt)
                keys = result.scalars().all()
                for key in keys:
                    if key.models and key.models:
                        try:
                            decrypted_key = key.get_api_key()
                            base_url = key.base_url or self._get_default_base_url(key.provider)
                            return await self._execute_with_byok(
                                messages,
                                model_id or (key.models[0] if key.models else "gpt-3.5-turbo"),
                                decrypted_key,
                                base_url,
                                str(user_id),
                                db_session=db_session,
                                api_key_id=key.id,
                                request_type="chat",
                                **kwargs,
                            )
                        except Exception as byok_err:
                            logger.warning("BYOK fallback with key %s failed: %s", key.id, byok_err)
                            continue
            except Exception as e:
                logger.warning("BYOK fallback lookup failed: %s", e)

        return {
            "success": False,
            "error": f"No available model for {model_id}. Platform models unavailable and no BYOK keys found.",
            "model_id": model_id,
            "provider": "none",
        }


# Singleton instance
_model_router = None


def get_model_router() -> ModelRouter:
    """Get singleton ModelRouter instance."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router
