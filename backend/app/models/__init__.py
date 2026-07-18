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
from app.models.analytics import AnalyticsEvent
from app.models.auth_models import (
    CustomRole,
    OIDCProvider,
    RoleDelegation,
    RolePermission,
    UserCustomRole,
    UserOIDCAccount,
    UserTenant,
)
from app.models.auth_v3_models import (
    ApiKey,
    AuthSession,
    AuthWebhookSubscription,
    OIDCProviderConfig,
)

# Binding models (Phase 2.3)
from app.models.binding_models import (
    AgentCapabilityBinding,
    AgentToolBinding,
    CapabilityDependency,
)

# Blog + case-study models (T1 — DB-backed blog)
from app.models.blog_models import BlogPost, BlogTag

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
from app.models.contact import ContactSubmission

# Cost category enum + event DTO (Q1-B Chunk 4)
from app.models.cost_event import CostCategory, CostEvent

# Critique model (D30-60, T24 — Critic Agent + Memory Correction UX)
from app.models.critique_models import ALL_CRITIC_KINDS, Critique

# Evaluation models
from app.models.evaluation_models import (
    EvalRun,
    GoldenDataset,
    GoldenTestCase,
)
from app.models.feedback_models import FeedbackPattern, FeedbackReport

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
    IntegrationHealthRecord,
    IntegrationIncident,
    IntegrationUsageLog,
    UserOAuthApp,
    UserOAuthConnection,
)

# Knowledge graph models (Phase 5 improvement foundation)
from app.models.knowledge_graph_models import KnowledgeEdge, KnowledgeNode
from app.models.learning_models import AdaptationRuleDB, LearningFeedbackDB

# Legacy tables with production data (schema reconciliation)
from app.models.legacy_models import AuditLog

# LLM call record model (H1.3 observability)
from app.models.llm_call_record import LLMCallRecord

# Marketplace transaction lifecycle + internal wallet (MARKETPLACE-2)
from app.models.marketplace_txn_models import (
    MarketplaceTransactionModel,
    MarketplaceWalletModel,
    TransactionStatus,
)

# Materialization state model (Phase 1.1e)
from app.models.materialization_models import MaterializationState

# Memory correction events (D30-60, T29 — privacy audit trail)
from app.models.memory_correction_models import (
    ALL_ACTORS,
    ALL_EVENT_TYPES,
    MemoryCorrectionEvent,
)

# Memory digest deliveries (D30-60, T31 — daily digest)
from app.models.memory_digest_models import (
    ALL_DELIVERY_CHANNELS,
    ALL_DELIVERY_STATUSES,
    MemoryDigestDelivery,
)

# Memory extraction pauses (D30-60, T30 — pause toggle)
from app.models.memory_extraction_pause_models import MemoryExtractionPause

# Memory models (canonical + legacy)
from app.models.memory_models import MemoryEntry, PendingWrite

# Mission versioning (Phase 3.1 — already existed, now normalized)
from app.models.mission_advanced_models import MissionPlanCandidate, MissionVersion

# Changelog model (re-register — was orphaned, never imported)
from app.models.changelog_models import ChangelogEntry

# External event model (re-register — was orphaned, never imported)
from app.models.external_event_model import ExternalEvent

# Memory action event model (re-register — was orphaned, never imported)
from app.models.memory_action_models import MemoryActionEvent

# Prompt version model (re-register — was orphaned, never imported)
from app.models.prompt_version_models import PromptVersion

# Scaffold models (re-register — were orphaned, never imported)
from app.models.scaffold_models import ScaffoldProposal, ScaffoldVersion

# Mission models
from app.models.mission_models import (
    Mission,
    MissionExecutionOutbox,
    MissionImprovement,
    MissionLog,
    MissionTask,
)

# Mission Programs (T1)
from app.models.mission_program_models import (
    MissionProgram,
    ProgramRun,
    ProgramRunStatus,
    ProgramStatus,
)
from app.models.models import (
    AgentReview,
    ComposedCapabilityModel,
    LogEntry,
    MarketplaceCategoryModel,
    MarketplaceListingModel,
    MarketplaceReviewModel,
    UserInstallationModel,
)
from app.models.notification_models import Notification, NotificationSettings, PushSubscription

# Partner models (depend on User)
from app.models.partner_revenue_models import (
    Partner,
    PartnerRevenue,
)

# Personal memory claims (D0-30, T18)
from app.models.personal_memory_models import PersonalMemoryClaim
from app.models.phase4_models import FeatureFlag, IntegrationConnection, UsageRecord, UserFile, UserSettings

# Playground sandbox models (Phase 4)
from app.models.playground_models import PlaygroundSandbox

# Plugin models (Phase 9.1)
from app.models.plugin_models import InstalledPlugin
from app.models.roadmap_models import RoadmapComment, RoadmapItem, RoadmapVote

# Sandbox models (sandboxd integration)
from app.models.sandbox_models import MissionSandbox

# Q3 — dedicated skills table (C3 correction: NOT MemoryEntry KV)
from app.models.skill_models import ALL_SKILL_PROVENANCE, ALL_SKILL_TRUST_TIERS, Skill

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
from app.models.tool_models import CustomTool, ToolAnalytics, ToolChain, ToolChainExecution, ToolPermission

# Topology models (Phase 1.1f)
from app.models.topology_models import (
    TopologyEdge,
    TopologyNode,
    TopologySnapshot,
)
from app.models.trigger_models import MissionTrigger, TriggerLog
from app.models.user import User
from app.models.webhook_models import WebhookEndpoint, WebhookLog

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
    WorkspaceToolAllowlist,
    WorkspaceVersion,
)

# RefreshToken model lives in auth_service; import here to register with Base.metadata
from app.services.auth_service import RefreshToken
