#!/usr/bin/env python3
"""
A2A Agent Wrapper - Wraps existing agents for A2A protocol

Provides wrappers for LangGraph, MetaLoop, and Nexus agents to enable
seamless agent-to-agent communication via FastA2A protocol.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .a2a_server import A2AMessage, MessageType, get_a2a_server

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Standardized agent response"""

    content: str
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0

    def to_a2a_message(self, sender: str, receiver: str, context_id: str | None = None) -> A2AMessage:
        return A2AMessage(
            type=MessageType.RESPONSE,
            sender=sender,
            receiver=receiver,
            content=self.content,
            context_id=context_id,
            metadata={
                "success": self.success,
                "tool_calls": self.tool_calls,
                "tokens_used": self.tokens_used,
                **self.metadata,
            },
        )


class A2AAgentWrapper(ABC):
    """Base wrapper for A2A-compatible agents"""

    def __init__(self, agent_id: str, agent_name: str, capabilities: list[str] = None):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.capabilities = capabilities or []
        self._a2a_server = get_a2a_server()

    @abstractmethod
    async def process_message(self, message: A2AMessage) -> AgentResponse:
        """Process incoming A2A message and return response"""
        pass

    @abstractmethod
    async def stream_response(self, message: A2AMessage) -> AsyncIterator[str]:
        """Stream response chunks for real-time output"""
        pass

    def register(self):
        """Register this agent with A2A server"""
        self._a2a_server.agent_registry.register_agent(
            self.agent_id,
            {
                "name": self.agent_name,
                "description": self.__class__.__doc__ or "",
                "capabilities": self.capabilities,
                "status": "available",
                "wrapper_type": self.__class__.__name__,
            },
        )

    def unregister(self):
        """Unregister this agent"""
        self._a2a_server.agent_registry.unregister_agent(self.agent_id)


class LangGraphAgentWrapper(A2AAgentWrapper):
    """
    Wrapper for LangGraph-based agents.

    Enables LangGraph agents to communicate via A2A protocol.
    Supports streaming responses and tool calls.
    """

    def __init__(
        self,
        agent_id: str = "langgraph-agent",
        agent_name: str = "LangGraph Agent",
        capabilities: list[str] = None,
    ):
        super().__init__(
            agent_id,
            agent_name,
            capabilities or ["chat", "reasoning", "tool_calling", "streaming"],
        )
        self._agent = None
        self._config: dict[str, Any] = {}

    def set_agent(self, agent: Any, config: dict[str, Any] = None):
        """Set the underlying LangGraph agent instance"""
        self._agent = agent
        self._config = config or {}

    async def process_message(self, message: A2AMessage) -> AgentResponse:
        """Process message through LangGraph agent"""
        try:
            if not self._agent:
                # Try to import and create agent
                try:
                    from app.services.llm_langgraph.agent import get_agent

                    self._agent = get_agent()  # type: ignore[assignment]
                except ImportError:
                    return AgentResponse(
                        content="LangGraph agent not available",
                        success=False,
                        metadata={"error": "agent_not_initialized"},
                    )

            # Process through llm_langgraph agent (.run() API)
            result = self._agent.run(  # type: ignore[attr-defined]
                message.content,
                context=self._config,
            )

            # Extract response
            if isinstance(result, dict):
                content = result.get("response", result.get("messages", ""))
                if isinstance(content, list):
                    last = content[-1] if content else {}
                    content = getattr(last, "content", str(last))
                return AgentResponse(
                    content=str(content),
                    success=result.get("status", "ok") == "ok",
                    tokens_used=result.get("usage", {}).get("total_tokens", 0),
                    metadata={"agent_type": "langgraph", "model_id": result.get("model_id", "")},
                )

            return AgentResponse(content=str(result), success=True, metadata={"agent_type": "langgraph"})

        except Exception as e:
            logger.error("LangGraph agent error: %s", e)
            return AgentResponse(
                content=f"Error processing message: {e!s}",
                success=False,
                metadata={"error": str(e)},
            )

    async def stream_response(self, message: A2AMessage) -> AsyncIterator[str]:  # type: ignore[override]
        """Stream response from LangGraph agent"""
        try:
            if not self._agent:
                try:
                    from app.services.llm_langgraph.agent import get_agent

                    self._agent = get_agent()  # type: ignore[assignment]
                except ImportError:
                    yield "LangGraph agent not available"
                    return

            # llm_langgraph agent uses .run() (sync) — yield the full result
            result = self._agent.run(  # type: ignore[attr-defined]
                message.content,
                context=self._config,
            )
            if isinstance(result, dict):
                content = result.get("response", str(result))
                if isinstance(content, list):
                    last = content[-1] if content else {}
                    content = getattr(last, "content", str(last))
                yield str(content)
            else:
                yield str(result)

        except Exception as e:
            logger.error("LangGraph streaming error: %s", e)
            yield f"Error: {e!s}"


