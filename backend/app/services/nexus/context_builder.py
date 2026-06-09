"""
Context Builder - Assembles context from multiple sources

Pulls relevant context from memory, RAG, and conversation history
before any operation.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextSource:
    """Represents a source of context data"""

    name: str
    priority: int = 0  # Higher = more important
    enabled: bool = True
    last_fetch: datetime | None = None
    error_count: int = 0


class ContextBuilder:
    """
    Assembles context from multiple sources for any operation.

    Sources include:
    - Agent's personal memory
    - RAG knowledge base
    - Conversation history
    - Other agents' shared memories (if in a chain/swarm)
    - User preferences
    - System state
    """

    def __init__(self):
        self._sources: dict[str, ContextSource] = {}
        self._fetchers: dict[str, Callable[[dict], Awaitable[dict]]] = {}
        self._scorers: list[Callable[[dict, dict], Awaitable[float]]] = []
        self._cache: dict[str, dict] = {}
        self._cache_ttl: int = 300  # 5 minutes

    def register_source(
        self, name: str, fetcher: Callable[[dict], Awaitable[dict]], priority: int = 0
    ) -> None:
        """Register a context source with its fetcher function"""
        self._sources[name] = ContextSource(name=name, priority=priority)
        self._fetchers[name] = fetcher
        logger.info("Registered context source: %s (priority %s)", name, priority)

    def add_relevance_scorer(
        self, scorer: Callable[[dict, dict], Awaitable[float]]
    ) -> None:
        """Add a function that scores relevance of context to a query"""
        self._scorers.append(scorer)

    async def build(
        self,
        query: str,
        context_params: dict[str, Any],
        sources: list[str] | None = None,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """
        Build context for a query by fetching from all relevant sources.

        Args:
            query: The query or task to build context for
            context_params: Parameters like user_id, session_id, agent_id
            sources: Optional list of specific sources to use
            max_tokens: Maximum tokens for assembled context

        Returns:
            Dict with assembled context from all sources
        """
        result: dict[str, Any] = {
            "query": query,
            "params": context_params,
            "sources": {},
            "assembled": "",
            "metadata": {
                "total_sources": 0,
                "successful_sources": 0,
                "failed_sources": 0,
                "build_time_ms": 0,
            },
        }

        start_time = datetime.now(UTC)

        # Determine which sources to use
        source_names: list[str] = (
            list(sources) if sources else list(self._sources.keys())
        )
        source_names = [
            s for s in source_names if s in self._sources and self._sources[s].enabled
        ]

        # Sort by priority (higher first)
        source_names.sort(key=lambda s: self._sources[s].priority, reverse=True)

        # Fetch from each source concurrently
        fetch_tasks = {}
        for name in source_names:
            fetch_tasks[name] = self._fetch_from_source(name, query, context_params)

        # Wait for all fetches
        fetch_results = await asyncio.gather(
            *fetch_tasks.values(), return_exceptions=True
        )

        # Process results
        for name, fetch_result in zip(fetch_tasks.keys(), fetch_results, strict=False):
            result["metadata"]["total_sources"] += 1

            if isinstance(fetch_result, Exception):
                logger.warning("Context source %s failed: %s", name, fetch_result)
                result["sources"][name] = {"error": str(fetch_result)}
                result["metadata"]["failed_sources"] += 1
                self._sources[name].error_count += 1
            else:
                result["sources"][name] = fetch_result
                result["metadata"]["successful_sources"] += 1
                self._sources[name].last_fetch = datetime.now(UTC)

        # Assemble the context string
        result["assembled"] = self._assemble_context(
            result["sources"],
            query,
            max_tokens,  # type: ignore[arg-type]
        )

        result["metadata"]["build_time_ms"] = (
            datetime.now(UTC) - start_time
        ).total_seconds() * 1000

        return result

    async def _fetch_from_source(
        self, source_name: str, query: str, context_params: dict[str, Any]
    ) -> dict[str, Any]:
        """Fetch context from a single source"""
        fetcher = self._fetchers.get(source_name)
        if not fetcher:
            return {"error": f"No fetcher for source {source_name}"}

        try:
            return await fetcher({"query": query, **context_params})
        except Exception as e:
            logger.error("Error fetching from %s: %s", source_name, e)
            raise

    def _assemble_context(
        self, sources_data: dict[str, dict], query: str, max_tokens: int
    ) -> str:
        """Assemble context string from all source data"""
        parts = []

        for source_name, data in sources_data.items():
            if "error" in data:
                continue

            if "content" in data:
                parts.append(f"[{source_name}]\n{data['content']}\n")
            elif "documents" in data:
                docs_text = "\n".join(
                    [
                        f"- {doc.get('content', doc.get('text', str(doc)))[:500]}"
                        for doc in data["documents"][:5]  # Limit to 5 docs
                    ]
                )
                parts.append(f"[{source_name}]\n{docs_text}\n")
            elif "memories" in data:
                mem_text = "\n".join(
                    [
                        f"- {mem.get('content', mem.get('text', str(mem)))[:300]}"
                        for mem in data["memories"][:5]
                    ]
                )
                parts.append(f"[{source_name}]\n{mem_text}\n")

        # Join and truncate to max_tokens (rough estimate: 4 chars per token)
        assembled = "\n".join(parts)
        if len(assembled) > max_tokens * 4:
            assembled = assembled[: max_tokens * 4] + "\n... [truncated]"

        return assembled

    async def score_relevance(self, context: dict[str, Any], query: str) -> float:
        """Score how relevant the context is to the query"""
        if not self._scorers:
            return 0.5  # Default score if no scorers

        scores = []
        for scorer in self._scorers:
            try:
                score = await scorer(context, query)  # type: ignore[arg-type]
                scores.append(score)
            except Exception as e:
                logger.warning("Scorer failed: %s", e)

        return sum(scores) / len(scores) if scores else 0.5

    def enable_source(self, name: str) -> bool:
        """Enable a context source"""
        if name in self._sources:
            self._sources[name].enabled = True
            return True
        return False

    def disable_source(self, name: str) -> bool:
        """Disable a context source"""
        if name in self._sources:
            self._sources[name].enabled = False
            return True
        return False

    def list_sources(self) -> list[dict[str, Any]]:
        """List all registered context sources"""
        return [
            {
                "name": source.name,
                "priority": source.priority,
                "enabled": source.enabled,
                "last_fetch": (
                    source.last_fetch.isoformat() if source.last_fetch else None
                ),
                "error_count": source.error_count,
            }
            for source in self._sources.values()
        ]
