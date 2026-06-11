# 05 — Knowledge, Events, Data, and AI Provider Layer

## 1. Knowledge Architecture

### Goals

Support:

- Autonomous agents.
- Long-lived memory.
- Workspace knowledge.
- Semantic search.
- Graph relationships.
- Episodic recall.
- Retrieval explainability.
- Memory retention and deletion.

### Memory Layers

```text
Working Memory
  ↓
Conversation Memory
  ↓
Semantic Memory
  ↓
Episodic Memory
  ↓
Graph Knowledge
  ↓
Organizational Memory
```

### Storage Choices

| Layer | Primary Store | Why |
|---|---|---|
| Semantic vectors | Qdrant | Current FlowManner already uses Qdrant and it fits vector search. |
| Graph relationships | Postgres first, optional graph DB later | Avoid premature graph infrastructure; Postgres adjacency tables are enough initially. |
| Episodic memory | Event log + run archive | Execution history is already event-sourced. |
| Working memory | Run checkpoint | Must be durable and resumable. |
| Retrieval cache | Redis | Fast repeated lookups and TTLs. |

### Retrieval Pipeline

```text
Query
  ↓
Normalize and classify intent
  ↓
Apply workspace/user permissions
  ↓
Hybrid retrieval:
  - keyword
  - vector
  - graph neighborhood
  - recency
  - authority
  ↓
Rerank
  ↓
Citation packaging
  ↓
Context builder
```

### Knowledge Events

Required events:

- `memory.document.ingested`
- `memory.document.deleted`
- `memory.vector.indexed`
- `memory.graph.updated`
- `memory.retrieval.requested`
- `memory.retrieval.returned`

### Knowledge Rules

1. Retrieval must be workspace-scoped.
2. Deletion must cascade to vectors and graph.
3. Memory writes should be event-driven.
4. Retrieval must expose provenance.
5. Embeddings must be versioned.
6. Sensitive data must not be indexed without policy.

## 2. Event Architecture

### Event Backbone

Use a layered event architecture. NATS JetStream is a future Phase 4 dependency; it is not part of the current Docker Compose topology.

```text
Postgres outbox
  → RabbitMQ for current Celery/task compatibility
  → NATS JetStream for domain events after Phase 4
  → Redpanda/Kafka later for high-volume audit and analytics
```

### Why This Combination

| Component | Role |
|---|---|
| Postgres outbox | Reliable transaction boundary. |
| RabbitMQ | Current Celery/task compatibility. |
| NATS JetStream | Future Phase 4 domain event backbone. |
| Redpanda/Kafka | Future high-volume immutable log for SaaS scale. |

### Event Categories

| Category | Purpose |
|---|---|
| Command | Request to do something. |
| DomainEvent | Business fact that happened. |
| IntegrationEvent | External system notification. |
| SystemEvent | Infrastructure/runtime fact. |
| AuditEvent | Immutable compliance record. |

### Event Schema Requirements

Every event should include:

- `event_id`
- `type`
- `version`
- `source`
- `subject`
- `tenant_id`
- `workspace_id`
- `correlation_id`
- `causation_id`
- `sequence`
- `occurred_at`
- `actor`
- `payload`
- `redaction_level`
- `schema_url`

### Replay and Auditability

Replay must be possible at three levels:

1. Run replay.
2. Agent replay.
3. Workspace audit replay.

Replay requires:

- Append-only event log.
- Stable event schema versions.
- Deterministic reducers where possible.
- Snapshots for long histories.
- Redaction-aware export.

## 3. Data Layer

### Recommended Stores

| Store | Use |
|---|---|
| Postgres | Transactional source of truth, event log, projections, graph relationships. |
| Redis | Cache, rate limits, sessions, ephemeral locks. |
| Qdrant | Semantic memory and vector search. |
| Object Storage | Artifacts, uploads, exports, replay bundles. |
| ClickHouse / Parquet / S3 | Analytics, usage, cost rollups. |
| OpenSearch | Optional full-text search later. |

### Data Ownership

| Data Type | Owner |
|---|---|
| User identity | User domain |
| Workspace membership | Workspace domain |
| Agent definitions | Agent domain |
| Workflow definitions | Workflow domain |
| Run/task state | Execution domain |
| Tool registry | Tool domain |
| Vector indexes | Knowledge domain |
| Billing meters | Billing domain |
| Telemetry | Observability domain |

### Migration Strategy

Recommended migration path:

1. Freeze current execution semantics.
2. Add canonical event schema.
3. Dual-write from legacy mission/graph/swarm paths into new run/event model.
4. Backfill existing runs into event-compatible form.
5. Feature-flag new Blueprint+Run paths.
6. Deprecate legacy write paths gradually.
7. Remove old paths only after verified usage is zero.

Do not do a big-bang rewrite.

## 4. AI Provider Layer

### Provider Abstraction

The provider layer must expose a stable internal interface:

```text
Provider Adapter
  → capabilities
  → chat/completion
  → streaming
  → tool calling
  → structured outputs
  → token accounting
  → cost accounting
  → retry behavior
```

### Required Providers

| Provider | Status |
|---|---|
| OpenAI | Required |
| Anthropic | Required |
| Gemini | Required |
| Ollama | Required |
| llama.cpp | Required |
| Future providers | Supported by adapter pattern |

### Provider Registry

Every provider/model should declare:

- Provider name.
- Model family.
- Context window.
- Tool calling support.
- Streaming support.
- Structured output support.
- Cost model.
- Latency profile.
- Region.
- Reliability tier.
- Safety constraints.
- Local/cloud flag.

### Routing Rules

Provider routing should consider:

- User preference.
- Workspace policy.
- Cost budget.
- Latency budget.
- Model capability.
- Provider health.
- Data residency.
- Local availability.
- Fallback policy.

### Provider Anti-Lock-In Rules

1. Never scatter provider SDKs through business logic.
2. Keep provider-specific types behind adapters.
3. Keep provider calls traceable.
4. Keep cost and token accounting provider-neutral.
5. Support OpenAI-compatible adapters for future vendors.
6. Make local inference first-class, not second-class.

## 5. Knowledge + Event + Data Integration

The target integration pattern:

```text
Execution event
  → event bus
  → knowledge indexer
  → vector/graph update
  → retrieval index
  → agent context
```

This means agents can learn from past executions without storing state in memory.

## 6. Design Principle

> Knowledge should be derived from events, not copied from process state.

That makes memory durable, replayable, and auditable.
