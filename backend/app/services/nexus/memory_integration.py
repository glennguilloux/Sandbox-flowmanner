#!/usr/bin/env python3
"""
Memory Integration for LangGraph Chat

Provides:
- Memory injection at session start (Item 7)
- Post-conversation auto-extraction (Item 8)
"""

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class MemoryIntegration:
    """
    Integrates long-term memory into chat sessions.

    Features:
    - Injects relevant memories at session start
    - Auto-extracts important information after conversations
    - Manages memory context for agents
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self._memory_service = None

    async def _get_memory_service(self):
        """Get or create memory service instance"""
        if self._memory_service is None:
            try:
                from app.database import SessionLocal
                from app.services.memory_service import MemoryService

                if self.db is None:
                    self.db = SessionLocal()

                self._memory_service = MemoryService(self.db)
            except Exception as e:
                logger.error('Failed to initialize memory service: %s', e)
                return None
        return self._memory_service

    async def inject_memories(
        self, user_id: int, query: str, thread_id: str, limit: int = 5
    ) -> str | None:
        """
        Inject relevant memories into the conversation context.

        Item 7: Memory injection at session start

        Args:
            user_id: User ID to recall memories for
            query: Current user message to find relevant memories
            thread_id: Thread ID for context
            limit: Maximum number of memories to inject

        Returns:
            Formatted memory context string or None
        """
        try:
            memory_service = await self._get_memory_service()
            if memory_service is None:
                return None

            # Recall relevant memories based on query
            memories = await memory_service.retrieve_by_query(
                agent_id=f"user_{user_id}", query=query, limit=limit, min_importance=0.3
            )

            if not memories:
                logger.info('No relevant memories found for user %s', user_id)
                return None

            # Format memories for context injection
            memory_context = "\n".join(
                [f"- {m.get('content', '')}" for m in memories[:limit]]
            )

            logger.info('Injected %s memories for user %s', len(memories[:limit]), user_id)
            return f"[Relevant memories from past conversations:]\n{memory_context}"

        except Exception as e:
            logger.error('Error injecting memories: %s', e)
            return None

    async def extract_and_store(
        self, user_id: int, conversation: list[dict[str, str]], thread_id: str
    ) -> bool:
        """
        Extract important information from conversation and store as memories.

        Item 8: Post-conversation auto-extraction

        Args:
            user_id: User ID to store memories for
            conversation: List of messages with 'role' and 'content'
            thread_id: Thread ID for reference

        Returns:
            True if extraction successful
        """
        try:
            memory_service = await self._get_memory_service()
            if memory_service is None:
                return False

            # Extract key information from conversation
            extracted = await self._extract_key_information(conversation)

            if not extracted:
                logger.info('No key information extracted from thread %s', thread_id)
                return True  # Not an error, just nothing to store

            # Store each extracted item as a memory
            stored_count = 0
            for item in extracted:
                try:
                    await memory_service.store(
                        agent_id=f"user_{user_id}",
                        content=item["content"],
                        memory_type=item.get("memory_type", "long_term"),
                        metadata={
                            "thread_id": thread_id,
                            "extracted_at": datetime.now(UTC).isoformat(),
                            "category": item.get("category", "general"),
                        },
                        tags=item.get("tags", []),
                        user_id=user_id,
                    )
                    stored_count += 1
                except Exception as e:
                    logger.error('Error storing memory: %s', e)

            logger.info('Stored %s memories from thread %s', stored_count, thread_id)
            return True

        except Exception as e:
            logger.error('Error in extract_and_store: %s', e)
            return False

    async def _extract_key_information(
        self, conversation: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        """
        Extract key information from a conversation.

        Uses heuristics to identify important information:
        - User preferences
        - Facts about the user
        - Important decisions or conclusions
        - Action items
        """
        extracted = []

        # Combine conversation for analysis
        full_text = "\n".join(
            [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in conversation]
        )

        # Simple extraction heuristics
        preference_keywords = [
            "prefer",
            "like",
            "want",
            "need",
            "favorite",
            "always",
            "never",
        ]
        fact_keywords = [
            "my name is",
            "i am",
            "i work",
            "i live",
            "my job",
            "my company",
        ]
        important_keywords = ["important", "remember", "note", "save", "don't forget"]

        for msg in conversation:
            if msg.get("role") != "user":
                continue

            content = msg.get("content", "").lower()

            # Check for preferences
            if any(kw in content for kw in preference_keywords):
                extracted.append(
                    {
                        "content": msg.get("content", ""),
                        "memory_type": "long_term",
                        "category": "preference",
                        "tags": ["preference", "user"],
                    }
                )

            # Check for facts
            elif any(kw in content for kw in fact_keywords):
                extracted.append(
                    {
                        "content": msg.get("content", ""),
                        "memory_type": "long_term",
                        "category": "fact",
                        "tags": ["fact", "user"],
                    }
                )

            # Check for important items
            elif any(kw in content for kw in important_keywords):
                extracted.append(
                    {
                        "content": msg.get("content", ""),
                        "memory_type": "long_term",
                        "category": "important",
                        "tags": ["important", "user"],
                    }
                )

        return extracted


# Singleton instance
_memory_integration = None


def get_memory_integration(db_session=None) -> MemoryIntegration:
    """Get or create memory integration instance"""
    global _memory_integration
    if _memory_integration is None:
        _memory_integration = MemoryIntegration(db_session)
    return _memory_integration
