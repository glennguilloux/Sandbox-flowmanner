# Flowmanner — Canonical Knowledge Representation

*Synthesized from 38 model files, 67+ route modules, 85+ frontend pages, dual-machine infrastructure, and architectural documentation. Extracted June 1, 2026.*

---

## 1. CORE CONCEPTS

### The Fundamental Idea
Flowmanner is a **multi-agent AI workflow automation platform** that lets users define, orchestrate, and execute complex tasks using AI agents — operating individually, in teams, or as coordinated swarms. The system combines a visual flow builder with LLM-powered execution, real-time chat, persistent memory, and a marketplace for sharing agent templates and tools.

### The Five Pillars

| Pillar | Description |
|--------|-------------|
| **Missions** | The unit of work — a goal decomposed into tasks, executed by agents |
| **Agents** | AI entities with personalities, tools, and capabilities that execute tasks |
| **Chat** | The primary human interface — a real-time, streaming LLM chat with branching |
| **Graphs / Flows** | Visual workflow definitions (nodes + edges) that agents execute |
| **Marketplace** | A sharing economy for agents, tools, templates, and integrations |

### Secondary Concepts

| Concept | Description |
|---------|-------------|
| **Swarms** | Multiple agents collaborating on a task with consensus strategies (parallel, sequential, debate) |
| **Orchestration** | Teams of agents with defined strategies, roles, and task routing |
| **Workspaces / Tenants** | Multi-user organizational structures with role-based access |
| **Memory** | Persistent knowledge extracted from sessions and missions, stored with embeddings |
| **RAG** | Document ingestion to chunking to vector embedding to retrieval |
| **BYOK** | Users supply their own LLM API keys (OpenAI, Anthropic, OpenRouter) |
| **Delegations** | Temporary role transfer between users within tenants |
| **Reliability** | Chaos-tested resilience — circuit breakers, fault isolation for LLM calls |
| **Learning** | Adaptation rules and feedback loops that improve agent behavior over time |
| **Tools** | Unified tool system: browser, terminal, topology, custom tools, tool chains |
| **Triggers** | Cron schedules and inbound webhooks that auto-launch missions |
| **Webhooks** | Outbound HTTP callbacks for mission lifecycle events |
| **Evaluations** | Golden datasets and test cases for benchmarking agent/LLM quality |
| **Roadmap** | Public feature voting with items, votes, and comments |
| **Partners** | Revenue-sharing organizations with Stripe integration |
| **Analytics** | Usage tracking, cost monitoring, performance metrics across all layers |

---

## 2. DIMENSIONS

### Organization Dimensions
```
User Identity
├── Role: free | pro | enterprise | admin
├── Tenant: Tenant organization (multi-tenant SaaS)
│   ├── Role: owner | admin | member
│   ├── Permissions: create_missions | manage_members | view_billing
│   └── Subscription Tier: Free | Pro | Enterprise
├── Workspace: Collaborative space
│   ├── Role: owner | admin | member
│   ├── Teams: Sub-groups within workspace
│   └── Plan: free | pro | enterprise
└── Partner: Revenue-sharing org affiliation
```

### Execution Dimensions
```
Execution Model
├── Solo: Single agent executing a mission
├── Sequential: Agents execute in ordered pipeline
├── Parallel: Multiple agents execute simultaneously
├── Debate: Agents reach consensus through rounds
├── Swarm: Dynamic multi-agent with consensus_strategy
│   ├── Consensus strategies: majority | unanimous | weighted
│   └── Pipeline phases: tracked with analytics
└── Orchestration: Team-based with formal role assignments
```

### Mission Lifecycle
```
Mission Status: pending to in_progress to completed | failed | cancelled
Task Status:    pending to assigned to in_progress to completed | failed | skipped
Task Dependencies: task can block on other tasks (DAG structure)
Retry: configurable max_retries + retry_count + next_retry_at
```

### Chat Dimensions
```
Chat Structure
├── ChatFolder: Organizational grouping of threads
├── ChatThread: Conversation container
│   ├── messages: ordered list of ChatMessage
│   ├── files: attached ChatFile objects
│   ├── branches: ChatBranch (fork conversations at any message)
│   ├── shared_links: SharedLink (token-based sharing)
│   └── ChatTemplate: Reusable system prompts + model configs
└── Message roles: user | assistant | system | tool
```

