"""SQLAlchemy Base and shared model utilities."""

from datetime import UTC, datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class UUIDMixin:
    """Mixin that adds a UUID primary key."""

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )


# Import all models to register them with Base.metadata
# Order matters for FK resolution - import base tables first

# User model (no dependencies on other app models)
# Agent models (consolidated from 5 files, H4.3)
# Agent versioning (Phase 3.1)
from app.models.agent import (
    Agent,
    AgentCapability,
    AgentMemory,
    AgentMessage,
    AgentRegistration,
    AgentState,
    AgentTemplate,
    AgentVersion,
    DebateRound,
    EscalationRecord,
    HandoffRecord,
)

# Binding models (Phase 2.3)
from app.models.binding_models import (
    AgentCapabilityBinding,
    AgentToolBinding,
    CapabilityDependency,
)

# Blueprint + Run unified models (Phase 10.1)
from app.models.blueprint_models import (
    Blueprint,
    BlueprintVersion,
    Run,
)

# BYOK (depends on User)
from app.models.byok_models import UserAPIKey
from app.models.capability_catalog_models import Capability, CapabilityVersion
from app.models.capability_models import (
    Action,
    Budget,
    BudgetExhausted,
    CapabilityToken,
    PydanticAdapter,
    ResourceRef,
)

# H3 Capability models (H3.1 type-safe Pydantic schemas)
from app.models.capability_models import (
    Capability as TypedCapability,
)

# Chat models (depend on User)
from app.models.chat import ChatFile, ChatFolder, ChatMessage, ChatThread

# Circuit breaker models (Phase 6.4)
from app.models.circuit_breaker_models import MissionCircuitBreaker

# Community models (Phase 3 comments + drift remediation chunk 8)
from app.models.community_models import CommunityComment, CommunityTemplate

# Evaluation models
from app.models.evaluation_models import (
    EvalRun,
    GoldenDataset,
    GoldenTestCase,
)
from app.models.extension import Extension

# Workflow models (consolidated from GraphWorkflow + Flow, H4.2)
from app.models.graph import (
    GraphExecution,
    GraphState,
    # Backward-compat aliases:
    GraphWorkflow,
    Workflow,
    WorkflowExecution,
    WorkflowState,
)

# HITL models (Phase 6.2)
from app.models.hitl_models import InboxItem, WorkspaceHITLConfig

# Idempotency models
from app.models.idempotency import IdempotencyKey, IdempotencyRequestLog

# Integration models (HTTP outbound + OAuth)
from app.models.integration_models import (
    HttpIntegrationConfig,
    HttpIntegrationLog,
    UserOAuthApp,
    UserOAuthConnection,
)

# Knowledge graph models (Phase 5 improvement foundation)
from app.models.knowledge_graph_models import KnowledgeEdge, KnowledgeNode

# Cost category enum + event DTO (Q1-B Chunk 4)
from app.models.cost_event import CostCategory, CostEvent

# LLM call record model (H1.3 observability)
from app.models.llm_call_record import LLMCallRecord

# Materialization state model (Phase 1.1e)
from app.models.materialization_models import MaterializationState

# Memory models (canonical + legacy)
from app.models.memory_models import MemoryEntry

# Mission versioning (Phase 3.1 — already existed, now normalized)
from app.models.mission_advanced_models import MissionVersion

# Mission models
from app.models.mission_models import (
    Mission,
    MissionImprovement,
    MissionLog,
    MissionTask,
)

# Partner models (depend on User)
from app.models.partner_revenue_models import (
    Partner,
    PartnerRevenue,
)

# Playground sandbox models (Phase 4)
from app.models.playground_models import PlaygroundSandbox

# Plugin models (Phase 9.1)
from app.models.plugin_models import InstalledPlugin

# Sandbox models (sandboxd integration)
from app.models.sandbox_models import MissionSandbox

# Subscription models (depend on User)
from app.models.subscription_models import (
    SubscriptionTier,
    UserSubscription,
)

# Substrate event model (H2.1 event-sourced execution)
from app.models.substrate_models import SubstrateEvent

# Swarm models
from app.models.swarm import (
    SwarmAgent,
    SwarmConsensusRound,
    SwarmProfile,
    SwarmTask,
)

# Orchestrator models
from app.models.swarm_models import OrchestratorExecution, OrchestratorTask

# Canonical tool + capability catalog models (Phase 1)
from app.models.tool_catalog_models import Tool, ToolVersion

# Topology models (Phase 1.1f)
from app.models.topology_models import (
    TopologyEdge,
    TopologyNode,
    TopologySnapshot,
)
from app.models.user import User

# Workflow versioning and execution events (Phase 2.6)
from app.models.workflow_version_models import (
    ExecutionEvent,
    WorkflowVersion,
)

# Workspace activity log
from app.models.workspace_activity_log import WorkspaceActivityLog

# H4 Phase 4: Tenant models deleted — Workspace is now the canonical org model
# Workspace models (DB-backed)
# Workspace versioning (Phase 3.1)
from app.models.workspace_models import (
    Team,
    TeamMember,
    Workspace,
    WorkspaceInvitation,
    WorkspaceMember,
    WorkspaceVersion,
)
