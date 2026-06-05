"""
Nexus Orchestrator Service

Central coordination service that enables any subsystem to request capabilities from any other.
Every service registers what it can do, and Nexus provides a unified interface for cross-system operations.
"""

from .capability_registry import Capability, CapabilityRegistry
from .orchestrator import NexusOrchestrator

__all__ = [
    "Capability",
    "CapabilityRegistry",
    "NexusOrchestrator",
]
