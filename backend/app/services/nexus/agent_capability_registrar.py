"""
Agent Capability Registrar - Self-Registering Agents System

UPGRADE 6: Self-Registering Agents
Enables agents to auto-discover tools and register as capabilities.

Features:
- Auto-discovery of tools from ToolDiscoveryService
- Self-registration in CapabilityRegistry
- Dynamic capability exposure
- Health monitoring and auto-recovery
- Capability versioning and deprecation
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentCapability:
    """Represents a capability exposed by an agent"""

    id: str
    agent_id: str
    name: str
    description: str
    category: str
    tools: list[str]  # Tool IDs this capability uses
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable | None = None
    requires_auth: bool = True
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    rate_limit: int | None = None
    timeout_seconds: int = 60
    version: str = "1.0.0"
    status: str = "active"  # active, deprecated, disabled
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tools": self.tools,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "requires_auth": self.requires_auth,
            "cost_estimate": self.cost_estimate,
            "rate_limit": self.rate_limit,
            "timeout_seconds": self.timeout_seconds,
            "version": self.version,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class AgentRegistration:
    """Registration record for a self-registered agent"""

    agent_id: str
    agent_name: str
    agent_type: str
    capabilities: list[str]  # Capability IDs
    discovered_tools: list[str]  # Tool IDs discovered
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "capabilities": self.capabilities,
            "discovered_tools": self.discovered_tools,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "status": self.status,
            "metadata": self.metadata,
        }


class AgentCapabilityRegistrar:
    """
    Manages self-registration of agents as capabilities.

    UPGRADE 6: Self-Registering Agents

    Flow:
    1. Agent calls register_agent() with its metadata
    2. Registrar discovers relevant tools from ToolDiscoveryService
    3. Agent's capabilities are registered in CapabilityRegistry
    4. Heartbeat system monitors agent health
    5. Auto-recovery on failure
    """

    def __init__(self, capability_registry=None, tool_discovery=None, db_session=None):
        self._capability_registry = capability_registry
        self._tool_discovery = tool_discovery
        self._db_session = db_session

        # Agent registrations indexed by agent_id
        self._registrations: dict[str, AgentRegistration] = {}

        # Capabilities indexed by capability_id
        self._capabilities: dict[str, AgentCapability] = {}

        # Heartbeat tracking
        self._heartbeat_timeout = timedelta(minutes=5)
        self._heartbeat_task: asyncio.Task | None = None

        # Tool discovery cache
        self._tool_cache: dict[str, dict[str, Any]] = {}

    @property
    def capability_registry(self):
        """Lazy-load capability registry"""
        if self._capability_registry is None:
            try:
                from app.services.nexus.capability_registry import (
                    CapabilityRegistry,
                    get_capability_registry,
                )

                self._capability_registry = get_capability_registry()
            except ImportError:
                logger.warning("CapabilityRegistry not available")
        return self._capability_registry

    @property
    def tool_discovery(self):
        """Lazy-load tool discovery service"""
        if self._tool_discovery is None:
            try:
                from app.services.tool_discovery_service import get_discovery_service

                self._tool_discovery = get_discovery_service()
            except ImportError:
                logger.warning("ToolDiscoveryService not available")
        return self._tool_discovery

    async def register_agent(
        self,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        description: str,
        capabilities: list[dict[str, Any]],
        tool_categories: list[str] | None = None,
        tool_tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRegistration:
        """
        Register an agent with auto-discovered tools and capabilities.

        Args:
            agent_id: Unique agent identifier
            agent_name: Human-readable agent name
            agent_type: Type of agent (e.g., "meta_loop", "specialist", "orchestrator")
            description: Agent description
            capabilities: List of capability definitions
            tool_categories: Optional categories to discover tools from
            tool_tags: Optional tags to filter discovered tools
            metadata: Additional agent metadata

        Returns:
            AgentRegistration record
        """
        logger.info(f"Registering agent: {agent_name} ({agent_id})")

        # Discover tools for this agent
        discovered_tools = await self._discover_tools_for_agent(
            agent_type, tool_categories, tool_tags
        )

        # Register capabilities
        registered_capabilities = []
        for cap_def in capabilities:
            cap = await self._register_capability(
                agent_id=agent_id, cap_def=cap_def, discovered_tools=discovered_tools
            )
            if cap:
                registered_capabilities.append(cap.id)
                self._capabilities[cap.id] = cap

        # Create registration record
        registration = AgentRegistration(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=agent_type,
            capabilities=registered_capabilities,
            discovered_tools=[
                t.get("tool_id") for t in discovered_tools if t.get("tool_id")
            ],
            metadata=metadata or {},
        )

        self._registrations[agent_id] = registration

        # Persist to database if available
        await self._persist_registration(registration)

        logger.info(
            f"Agent {agent_name} registered with {len(registered_capabilities)} capabilities"
        )

        return registration

    async def _discover_tools_for_agent(
        self,
        agent_type: str,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Discover relevant tools for an agent based on type and filters.

        Uses ToolDiscoveryService for semantic tool discovery.
        """
        discovered = []

        if not self.tool_discovery:
            logger.warning("ToolDiscoveryService not available for tool discovery")
            return discovered

        try:
            # Build discovery query from agent type
            query = f"tools for {agent_type} agent"

            # Search for relevant tools
            results = self.tool_discovery.search(
                query=query, top_k=20, category_filter=categories
            )

            for result in results:
                tool_data = result.tool.to_dict()
                tool_data["relevance_score"] = result.score
                tool_data["match_reasons"] = result.match_reasons
                discovered.append(tool_data)

            # Also list tools by category if specified
            if categories:
                for category in categories:
                    tools = self.tool_discovery.embedding_service.list_tools(
                        category=category
                    )
                    for tool in tools:
                        if tool.tool_id not in [t.get("tool_id") for t in discovered]:
                            discovered.append(tool.to_dict())

            logger.info(f"Discovered {len(discovered)} tools for {agent_type} agent")

        except Exception as e:
            logger.error(f"Tool discovery failed: {e}")

        return discovered

    async def _register_capability(
        self,
        agent_id: str,
        cap_def: dict[str, Any],
        discovered_tools: list[dict[str, Any]],
    ) -> AgentCapability | None:
        """Register a single capability for an agent"""
        try:
            # Generate capability ID
            cap_id = f"agent:{agent_id}:{cap_def.get('name', 'unknown').lower().replace(' ', '_')}"

            # Map tools to capability
            tool_ids = cap_def.get("tools", [])

            # If no tools specified, use discovered tools
            if not tool_ids and discovered_tools:
                tool_ids = [
                    t.get("tool_id") for t in discovered_tools[:5] if t.get("tool_id")
                ]

            # Create capability
            capability = AgentCapability(
                id=cap_id,
                agent_id=agent_id,
                name=cap_def.get("name", "Unnamed Capability"),
                description=cap_def.get("description", ""),
                category=cap_def.get("category", "agent"),
                tools=tool_ids,
                input_schema=cap_def.get("input_schema", {}),
                output_schema=cap_def.get("output_schema", {}),
                handler=cap_def.get("handler"),
                requires_auth=cap_def.get("requires_auth", True),
                cost_estimate=cap_def.get("cost_estimate", {}),
                rate_limit=cap_def.get("rate_limit"),
                timeout_seconds=cap_def.get("timeout_seconds", 60),
                version=cap_def.get("version", "1.0.0"),
                metadata=cap_def.get("metadata", {}),
            )

            # Register in CapabilityRegistry if available
            if self.capability_registry:
                from app.services.nexus.capability_registry import Capability

                # Create Capability for registry
                reg_cap = Capability(
                    id=capability.id,
                    name=capability.name,
                    description=capability.description,
                    category=capability.category,
                    handler=capability.handler
                    or self._create_default_handler(capability),
                    input_schema=capability.input_schema,
                    output_schema=capability.output_schema,
                    requires_auth=capability.requires_auth,
                    cost_estimate=capability.cost_estimate,
                    rate_limit=capability.rate_limit,
                    timeout_seconds=capability.timeout_seconds,
                    metadata={
                        "agent_id": agent_id,
                        "tools": tool_ids,
                        "version": capability.version,
                    },
                )

                self.capability_registry.register(reg_cap)
                logger.info(f"Registered capability: {cap_id}")

            return capability

        except Exception as e:
            logger.error(f"Failed to register capability: {e}")
            return None

    def _create_default_handler(self, capability: AgentCapability) -> Callable:
        """Create a default handler for agent capabilities"""

        async def default_handler(params: dict[str, Any]) -> dict[str, Any]:
            """Default capability handler that routes to agent"""
            return {
                "status": "routed",
                "capability_id": capability.id,
                "agent_id": capability.agent_id,
                "tools": capability.tools,
                "params": params,
                "message": "Capability routed to agent for execution",
            }

        return default_handler

    async def _persist_registration(self, registration: AgentRegistration) -> None:
        """Persist registration to database"""
        if not self._db_session:
            return

        try:
            # Import model
            from app.models.agent import AgentRegistration as AgentRegistrationModel

            # Check if exists
            existing = (
                self._db_session.query(AgentRegistrationModel)
                .filter(AgentRegistrationModel.agent_id == registration.agent_id)
                .first()
            )

            if existing:
                existing.agent_name = registration.agent_name
                existing.agent_type = registration.agent_type
                existing.capabilities = registration.capabilities
                existing.discovered_tools = registration.discovered_tools
                existing.status = registration.status
                existing.updated_at = datetime.now(UTC)
            else:
                new_record = AgentRegistrationModel(
                    agent_id=registration.agent_id,
                    agent_name=registration.agent_name,
                    agent_type=registration.agent_type,
                    capabilities=registration.capabilities,
                    discovered_tools=registration.discovered_tools,
                    status=registration.status,
                    metadata=registration.metadata,
                )
                self._db_session.add(new_record)

            self._db_session.commit()
            logger.info(f"Persisted registration for {registration.agent_name}")

        except Exception as e:
            logger.error(f"Failed to persist registration: {e}")
            if self._db_session:
                self._db_session.rollback()

    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent and its capabilities.

        Args:
            agent_id: The agent ID to unregister

        Returns:
            True if unregistered successfully
        """
        if agent_id not in self._registrations:
            logger.warning(f"Agent {agent_id} not registered")
            return False

        registration = self._registrations[agent_id]

        # Unregister capabilities from CapabilityRegistry
        if self.capability_registry:
            for cap_id in registration.capabilities:
                self.capability_registry.unregister(cap_id)
                logger.info(f"Unregistered capability: {cap_id}")

        # Remove from local storage
        for cap_id in registration.capabilities:
            self._capabilities.pop(cap_id, None)

        del self._registrations[agent_id]

        logger.info(f"Unregistered agent: {agent_id}")
        return True

    async def heartbeat(self, agent_id: str) -> bool:
        """
        Record heartbeat from an agent.

        Args:
            agent_id: The agent ID sending heartbeat

        Returns:
            True if heartbeat recorded, False if agent not registered
        """
        if agent_id not in self._registrations:
            return False

        self._registrations[agent_id].last_heartbeat = datetime.now(UTC)
        self._registrations[agent_id].status = "active"

        return True

    async def start_health_monitor(self) -> None:
        """Start background health monitoring task"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            logger.warning("Health monitor already running")
            return

        self._heartbeat_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Started agent health monitor")

    async def stop_health_monitor(self) -> None:
        """Stop health monitoring task"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
        logger.info("Stopped agent health monitor")

    async def _health_monitor_loop(self) -> None:
        """Background loop to monitor agent health"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._check_agent_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    async def _check_agent_health(self) -> None:
        """Check health of all registered agents"""
        now = datetime.now(UTC)

        for agent_id, registration in self._registrations.items():
            time_since_heartbeat = now - registration.last_heartbeat

            if time_since_heartbeat > self._heartbeat_timeout:
                logger.warning(f"Agent {agent_id} heartbeat timeout")
                registration.status = "unhealthy"

                # Disable capabilities
                for cap_id in registration.capabilities:
                    if cap_id in self._capabilities:
                        self._capabilities[cap_id].status = "disabled"
            else:
                # Restore if was unhealthy
                if registration.status == "unhealthy":
                    logger.info(f"Agent {agent_id} recovered")
                    registration.status = "active"

                    # Re-enable capabilities
                    for cap_id in registration.capabilities:
                        if cap_id in self._capabilities:
                            self._capabilities[cap_id].status = "active"

    def get_agent(self, agent_id: str) -> AgentRegistration | None:
        """Get agent registration by ID"""
        return self._registrations.get(agent_id)

    def get_capability(self, capability_id: str) -> AgentCapability | None:
        """Get capability by ID"""
        return self._capabilities.get(capability_id)

    def list_agents(self, status: str | None = None) -> list[AgentRegistration]:
        """List all registered agents, optionally filtered by status"""
        agents = list(self._registrations.values())
        if status:
            agents = [a for a in agents if a.status == status]
        return agents

    def list_capabilities(
        self,
        agent_id: str | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> list[AgentCapability]:
        """List capabilities with optional filters"""
        caps = list(self._capabilities.values())

        if agent_id:
            caps = [c for c in caps if c.agent_id == agent_id]
        if category:
            caps = [c for c in caps if c.category == category]
        if status:
            caps = [c for c in caps if c.status == status]

        return caps

    def get_stats(self) -> dict[str, Any]:
        """Get registrar statistics"""
        agents = list(self._registrations.values())
        caps = list(self._capabilities.values())

        return {
            "total_agents": len(agents),
            "active_agents": len([a for a in agents if a.status == "active"]),
            "unhealthy_agents": len([a for a in agents if a.status == "unhealthy"]),
            "total_capabilities": len(caps),
            "active_capabilities": len([c for c in caps if c.status == "active"]),
            "capabilities_by_category": self._count_by_field(caps, "category"),
            "agents_by_type": self._count_by_field(agents, "agent_type"),
        }

    def _count_by_field(self, items: list[Any], field: str) -> dict[str, int]:
        """Count items by a field value"""
        counts = {}
