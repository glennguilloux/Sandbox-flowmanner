# ─────────────────────────────────────────────────────────────────────────
# Auto-decomposed from app/services/chat_service.py (CARD 3 refactor).
# Part of the `chat` package. Sibling cross-references and original imports
# are preserved so behavior/signatures stay byte-for-byte identical.
# ─────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "_PROMPT_CACHE_TTL",
    "_get_active_prompt_content",
    "_get_prompt_redis",
    "_inject_web_search",
    "_prompt_cache_key",
    "invalidate_prompt_version_cache",
]


async def _inject_web_search(messages: list[dict], query: str) -> list[dict]:
    try:
        from app.services.web_search.models import SearchConfig
        from app.services.web_search.service_enhanced import EnhancedWebSearchService

        config = SearchConfig(
            duckduckgo_enabled=True,
            searxng_enabled=True,
            searxng_url="http://searxng:8080",
        )
        service = EnhancedWebSearchService(config)
        # Extract key search terms for better results
        search_query = query
        for prefix in [
            "what is",
            "what's",
            "what are",
            "tell me",
            "can you",
            "do you know",
            "how much is",
            "how much does",
            "current",
            "latest",
            "find",
            "search",
        ]:
            if search_query.lower().startswith(prefix):
                search_query = search_query[len(prefix) :].strip(" ?!,.;:")
                break
        if not search_query.strip():
            search_query = query
        search_result = await service.search(
            query=search_query,
            max_results=5,
            use_cache=False,
            use_reranking=False,
            use_query_understanding=False,
        )

        results = search_result.get("results", [])
        if not results:
            return messages

        lines = [
            "IMPORTANT: The following web search results contain CURRENT, FACTUAL information.",
            f'Use these results to answer the user\'s question about: "{query}"',
            "Do NOT say you lack access to live data — you have the data right here.",
            "If the results contain a price, date, or figure, cite it directly.",
            "",
            "Search results:",
        ]
        for i, r in enumerate(results[:5], 1):
            if isinstance(r, dict):
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("snippet", r.get("content", ""))[:200]
            else:
                title = getattr(r, "title", "Untitled") or "Untitled"
                url = getattr(r, "url", "") or ""
                snippet = (getattr(r, "snippet", "") or getattr(r, "content", "") or "")[:200]
            lines.append(f"{i}. {title} — {url}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")

        search_context = "\n".join(lines)
        # Append search results to the last user message so the model can't ignore them
        messages[-1]["content"] = (
            f"{search_context}\n\nBased on the search results above, answer the following:\n{messages[-1]['content']}"
        )

    except Exception as e:
        logger.warning("Web search failed (non-fatal): %s", e)

    return messages


_PROMPT_CACHE_TTL = 300  # 5 minutes


def _prompt_cache_key(workspace_id: str, name: str) -> str:
    return f"prompt_version:{workspace_id}:{name}"


async def _get_prompt_redis():
    """Return an async Redis client, or None if unavailable."""
    try:
        from redis.asyncio import from_url  # type: ignore[import-untyped]

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return from_url(url, decode_responses=True)
    except Exception:
        return None


async def invalidate_prompt_version_cache(workspace_id: str, name: str | None = None) -> None:
    """Delete cached prompt version(s) for a workspace.

    Called after create/activate/delete in the prompt CRUD API.
    If *name* is given, invalidates only that name group.
    If *name* is None, invalidates all prompt caches for the workspace.
    """
    rds = await _get_prompt_redis()
    if rds is None:
        return
    try:
        if name:
            await rds.delete(_prompt_cache_key(workspace_id, name))
        else:
            # Scan for all prompt_version:{workspace_id}:* keys
            pattern = f"prompt_version:{workspace_id}:*"
            cursor = 0
            while True:
                cursor, keys = await rds.scan(cursor, match=pattern, count=100)
                if keys:
                    await rds.delete(*keys)
                if cursor == 0:
                    break
    except Exception:
        pass  # cache miss is fine
    finally:
        await rds.aclose()


async def _get_active_prompt_content(
    db: AsyncSession,
    workspace_id: str,
    name: str = "Default Assistant",
) -> str | None:
    """Look up the active prompt version for a workspace and name group.

    Returns the prompt content string, or None if no active version exists.
    Phase 6: prompt versioning with Redis caching (5min TTL).

    Results are cached in Redis to avoid a DB query on every chat message.
    Cache is invalidated by ``invalidate_prompt_version_cache()`` when
    prompt versions are created, activated, or deleted via the API.
    """
    from app.models.prompt_version_models import PromptVersion

    cache_key = _prompt_cache_key(workspace_id, name)

    # ── Single Redis connection for read + write ───────────────────
    rds = await _get_prompt_redis()
    try:
        # ── Try cache first ──────────────────────────────────────
        if rds is not None:
            try:
                cached = await rds.get(cache_key)
                if cached is not None:
                    if cached == "__NONE__":
                        return None  # sentinel: no active version
                    return cached
            except Exception:
                pass  # cache miss → fall through to DB

        # ── DB query ───────────────────────────────────────────
        result = await db.execute(
            select(PromptVersion).where(
                PromptVersion.workspace_id == workspace_id,
                PromptVersion.name == name,
                PromptVersion.is_active == True,
            )
        )
        pv = result.scalar_one_or_none()
        content = pv.content if pv is not None else None

        # ── Populate cache (same connection) ───────────────────
        if rds is not None:
            try:
                cache_val = content if content is not None else "__NONE__"
                await rds.setex(cache_key, _PROMPT_CACHE_TTL, cache_val)
            except Exception:
                pass  # caching is best-effort

        return content
    finally:
        if rds is not None:
            await rds.aclose()
