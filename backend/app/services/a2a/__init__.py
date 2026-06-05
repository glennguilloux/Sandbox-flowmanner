#!/usr/bin/env python3
"""
A2A (Agent-to-Agent) Communication Module

Provides FastA2A protocol implementation for inter-agent communication.
"""

from .a2a_agent_wrapper import (
    A2AAgentWrapper,
    AgentResponse,
    LangGraphAgentWrapper,
    MetaLoopAgentWrapper,
    NexusOrchestratorWrapper,
    create_agent_wrapper,
    register_default_agents,
)
from .a2a_server import (
    A2AMessage,
    A2AServer,
    A2ASession,
    MessageType,
    SessionState,
    get_a2a_server,
)

__all__ = [
    # Wrappers
    "A2AAgentWrapper",
    "A2AMessage",
    # Server
    "A2AServer",
    "A2ASession",
    "AgentResponse",
    "LangGraphAgentWrapper",
    "MessageType",
    "MetaLoopAgentWrapper",
    "NexusOrchestratorWrapper",
    "SessionState",
    "create_agent_wrapper",
    "get_a2a_server",
    "register_default_agents",
]
