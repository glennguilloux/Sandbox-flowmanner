"""
Memory Bridge - Connects agent memory to RAG and other systems

Enables agents to store, recall, and share memories across
the platform's memory systems.
"""

from .memory_bridge import MemoryBridge
from .memory_service import MemoryService

__all__ = ["MemoryBridge", "MemoryService"]