class MetaLoopAgentWrapper(A2AAgentWrapper):
    """
    Wrapper for MetaLoop agents.

    Enables MetaLoop 6-phase orchestration agents to communicate via A2A.
    Supports self-improvement cycles and feedback integration.
    """

    def __init__(
        self,
        agent_id: str = "metaloop-agent",
        agent_name: str = "MetaLoop Agent",
        capabilities: list[str] = None,
    ):
        super().__init__(
            agent_id,
            agent_name,
            capabilities
            or [
                "self_improvement",
                "reasoning",
                "feedback_loop",
                "hallucination_detection",
                "memory_storage",
                "cost_tracking",
            ],
        )
        self._metaloop = None

    def _get_metaloop(self):
        """Lazy load MetaLoop service"""
        if self._metaloop is None:
            try:
                from app.services.meta_loop_feedback_integration import (
                    MetaLoopFeedbackIntegration,
                )

                self._metaloop = MetaLoopFeedbackIntegration()
            except ImportError:
                try:
                    from app.services.self_improvement_service import (
                        SelfImprovementService,
                    )

                    self._metaloop = SelfImprovementService()
                except ImportError:
                    logger.warning("MetaLoop service not available")
        return self._metaloop

    async def process_message(self, message: A2AMessage) -> AgentResponse:
        """Process message through MetaLoop phases"""
        try:
            metaloop = self._get_metaloop()

            if not metaloop:
                return AgentResponse(
                    content="MetaLoop service not available",
                    success=False,
                    metadata={"error": "service_not_initialized"},
                )

            # Execute MetaLoop cycle
            if hasattr(metaloop, "execute_cycle"):
                result = await metaloop.execute_cycle(query=message.content, context=message.metadata)
            elif hasattr(metaloop, "process"):
                result = await metaloop.process(message.content)
            else:
                result = await metaloop.run(message.content)

            # Extract response
            if isinstance(result, dict):
                return AgentResponse(
                    content=result.get("response", str(result)),
                    success=True,
                    metadata={
                        "phases_completed": result.get("phases_completed", []),
                        "improvements": result.get("improvements", []),
                        "cost": result.get("cost", 0),
                        "agent_type": "metaloop",
                    },
                )

            return AgentResponse(content=str(result), success=True, metadata={"agent_type": "metaloop"})

        except Exception as e:
            logger.error("MetaLoop agent error: %s", e)
            return AgentResponse(
                content=f"Error processing message: {e!s}",
                success=False,
                metadata={"error": str(e)},
            )

    async def stream_response(self, message: A2AMessage) -> AsyncIterator[str]:  # type: ignore[override]
        """Stream MetaLoop phases"""
        try:
            metaloop = self._get_metaloop()

            if not metaloop:
                yield "MetaLoop service not available"
                return

            # Stream through phases
            phases = [
                "query_processing",
                "response_generation",
                "hallucination_detection",
                "memory_storage",
                "response_delivery",
                "cost_tracking",
            ]

            for phase in phases:
                yield f"[Phase: {phase}]\n"

                if hasattr(metaloop, f"_phase_{phase}"):
                    phase_method = getattr(metaloop, f"_phase_{phase}")
                    if asyncio.iscoroutinefunction(phase_method):
                        result = await phase_method(message.content)
                    else:
                        result = phase_method(message.content)

                    if isinstance(result, dict) and "output" in result:
                        yield f"  {result['output']}\n"
                    else:
                        yield "  Completed\n"
                else:
                    yield "  Skipped\n"

        except Exception as e:
            logger.error("MetaLoop streaming error: %s", e)
            yield f"Error: {e!s}"


