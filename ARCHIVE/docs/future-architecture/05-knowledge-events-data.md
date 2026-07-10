# 05 - Knowledge, Events, Data, and AI Provider Layer

## 1. Knowledge Architecture

### Goals

Knowledge must support:

- Autonomous agents.
- Long-lived memory.
- Workspace-scoped recall.
- Semantic search.
- Graph relationships.
- Episodic recall from execution events.
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

### Memory Retention and Deletion

Memory retention and deletion must be explicit contracts, not side effects of vector storage.

Rules:

1. Every memory item records tenant, workspace, creator, source event, retention policy, and redaction level.
2. Workspace deletion cascades to vectors, graph edges, retrieval cache entries, and projection rows.
3. Document deletion emits `memory.document.deleted.v1` before downstream indexes remove data.
4. Retention expiry emits `memory.retention.expired.v1` before physical deletion.
5. Deletion must be idempotent and auditable.
6. Sensitive data must not be indexed without an explicit policy decision.

### Knowledge Events

Knowledge events are domain events emitted by the Knowledge domain or by consumers that derive knowledge from execution events.

Required events:

| Event | Meaning |
|---|---|
| `memory.document.ingested.v1` | A document or artifact became searchable for a workspace. |
| `memory.document.deleted.v1` | A document was logically deleted and downstream cleanup started. |
| `memory.vector.indexed.v1` | Vector indexing completed for a memory item. |
| `memory.graph.updated.v1` | Graph relationships changed. |
| `memory.retrieval.requested.v1` | Retrieval was requested with permissions and provenance requirements. |
| `memory.retrieval.returned.v1` | Retrieval returned citations with scores and redaction metadata. |
| `memory.retention.expired.v1` | Retention policy expired a memory item. |

### Knowledge Event Consumers

Knowledge event consumers must be replaceable and independently testable:

| Consumer | Input | Output |
|---|---|---|
| Vector indexer | `memory.document.ingested.v1` | `memory.vector.indexed.v1` |
| Graph projector | `memory.document.ingested.v1`, `memory.document.deleted.v1` | `memory.graph.updated.v1` |
| Retrieval cache invalidator | `memory.document.deleted.v1`, `memory.retention.expired.v1` | Cache invalidation or TTL refresh |
| Retention worker | retention policy table | `memory.retention.expired.v1` |
| Audit/export worker | all knowledge events | redaction-aware audit records |

## 2. Event Architecture

### Event Backbone

Use a layered event architecture. NATS JetStream is future Phase 4 only. It is not part of the current Docker Compose topology and cannot start before the event schema and Postgres outbox are stable.

Stop gates:

- No NATS before outbox/event-schema stability.
- No unsupported provider routing.
- No premature provider-specific claims.
- No provider-specific SDK calls in business logic.

```text
Domain transaction
  → Postgres outbox
  → RabbitMQ compatibility relay
  → Knowledge/event consumers
  → NATS JetStream after Phase 4, if approved
  → Redpanda/Kafka later for high-volume audit and analytics
```

### Postgres Outbox

The Postgres outbox is the reliability boundary between business transactions and message delivery.

Rules:

1. Append domain data and outbox rows in one Postgres transaction.
2. Publish only after the transaction commits.
3. Treat the outbox as the source for replay and retry.
4. Keep publisher retries idempotent by `event_id`.
5. Do not call external AI providers inside the database transaction.
6. Do not let RabbitMQ, Celery, NATS, or another transport mutate the outbox table directly.

Outbox row contract:

| Field | Meaning |
|---|---|
| `id` | Database primary key. |
| `event_id` | Canonical event identifier, unique across the system. |
| `event_type` | Event name with version suffix, for example `memory.document.ingested.v1`. |
| `schema_version` | Event schema version. |
| `source` | Emitting module or aggregate. |
| `subject` | Aggregate type and identifier. |
| `tenant_id` | Tenant scope. |
| `workspace_id` | Workspace scope when applicable. |
| `correlation_id` | Request or mission correlation. |
| `causation_id` | Event that caused this event. |
| `occurred_at` | Business time the event happened. |
| `payload` | JSON event body. |
| `redaction_level` | Export and routing sensitivity. |
| `created_at` | Database write time. |
| `published_at` | First successful publish time. |

### Event Schema v1

Event schema v1 is the minimum contract before any event backbone work.

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `event_id` | UUID | Yes | Unique event identifier. |
| `type` | string | Yes | Stable name with version suffix. |
| `version` | integer | Yes | Schema version, starting at `1`. |
| `source` | string | Yes | Emitting module or aggregate. |
| `subject` | string | Yes | Aggregate type and id. |
| `tenant_id` | UUID | Yes | Tenant boundary. |
| `workspace_id` | UUID | Conditional | Workspace boundary when the event is workspace-scoped. |
| `correlation_id` | UUID | Yes | Request, mission, or API correlation. |
| `causation_id` | UUID | Conditional | Event that caused this event. |
| `sequence` | integer | Yes | Per-subject append order. |
| `occurred_at` | timestamp | Yes | Business time. |
| `actor` | object | Yes | User, service, or system actor. |
| `payload` | object | Yes | Event-specific data. |
| `redaction_level` | enum | Yes | Controls retention, export, and provider routing. |
| `schema_url` | URI | Yes | Human-readable schema location. |

### Outbox Transaction Boundary

The outbox transaction boundary is the contract that keeps event emission reliable.

```text
BEGIN
  write domain row
  append outbox row with event_id, event_type, schema_version, payload, redaction_level
COMMIT
  publish outbox rows after commit
  mark published_at only after transport acknowledgement
```

TDD focus: tests must prove that a failed transaction emits no event, a committed transaction emits exactly one event, and a retry after partial publish does not duplicate work.

