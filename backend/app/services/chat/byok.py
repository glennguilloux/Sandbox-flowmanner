# ─────────────────────────────────────────────────────────────────────────
# Auto-decomposed from app/services/chat_service.py (CARD 3 refactor).
# Part of the `chat` package. Sibling cross-references and original imports
# are preserved so behavior/signatures stay byte-for-byte identical.
# ─────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.config import settings
from app.services.llm_providers import (
    _LLM_API_BASE,
    _LLM_API_KEY,
    _LLM_MODEL,
    OPENAI_PROVIDER_FAMILIES,
    PROVIDER_MAP,
    _detect_provider_from_key,
    _get_base_url_for_provider,
    _get_provider_for_model,
    _get_upstream_model_name,
    _normalize_provider,
    _providers_compatible,
    _resolve_provider,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "_MAX_TOOL_ROUNDS",
    "_SANDBOXD_SYSTEM_GUIDANCE",
    "_lookup_stored_byok_key",
    "_validate_byok_key_matches_model",
]


async def _lookup_stored_byok_key(
    db: AsyncSession,
    user_id: int,
    provider_hint: str | None = None,
) -> tuple[str | None, str | None]:
    """Look up the best stored BYOK key for a user.

    Returns (api_key, base_url) or (None, None) if no key found.
    If provider_hint is given, prefers a key whose provider matches.
    Falls back to any active key if no provider match.
    """
    logger.debug("BYOK lookup: user=%s provider=%s", user_id, provider_hint)
    try:
        from sqlalchemy import select

        from app.models.byok_models import UserAPIKey

        stmt = select(UserAPIKey).where(UserAPIKey.user_id == user_id).where(UserAPIKey.is_active == True)
        result = await db.execute(stmt)
        keys = list(result.scalars().all())
        if not keys:
            return None, None

        # Prefer a key whose provider matches the hint
        if provider_hint:
            normalized_hint = _normalize_provider(provider_hint)
            for k in keys:
                if _normalize_provider(k.provider) == normalized_hint:
                    logger.info(
                        "BYOK lookup FOUND: user=%s provider=%s key_id=%s",
                        user_id,
                        provider_hint,
                        k.id,
                    )
                    return k.get_api_key(), k.base_url

            # No exact provider match. For an openai_compatible (generic) key
            # the stored provider is "openai_compatible" regardless of the
            # model prefix (e.g. tencent/hy3:free, deepseek/...), so the hint
            # never equals it. These keys serve ANY model id, so use one
            # rather than falling through to the platform key (which 400/403s
            # because it doesn't know the user's model).
            compatible = [k for k in keys if k.provider == "openai_compatible"]
            if compatible:
                chosen = compatible[0]
                logger.info(
                    "BYOK lookup GENERIC: user=%s provider=%s -> openai_compatible key_id=%s",
                    user_id,
                    provider_hint,
                    chosen.id,
                )
                return chosen.get_api_key(), chosen.base_url

            # No provider match found — do NOT fall back to a random key.
            # Returning a key for the wrong provider causes 400 errors
            # (e.g. sending demo-llm to OpenRouter instead of glennguilloux).
            logger.info(
                "BYOK lookup NO MATCH: user=%s provider=%s available=%s",
                user_id,
                provider_hint,
                [k.provider for k in keys],
            )
            return None, None

        # Fall back to the first active key
        logger.debug(
            "BYOK lookup FALLBACK: user=%s provider=%s -> using first key key_id=%s",
            user_id,
            provider_hint,
            keys[0].id,
        )
        return keys[0].get_api_key(), keys[0].base_url
    except Exception:
        logger.warning(
            "BYOK lookup ERROR: user=%s provider=%s",
            user_id,
            provider_hint,
            exc_info=True,
        )
        return None, None


def _validate_byok_key_matches_model(user_api_key: str | None, model_id: str) -> str | None:
    """Validate that BYOK key matches the requested model provider.

    Returns None if valid.
    Returns error message if mismatch:
    - For llamacpp/*: always valid (ignore key)
    - For openai_compatible/*: accept any OpenAI-family key or unknown keys
    - For other providers: check if key matches model provider
    """
    if not user_api_key or not model_id:
        return None

    model_provider = _get_provider_for_model(model_id)

    if model_provider == "llamacpp":
        return None

    key_provider = _detect_provider_from_key(user_api_key)

    if not _providers_compatible(key_provider, model_provider):
        return f"Provider mismatch: model '{model_id}' requires {model_provider.title()}, but X-User-API-Key appears to be for {key_provider.title()}"

    return None


_SANDBOXD_SYSTEM_GUIDANCE = """

## Live Preview Tools (sandboxd)

You have tool-calling (function-calling) capabilities available. **When you
want to use one of these tools, you MUST emit an actual tool/function call —
do NOT describe the call in prose or write it as if it were text.** Narrating
"I will call sandboxd_preview" without emitting the function call does nothing
and stalls the conversation. Always prefer calling a tool over talking about
calling it.

When the user asks you to build something visual (landing page, dashboard,
chart, tool, app, or any HTML/CSS/JS project), use the sandboxd tools to
create a live preview. Follow this workflow **exactly**:

1. **sandboxd_preview** — emit a tool call with `{}` (no arguments) to create a
   new sandbox. Save the returned `sandbox_id` for ALL subsequent calls.
   ⚠️  CRITICAL: sandboxd_preview returns sandbox metadata ONLY (id, status).
   It does NOT return a usable app preview URL.  The sandbox runtime URL (port 3000)
   is empty — do NOT show it to the user.  The preview URL comes from sandboxd_serve.
2. **sandboxd_file_write** — write your files. Pass `sandbox_id` and `path` and `content`.
   Example: `{"sandbox_id": "...", "path": "index.html", "content": "<!DOCTYPE html>..."}`
   Subdirectories are created automatically (e.g. `"css/style.css"` works fine).
   Write ALL files before calling sandboxd_serve.
3. **sandboxd_serve** — start a dev server and get the preview URL:
   `{"sandbox_id": "..."}`
   This starts a server on port 8081 (the default python-img template does not use 8080; some legacy templates like react-standard may)
   that serves from /home/sandbox/ where your files were written.
   This is the ONLY tool that returns the app preview URL.  ALWAYS call it
   after writing files, and ALWAYS present its returned URL to the user.
4. **sandboxd_file_read** — read a file back: `{"sandbox_id": "...", "path": "index.html"}`
5. **sandboxd_file_list** — list workspace files: `{"sandbox_id": "...", "path": ""}`

If you need to run custom commands (npm install, python scripts, etc.), use
**sandboxd_exec** with the `command` field (argv array).

The preview URL format is:
https://s-<sandbox_id>-8081.preview.flowmanner.com

The URL is publicly accessible. The sandbox stays alive for 35 minutes.

If any tool returns an error containing "container is not running" or
"not running", do NOT retry more than once — explain the error to the user."""


_MAX_TOOL_ROUNDS = settings.CHAT_MAX_TOOL_ROUNDS