class NexusOrchestratorWrapper(A2AAgentWrapper):
    """
    Wrapper for Nexus Orchestrator.

    Enables Nexus orchestration capabilities via A2A protocol.
    Supports tool composition, capability discovery, and distributed execution.
    """

    def __init__(
        self,
        agent_id: str = "nexus-orchestrator",
        agent_name: str = "Nexus Orchestrator",
        capabilities: list[str] = None,
    ):
        super().__init__(
            agent_id,
            agent_name,
            capabilities
            or [
                "orchestration",
                "tool_composition",
                "capability_discovery",
                "distributed_execution",
                "cost_optimization",
                "failure_analysis",
            ],
        )
        self._orchestrator = None

    def _get_orchestrator(self):
        """Lazy load Nexus orchestrator"""
        if self._orchestrator is None:
            try:
                from app.services.nexus.orchestrator import get_nexus_orchestrator

                self._orchestrator = get_nexus_orchestrator()
            except ImportError:
                logger.warning("Nexus orchestrator not available")
        return self._orchestrator

    async def process_message(self, message: A2AMessage) -> AgentResponse:
        """Process message through Nexus orchestrator"""
        try:
            orchestrator = self._get_orchestrator()

            if not orchestrator:
                return AgentResponse(
                    content="Nexus orchestrator not available",
                    success=False,
                    metadata={"error": "orchestrator_not_initialized"},
                )

            # Parse intent from message
            intent = message.metadata.get("intent", "execute")

            if intent == "discover":
                # Discover capabilities
                capabilities = await orchestrator.discover_capabilities(query=message.content)
                return AgentResponse(
                    content=f"Discovered {len(capabilities)} capabilities",
                    success=True,
                    metadata={"capabilities": capabilities, "agent_type": "nexus"},
                )

            elif intent == "compose":
                # Compose tools for task
                composition = await orchestrator.compose_tools(
                    task_description=message.content,
                    constraints=message.metadata.get("constraints", {}),
                )
                return AgentResponse(
                    content=f"Composed {len(composition.get('tools', []))} tools",
                    success=True,
                    metadata={"composition": composition, "agent_type": "nexus"},
                )

            else:
                # Execute task
                result = await orchestrator.execute(task=message.content, context=message.metadata)

                return AgentResponse(
                    content=result.get("output", str(result)),
                    success=result.get("success", True),
                    metadata={
                        "execution_plan": result.get("plan"),
                        "tools_used": result.get("tools_used", []),
                        "cost": result.get("cost", 0),
                        "agent_type": "nexus",
                    },
                )

        except Exception as e:
            logger.error("Nexus orchestrator error: %s", e)
            return AgentResponse(
                content=f"Error processing message: {e!s}",
                success=False,
                metadata={"error": str(e)},
            )

    async def stream_response(self, message: A2AMessage) -> AsyncIterator[str]:  # type: ignore[override]
        """Stream Nexus execution progress"""
        try:
            orchestrator = self._get_orchestrator()

            if not orchestrator:
                yield "Nexus orchestrator not available"
                return

            # Stream execution steps
            yield "[Planning execution...]\n"

            if hasattr(orchestrator, "stream_execute"):
                async for step in orchestrator.stream_execute(message.content):
                    yield f"{step}\n"
            else:
                # Fallback to regular execute
                result = await orchestrator.execute(message.content)
                yield f"Result: {result.get('output', 'Completed')}\n"

        except Exception as e:
            logger.error("Nexus streaming error: %s", e)
            yield f"Error: {e!s}"


# Agent wrapper factory
def create_agent_wrapper(agent_type: str, **kwargs) -> A2AAgentWrapper:
    """
    Factory function to create agent wrappers.

    Args:
        agent_type: Type of agent ("langgraph", "metaloop", "nexus")
        **kwargs: Additional arguments passed to wrapper constructor

    Returns:
        A2AAgentWrapper instance
    """
    wrappers = {
        "langgraph": LangGraphAgentWrapper,
        "metaloop": MetaLoopAgentWrapper,
        "nexus": NexusOrchestratorWrapper,
    }

    wrapper_class = wrappers.get(agent_type.lower())
    if not wrapper_class:
        raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(wrappers.keys())}")

    return wrapper_class(**kwargs)  # type: ignore[abstract]


# Register default agents
def register_default_agents():
    """Register default agent wrappers with A2A server"""
    wrappers = [
        LangGraphAgentWrapper(),
        MetaLoopAgentWrapper(),
        NexusOrchestratorWrapper(),
    ]

    for wrapper in wrappers:
        wrapper.register()
        logger.info("Registered A2A agent: %s", wrapper.agent_id)

    return wrappers