### RabbitMQ Compatibility

RabbitMQ compatibility keeps the current Celery/task execution model alive while the future event backbone matures.

Rules:

1. RabbitMQ remains a transport compatibility layer, not the canonical event store.
2. The Postgres outbox remains the durable source for retries and replay.
3. Celery tasks can consume outbox-backed messages without owning event schema rules.
4. Legacy task queues may coexist with new knowledge/event consumers.
5. Migration away from RabbitMQ requires consumer parity and replay tests.

### NATS JetStream as Future Phase 4 Only

NATS JetStream is a future Phase 4 domain-event backbone candidate. It is not current topology.

NATS may be considered only after:

- Event schema v1 is defined and tested.
- Postgres outbox transaction boundaries are proven.
- RabbitMQ compatibility consumers can be replayed.
- Knowledge event consumers are idempotent.
- provider routing research remains source-backed or explicitly unresolved.

### Event Categories

| Category | Purpose |
|---|---|
| Command | Request to do something. |
| DomainEvent | Business fact that happened. |
| IntegrationEvent | External system notification. |
| SystemEvent | Infrastructure or runtime fact. |
| AuditEvent | Immutable compliance record. |

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
- Idempotent knowledge event consumers.

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

The provider layer must expose a stable internal interface. Business logic depends on capabilities, not provider SDKs.

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
  → health checks
```

### Provider Adapter Interface

The provider adapter interface is the port that every local or cloud provider implements.

Contract:

| Operation | Purpose |
|---|---|
| `capabilities()` | Returns model family, context window, tool calling, streaming, structured outputs, and redaction constraints. |
| `complete()` | Runs a non-streaming completion. |
| `stream()` | Runs a streaming completion. |
| `call_tools()` | Executes provider-native tool calling when supported. |
| `structured_output()` | Produces schema-constrained output when supported. |
| `token_and_cost()` | Returns provider-neutral token and cost accounting. |
| `health()` | Reports local/cloud health, latency, error rate, and capability probes. |

Provider-specific SDK calls stay inside adapters. Mission, workflow, and knowledge code must not import provider SDKs directly.

### Provider Registry

The provider registry is a configuration and policy table, not a routing oracle.

Every provider/model entry should declare:

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
- Redaction constraints.
- Health check endpoint or probe.
- Fallback policy.
- BYOK or platform ownership.

Provider names are configuration examples only. The architecture does not claim that any specific provider currently satisfies a routing rule.

### Local/Cloud Routing Rules

Local/cloud routing rules must be policy-driven and testable.

Rules:

1. User preference and workspace policy are inputs, not hard-coded business logic.
2. Local inference is first-class when the model capability, health, and policy allow it.
3. Cloud fallback is allowed only when local inference is unavailable, policy permits external transfer, and redaction_level allows it.
4. Workspace policy wins over cost and latency.
5. Provider health checks gate routing decisions.
6. Fallback must preserve correlation, causation, idempotency, token accounting, and audit records.
7. provider routing research remains explicitly unresolved until source-backed research confirms provider capabilities, fallback semantics, and local/cloud policy behavior.

### Provider Health Checks and Fallback

Provider health checks must separate capability from availability.

Minimum checks:

- Local model liveness.
- Cloud API availability.
- Streaming availability.
- Tool calling availability.
- Structured output availability.
- Latency and error-rate budget.
- Token and cost accounting sanity.
- Circuit breaker state.
- Last successful health timestamp.

Local/cloud fallback is allowed only through the provider registry and adapter interface. Fallback must not bypass redaction, audit, token accounting, or correlation tracking.

### Provider Routing Research Status

provider routing research is explicitly unresolved until source-backed research confirms provider capabilities, fallback semantics, and local/cloud policy behavior. Until then, this pack may list routing factors but must not claim a solved provider-specific implementation.

This means:

- Do not document a final routing algorithm as implemented.
- Do not add live provider tests as proof of architecture.
- Do not add provider-specific SDK details to business logic.
- Do not treat provider-specific examples as canonical routing behavior.

### Provider Anti-Lock-In Rules

1. Never scatter provider SDKs through business logic.
2. Keep provider-specific types behind adapters.
3. Keep provider calls traceable.
4. Keep cost and token accounting provider-neutral.
5. Support OpenAI-compatible adapters for future vendors.
6. Make local inference first-class, not second-class.
7. Keep provider routing replaceable until research is source-backed.

## 5. Knowledge + Event + Data Integration

The target integration pattern:

```text
Execution event
  → Postgres outbox
  → event bus or compatibility relay
  → knowledge event consumer
  → vector/graph update
  → retrieval index
  → agent context
```

This means agents can learn from past executions without storing state in process memory.

Knowledge writes must be event-driven, idempotent, and replayable. Consumers must tolerate duplicate delivery and must use `event_id` as the idempotency key.

## 6. TDD Contract Checklist

Before implementation work starts in this area, add or update tests for these contracts:

- [ ] event schema v1 fields: every required field has type, required status, and meaning.
- [ ] outbox transaction boundary: failed transactions emit no event, committed transactions emit one event, and retry after partial publish does not duplicate work.
- [ ] provider adapter interface: all provider calls go through the adapter port, and provider SDK imports stay out of business logic.
- [ ] provider health checks: health state gates routing and records latency, error rate, capability support, and last success time.
- [ ] local/cloud fallback: fallback respects workspace policy, redaction_level, health checks, correlation, causation, token accounting, and audit records.
- [ ] knowledge event consumers: vector, graph, cache, retention, and audit consumers are idempotent and replayable.

## 7. Design Principle

> Knowledge should be derived from events, not copied from process state.

That makes memory durable, replayable, and auditable.
