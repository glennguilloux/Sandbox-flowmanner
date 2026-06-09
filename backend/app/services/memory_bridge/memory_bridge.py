"""
Memory Bridge - Connects agent memory to RAG and other systems

Enables seamless integration between agent memory and:
- RAG knowledge base
- Shared agent memories
- External memory systems
- Context building
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .memory_service import Memory, MemoryService

logger = logging.getLogger(__name__)


@dataclass
class BridgeConfig:
    """Configuration for memory bridge"""

    sync_to_rag: bool = True
    rag_collection: str = "agent_memories"
    share_between_agents: bool = False
    max_shared_importance: float = 0.7
    context_injection_enabled: bool = True


class MemoryBridge:
    """
    Connects agent memory to RAG and other systems.

    Features:
    - Sync important memories to RAG for knowledge sharing
    - Share memories between agents in a swarm
    - Inject relevant memories into context
    - Bridge to external memory systems
    """

    def __init__(
        self,
        memory_service: MemoryService,
        rag_service=None,
        config: BridgeConfig | None = None,
    ):
        self.memory_service = memory_service
        self.rag_service = rag_service
        self.config = config or BridgeConfig()
        self._external_bridges: dict[str, Callable] = {}

    async def store_with_sync(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
        sync_to_rag: bool | None = None,
    ) -> Memory:
        """
        Store a memory and optionally sync to RAG.

        Args:
            agent_id: The agent storing the memory
            content: Memory content
            memory_type: Type of memory
            importance: Importance score
            metadata: Additional metadata
            sync_to_rag: Override config setting

        Returns:
            The created Memory object
        """
        # Store in local memory
        memory = await self.memory_service.store(
            agent_id=agent_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata,
        )

        # Sync to RAG if enabled and important enough
        should_sync = (
            sync_to_rag if sync_to_rag is not None else self.config.sync_to_rag
        )
        if (
            should_sync
            and self.rag_service
            and importance >= self.config.max_shared_importance
        ):
            await self._sync_to_rag(memory)

        # Sync to external bridges
        for bridge_name, bridge_func in self._external_bridges.items():
            try:
                await bridge_func("store", memory)
            except Exception as e:
                logger.warning("External bridge %s sync failed: %s", bridge_name, e)

        return memory

    async def _sync_to_rag(self, memory: Memory) -> bool:
        """Sync a memory to RAG knowledge base"""
        if not self.rag_service:
            return False

        try:
            doc = {
                "id": f"memory_{memory.id}",
                "content": memory.content,
                "metadata": {
                    "agent_id": memory.agent_id,
                    "memory_type": memory.memory_type,
                    "importance": memory.importance,
                    "created_at": memory.created_at.isoformat(),
                    "source": "agent_memory",
                },
            }

            await self.rag_service.ingest(
                documents=[doc], collection=self.config.rag_collection
            )

            logger.info("Synced memory %s to RAG", memory.id)
            return True
        except Exception as e:
            logger.error("Failed to sync memory to RAG: %s", e)
            return False

    async def recall_with_context(
        self,
        agent_id: str,
        query: str,
        include_rag: bool = True,
        include_shared: bool = True,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Recall memories with additional context from RAG and shared memories.

        Args:
            agent_id: The agent recalling memories
            query: Search query
            include_rag: Include RAG results
            include_shared: Include shared memories from other agents
            limit: Maximum results per source

        Returns:
            Dict with memories from all sources
        """
        result = {
            "query": query,
            "agent_memories": [],
            "rag_results": [],
            "shared_memories": [],
            "assembled_context": "",
        }

        # Get agent's own memories
        agent_memories = await self.memory_service.recall(
            agent_id=agent_id, query=query, limit=limit
        )
        result["agent_memories"] = [m.to_dict() for m in agent_memories]

        # Get RAG results if enabled
        if include_rag and self.rag_service:
            try:
                rag_results = await self.rag_service.search(
                    query=query, collection=self.config.rag_collection, top_k=limit
                )
                result["rag_results"] = rag_results.get("results", [])
            except Exception as e:
                logger.warning("RAG search failed: %s", e)

        # Get shared memories if enabled
        if include_shared and self.config.share_between_agents:
            shared = await self._get_shared_memories(query, limit)
            result["shared_memories"] = shared

        # Assemble context
        result["assembled_context"] = self._assemble_context(result)

        return result

    async def _get_shared_memories(
        self, query: str, limit: int
    ) -> list[dict[str, Any]]:
        """Get shared memories from other agents"""
        if not self.rag_service:
            return []

        try:
            results = await self.rag_service.search(
                query=query,
                collection=self.config.rag_collection,
                top_k=limit,
                filter={"source": "agent_memory"},
            )
            return results.get("results", [])
        except Exception as e:
            logger.warning("Shared memory search failed: %s", e)
            return []

    def _assemble_context(self, result: dict[str, Any]) -> str:
        """Assemble context string from all sources"""
        parts = []

        if result["agent_memories"]:
            parts.append("[Your Memories]")
            for mem in result["agent_memories"][:5]:
                parts.append(f"- {mem['content'][:200]}")

        if result["rag_results"]:
            parts.append("\n[Knowledge Base]")
            for doc in result["rag_results"][:3]:
                parts.append(f"- {doc.get('content', doc.get('text', ''))[:200]}")

        if result["shared_memories"]:
            parts.append("\n[Shared Memories]")
            for mem in result["shared_memories"][:3]:
                parts.append(f"- {mem.get('content', '')[:200]}")

        return "\n".join(parts)

    def register_external_bridge(
        self, name: str, bridge_func: Callable[[str, Memory], Awaitable[None]]
    ) -> None:
        """Register an external memory bridge"""
        self._external_bridges[name] = bridge_func
        logger.info("Registered external bridge: %s", name)

    async def inject_context(
        self, agent_id: str, query: str, max_tokens: int = 1000
    ) -> str:
        """
        Inject relevant context for a query.

        Used by the Context Builder to pull memory context.
        """
        if not self.config.context_injection_enabled:
            return ""

        result = await self.recall_with_context(agent_id=agent_id, query=query, limit=5)

        context = result["assembled_context"]

        # Truncate if needed
        if len(context) > max_tokens * 4:
            context = context[: max_tokens * 4] + "\n... [truncated]"

        return context

    async def share_memory(self, memory_id: str, target_agent_ids: list[str]) -> bool:
        """Share a memory with other agents"""
        # Get the memory
        memory = self.memory_service._memories.get(memory_id)
        if not memory:
            return False

        # Check if shareable
        if memory.importance < self.config.max_shared_importance:
            logger.warning("Memory %s not important enough to share", memory_id)
            return False

        # Sync to RAG for sharing
        if self.rag_service:
            await self._sync_to_rag(memory)

        logger.info("Shared memory %s with %s agents", memory_id, len(target_agent_ids))
        return True

    async def get_bridge_stats(self) -> dict[str, Any]:
        """Get statistics about the memory bridge"""
        return {
            "config": {
                "sync_to_rag": self.config.sync_to_rag,
                "rag_collection": self.config.rag_collection,
                "share_between_agents": self.config.share_between_agents,
                "context_injection_enabled": self.config.context_injection_enabled,
            },
            "external_bridges": list(self._external_bridges.keys()),
            "memory_stats": self.memory_service.get_stats(),
        }
