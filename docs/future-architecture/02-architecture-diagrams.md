# 02 — Architecture Diagrams

## 1. Future-State Architecture Diagram

```text
                                      ┌───────────────────────────┐
                                      │        Clients            │
                                      │ Web / Mobile / SDK / CLI  │
                                      └─────────────┬─────────────┘
                                                    │
                         ┌──────────────────────────▼──────────────────────────┐
                         │              API Gateway / Edge Layer              │
                         │ Nginx, Traefik, Cloudflare, or enterprise ingress   │
                         └──────────────────────────┬──────────────────────────┘
                                                    │
                         ┌──────────────────────────▼──────────────────────────┐
                         │              FlowManner Control Plane               │
                         │ Modular monolith backend with bounded domains       │
                         │                                                     │
                         │ ┌─────────────┐ ┌──────────────┐ ┌───────────────┐  │
                         │ │ Auth/User   │ │ Workspace    │ │ Billing       │  │
                         │ │ Domain      │ │ Domain       │ │ Domain        │  │
                         │ └─────────────┘ └──────────────┘ └───────────────┘  │
                         │ ┌─────────────┐ ┌──────────────┐ ┌───────────────┐  │
                         │ │ Agent       │ │ Workflow     │ │ Tool          │  │
                         │ │ Runtime     │ │ Domain       │ │ Domain        │  │
                         │ └─────────────┘ └──────────────┘ └───────────────┘  │
                         │ ┌─────────────┐ ┌──────────────┐ ┌───────────────┐  │
                         │ │ Knowledge   │ │ Observability│ │ Provider      │  │
                         │ │ Domain      │ │ Domain       │ │ Layer         │  │
                         │ └─────────────┘ └──────────────┘ └───────────────┘  │
                         └──────────────────────────┬──────────────────────────┘
                                                    │
              ┌─────────────────────────────────────┼─────────────────────────────────────┐
              │                                     │                                     │
┌─────────────▼─────────────┐        ┌──────────────▼──────────────┐        ┌─────────────▼─────────────┐
│ Transactional Store       │        │ Event Backbone              │        │ Execution Plane           │
│ Postgres                  │        │ Outbox + NATS JetStream     │        │ Stateless workers         │
│ - domain tables           │        │ RabbitMQ compatibility      │        │ - lease tasks             │
│ - append-only events      │        │ Redpanda/Kafka later        │        │ - execute tools/LLMs      │
│ - projections             │        │                             │        │ - checkpoint progress     │
└───────────────────────────┘        └─────────────────────────────┘        └─────────────┬─────────────┘
              │                                     │                                     │
┌─────────────▼─────────────┐        ┌──────────────▼──────────────┐        ┌─────────────▼─────────────┐
│ Semantic Memory           │        │ Analytics Store             │        │ AI Provider Layer         │
│ Qdrant                    │        │ ClickHouse / Parquet / S3   │        │ OpenAI / Anthropic /      │
│ - workspace vectors       │        │ - usage                     │        │ Gemini / Ollama /         │
│ - semantic memory         │        │ - cost                      │        │ llama.cpp / future        │
│ - retrieval indexes       │        │ - audit rollups             │        │ providers                 │
└───────────────────────────┘        └─────────────────────────────┘        └───────────────────────────┘
              │
┌─────────────▼─────────────┐
│ Object Storage            │
│ S3-compatible             │
│ - artifacts               │
│ - exports                 │
│ - uploaded files          │
└───────────────────────────┘
```

## 2. Domain Map

```text
FlowManner Domains

User & Identity
  ├── users
  ├── sessions
  ├── API keys
  ├── OIDC
  └── permissions

Workspace & Tenancy
  ├── organizations
  ├── workspaces
  ├── teams
  ├── memberships
  ├── scopes
  └── workspace policies

Agent Domain
  ├── agent definitions
  ├── agent instances
  ├── capabilities
  ├── memory profiles
  ├── behavior rules
  └── agent lifecycle

Workflow Domain
  ├── blueprints
  ├── workflow versions
  ├── node templates
  ├── edge rules
  ├── human checkpoints
  └── workflow contracts

Execution Domain
  ├── runs
  ├── tasks
  ├── leases
  ├── retries
  ├── checkpoints
  ├── budgets
  └── failure recovery

Tool Domain
  ├── tool registry
  ├── tool adapters
  ├── capability tokens
  ├── sandbox execution
  └── tool result validation

Knowledge Domain
  ├── semantic memory
  ├── episodic memory
  ├── graph knowledge
  ├── retrieval indexes
  └── memory policies

Billing Domain
  ├── subscriptions
  ├── usage meters
  ├── invoices
  ├── quotas
  └── cost attribution

Observability Domain
  ├── traces
  ├── metrics
  ├── logs
  ├── audit events
  ├── replay
  └── alerts
```

## 3. Data Flow Diagram

```text
User submits a workflow or mission
  ↓
API Gateway
  ↓
Control Plane receives request
  ↓
Auth + Workspace + Scope validation
  ↓
Domain command handler
  ↓
Transactional write:
  - create run/task
  - append initial event
  - insert outbox record
  ↓
Event outbox publisher
  ↓
Event backbone:
  - NATS JetStream for domain events
  - RabbitMQ for task dispatch compatibility
  ↓
Execution workers claim leases
  ↓
Workers execute steps:
  - LLM calls
  - tool calls
  - human approvals
  - external integrations
  ↓
Workers append events:
  - task.started
  - tool.called
  - llm.completed
  - run.checkpointed
  - run.completed
  ↓
Read model projections update:
  - dashboard
  - cost
  - audit timeline
  - search
  ↓
Client receives real-time updates:
  - SSE
  - WebSocket
  - SDK stream
```

## 4. Event Flow Diagram

```text
Command
  ↓
Domain validation
  ↓
Append domain event
  ↓
Outbox transaction
  ↓
Publisher
  ↓
Event consumers
      ├── Execution worker
      ├── Knowledge indexer
      ├── Cost meter
      ├── Audit log
      ├── Notification fanout
      └── Observability sink
```

Event shape:

```json
{
  "event_id": "uuidv7",
  "type": "run.task.completed",
  "version": 1,
  "source": "flowmanner.execution",
  "subject": "run_01HX...",
  "tenant_id": "tenant_01HX...",
  "workspace_id": "workspace_01HX...",
  "correlation_id": "run_01HX...",
  "causation_id": "task_01HX...",
  "sequence": 123,
  "occurred_at": "2026-06-11T12:00:00Z",
  "actor": {
    "type": "agent",
    "id": "agent_01HX..."
  },
  "payload": {
    "status": "completed",
    "result_ref": "artifact://..."
  },
  "redaction_level": "workspace-safe"
}
```

## 5. Execution Flow Diagram

```text
Run is created
  ↓
Planner decomposes run into tasks
  ↓
Task scheduler creates leases
  ↓
Workers claim leases
  ↓
Worker starts task
  ↓
Task executes:
  ├── LLM step
  ├── tool step
  ├── human approval step
  └── external integration step
  ↓
Checkpoint saved
  ↓
Event emitted
  ↓
Next task scheduled or run completes
  ↓
Projections update
```

## 6. Why This Shape Wins

This architecture gives FlowManner:

- Operational simplicity for self-hosted users.
- Horizontal scale for SaaS.
- Replayability for debugging.
- Auditability for enterprise customers.
- Provider portability.
- Memory and agent extensibility.
- A path to edge execution and GPU clusters without rewriting the platform.