### Agent Classifications
```
Agent Types
├── domain: Domain-specific specialist agent
├── custom: User-created agent
├── marketplace: Published agent listing
└── swarm_agent: Agent instance within a swarm

Agent Dimensions
├── Division: Broad category (e.g., coding, writing, data)
├── Capabilities: What the agent can do (JSON)
├── Specializations: Specific skills (JSON)
├── Personality: System prompt + model preference
├── Tools: Discovered/registered tools
└── Status: active | inactive | busy | error
```

---

## 3. ENTITIES (49 models mapped)

**Users & Identity:** User, UserAPIKey, UserSettings, UserSubscription
**Agents:** Agent, AgentTemplate, AgentRegistration, AgentCapability, AgentProtocol
**Missions:** Mission, MissionTask, MissionLog, MissionImprovement, MissionTrigger, TriggerLog
**Chat:** ChatFolder, ChatThread, ChatMessage, ChatFile, ChatBranch, ChatTemplate, SharedLink
**Swarm:** SwarmProfile, SwarmAgent, SwarmTask, SwarmConsensusRound, SwarmPipeline
**Graphs/Flows:** Flow, WorkflowRun, GraphWorkflow, GraphExecution, GraphState
**Memory/Learning:** Memory, MemorySession, AdaptationRuleDB, LearningFeedbackDB
**Tools:** ToolChain, ToolChainExecution, CustomTool, ToolPermission, ToolAnalytics
**Organization:** Workspace, WorkspaceMember, Team, TeamMember, WorkspaceInvitation, WorkspaceMessage, Tenant, TenantMember, TenantInvitation
**Marketplace:** MarketplaceListing, MarketplaceCategory, MarketplaceReview, UserInstallation, AgentReview
**Infrastructure:** WebhookEndpoint, WebhookLog, IntegrationConnection, FeatureFlag, UsageRecord, Notification, NotificationSettings, PushSubscription
**Eval/Quality:** GoldenDataset, GoldenTestCase, EvalRun
**Feedback/Roadmap:** FeedbackReport, FeedbackPattern, RoadmapItem, RoadmapVote, RoadmapComment
**Business:** Partner, PartnerRevenue, SubscriptionTier
**Other:** UserFile, LogEntry, ComposedCapabilityModel

---

## 4. RELATIONSHIPS

### Ownership Hierarchy
```
Tenant ←── User ──→ Workspace
  │                  ├── Teams → TeamMembers
  │                  ├── WorkspaceMembers
  │                  └── WorkspaceInvitations
  │
  ├── Missions → MissionTasks → MissionLogs
  │
  ├── ChatFolders → ChatThreads
  │     ├── ChatMessages
  │     ├── ChatFiles
  │     ├── ChatBranches
  │     └── SharedLinks
  │
  ├── Agents (custom)
  ├── AgentTemplates
  ├── Flows → WorkflowRuns
  ├── GraphWorkflows → GraphExecutions → GraphStates
  ├── ToolChains
  ├── CustomTools
  ├── WebhookEndpoints → WebhookLogs
  ├── MemorySessions → Memories
  ├── Subscriptions
  ├── UserAPIKeys (BYOK)
  ├── Notifications
  └── UserFiles

Mission → MissionTrigger → TriggerLog
Partner → PartnerRevenues (by mission)
```

### Cross-Cutting
```
SwarmProfile → SwarmAgents → SwarmTasks → SwarmConsensusRounds
SwarmPipeline → SwarmProfile (via swarm_id)
AgentTemplate → SwarmAgent (via agent_template_id)
Mission → Agent (via assigned_agent_id)
MissionTask → MissionTask (parent_task_id, DAG)
Mission → Mission (parent_mission_id, hierarchical)
ChatMessage → ChatBranch (parent_message_id, fork)
ChatThread → SharedLink (thread_id)
```

---

## 5. KNOWLEDGE FLOWS

### Primary Flow:
```
User types in Chat → LLM processes → Tool calls invoked
                                → Mission created
                                → Mission decomposed into tasks
                                → Tasks assigned to agents (solo/swarm/team)
                                → Agents execute (browser, terminal, tools)
                                → Results, logs, costs tracked
                                → Memory extracted from outcomes
                                → Learning feedback applied
```

### Event-Driven:
```
Cron Trigger fires → MissionTrigger evaluated → Mission launched
Webhook received → WebhookEndpoint matched → Handler invoked → Mission launched
```

### Infrastructure:
```
Client ↔ WebSocket (/ws) ↔ Backend ↔ PostgreSQL/Redis/Qdrant
VPS (Nginx :443) → WireGuard → Homelab (FastAPI :8000)
```

---

## 6. DESIGN PRINCIPLES

**Explicit:**
1. Self-service agents — users create and configure their own AI agents
2. Multi-agent by default — solo, team, swarm execution models
3. BYOK — user-supplied LLM API keys, no vendor lock-in
4. Observable execution — logs, cost tracking, token counting, Jaeger traces
5. Persistent learning — feedback feeds back into adaptation rules
6. Marketplace economy — agents, tools, templates shared and monetized
7. Chaos-tested reliability — circuit breakers, fault isolation
8. Dual-machine separation — VPS (frontend) + homelab (backend) via WireGuard

**Implicit:**
1. Build dont buy — local llama.cpp inference
2. No volume mounts on backend — code baked into Docker images
3. Incremental complexity — Free tier to Pro to Enterprise
4. Chat as universal interface — everything flows through chat
5. Extractable knowledge — Memories + RAG ensure system gets smarter

---

## 7. REPEATED TERMINOLOGY

| Term | Meaning |
|------|---------|
| Mission | A goal decomposed into tasks, executed by agents |
| Agent | AI entity with personality, tools, and capabilities |
| Swarm | Multiple agents collaborating with consensus |
| Orchestration | Team-based agent coordination |
| Graph / Flow | Visual node-edge workflow definition |
| Chat | Real-time streaming LLM conversation (primary UI) |
| Branch | Fork a conversation at any message point |
| Canvas | Visual workspace for artifacts and code |
| Artifact | Generated content displayed in chat |
| Tool | Executable capability (browser, terminal, custom API) |
| ToolChain | Sequence of tools chained together |
| RAG | Document ingestion to embedding to retrieval |
| Memory | Persistent knowledge extracted from sessions |
| BYOK | User-provided LLM API keys |
| Workspace | Multi-user collaborative space |
| Tenant | Multi-tenant organization |
| Template | Reusable blueprint (agent, mission, chat) |
| Integration | Third-party connection (Slack, GitHub, OAuth) |
| Trigger | Event that auto-launches a mission (cron, webhook) |
| Webhook | Inbound HTTP endpoint for external events |
| Delegation | Temporary role transfer between users |
| Evaluation | Quality benchmarking against golden datasets |
| Learning | Self-improvement via feedback and adaptation |
| Reliability | Chaos-tested resilience and circuit breakers |
| Topology | Visual layout of workflows and agents |
| Nexus | SwarmPipeline extension for specialized configs |
| SSE | Server-Sent Events for streaming chat |
| CodeSandbox | Isolated code execution (Python, JS, TS) |

---

## 8. OPEN QUESTIONS

1. Flow vs Graph — two models with overlapping concerns, converging or competing?
2. Agent pluralism — four different agent representations, canonical lifecycle?
3. Workspace vs Tenant — legacy or complementary org models?
4. Nexus — referenced but undefined, what is it?
5. Phase 4 — what were Phases 1-3?
6. GraphQL v2 — conditional Strawberry router, future API direction?
7. API versioning — v1, v2, v3, what differentiates them?

---

## 9. EVOLUTION

- Phase 1: Core chat infrastructure
- Phase 4: Sharing, export, user files, integrations, feature flags
- V1 to V2: GraphQL alongside REST
- V2 to V3: Auth v3 models (NextAuth migration?)
- In-memory to DB: Notifications, push subscriptions to persistent storage
- Agent evolution: Agent to AgentRegistration to Capabilities to Protocol
- Swarm evolution: Swarm to SwarmPipeline (with analytics)
- Mission expansion: Mission to Task to Log to Improvement to Trigger
- Memory/knowledge: Memory + MemorySession for persistent knowledge

---

## 10. HIDDEN ASSUMPTIONS

1. Homelab is always available — single point of failure for backend
2. Users understand agent configuration — technical audience assumed
3. Chat is the primary interface — everything centers on chat
4. LLM costs tracked but not capped — no hard spending limits
5. Docker rebuild is acceptable — ~2 min per backend change
6. Codebases are separate but coupled — no shared git repo
7. NextAuth + Zustand dual auth — both must agree
8. Marketplace implies community — active user ecosystem assumed
9. Platform extensibility by design — BYOK, custom tools, webhooks, plugins
