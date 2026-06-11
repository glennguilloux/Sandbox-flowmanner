# 04 — Execution Engine and Agent Runtime

## Part A — Durable Execution Engine

### Goal

Support:

- Millions of task executions.
- Distributed workers.
- Resumable execution.
- Retries.
- Checkpoints.
- Long-running workflows.
- Human-in-the-loop pauses.
- Cost and time budgets.
- Replayable audit trails.

### Core Concepts

| Concept | Meaning |
|---|---|
| Workflow Definition | Immutable or versioned description of what should happen. |
| Run | One execution of a workflow definition. |
| Task | Smallest schedulable unit of work inside a run. |
| Lease | Claim made by a worker to execute a task. |
| Checkpoint | Durable snapshot of progress, state, and references. |
| Event | Immutable record of what happened. |
| Projection | Read model derived from events for dashboards and APIs. |
| Budget | Cost, time, token, retry, and iteration limits. |
| Intervention | Human or system action that changes run progress. |

### Execution State Machine

```text
CREATED
  ↓
PLANNING
  ↓
SCHEDULED
  ↓
RUNNING
  ↓
COMPLETED
```

Intermediate states:

```text
WAITING_ON_HUMAN
WAITING_ON_TOOL
WAITING_ON_EXTERNAL_EVENT
RETRYING
PAUSED
CIRCUIT_BROKEN
FAILED
CANCELLED
```

### Worker Model

Workers are stateless and horizontally scalable.

Worker responsibilities:

1. Claim task leases.
2. Renew leases.
3. Execute one step.
4. Append event.
5. Save checkpoint.
6. Publish outbox events.
7. Heartbeat.
8. Recover from crash.

Worker constraints:

- No long-lived in-process run state.
- No assumptions about local filesystem persistence.
- No direct mutation of another domain's tables.
- No silent retries without event evidence.
- No uncapped loops.

### Lease Semantics

```text
task is available
  → worker claims lease
  → lease expires_at is set
  → worker heartbeats
  → worker completes task
  → event appended
  → lease released
```

If worker dies:

```text
lease expires
  → task becomes available again
  → another worker claims it
  → checkpoint prevents duplicate progress
```

### Checkpoint Strategy

Checkpoint every:

- N events, or
- N seconds for long-running tasks, or
- Before/after external side effects, or
- Before human approval pauses.

Checkpoint contents:

- Run ID.
- Task ID.
- State.
- Last event sequence.
- Tool call references.
- LLM call references.
- Artifact references.
- Retry count.
- Budget consumption.
- Worker identity.
- Idempotency key.

### Retry Strategy

Retry policy should be explicit:

```text
retryable error class
  → delay = base * 2^attempt + jitter
  → max attempts
  → max wall clock
  → max cost
  → circuit breaker
  → escalation
```

Use the current Nexus error taxonomy as a starting point:

- TIMEOUT
- VALIDATION
- RESOURCE
- LOGIC
- NETWORK
- PERMISSION
- NOT_FOUND
- RATE_LIMIT
- UNKNOWN

### Long-Running Workflows

Long-running workflows must be implemented with continuation, not process memory.

Examples:

- Wait for human approval.
- Wait for external webhook.
- Wait for scheduled time.
- Wait for a file.
- Wait for another run.
- Wait for a model to become available.

Implementation:

- Store wait reason in run state.
- Emit `run.waiting` event.
- Release worker lease.
- Resume when external event or timer arrives.

### Execution Engine Requirements

The engine must provide:

1. Idempotent task execution.
2. Exactly-once event append per logical step.
3. Lease-based worker coordination.
4. Crash recovery.
5. Replay from event log.
6. Budget enforcement.
7. Human intervention.
8. Cost attribution.
9. Structured failure classification.
10. Observability hooks.

### What to Keep from Current Substrate

Current FlowManner already has substrate concepts:

- Append-only event log.
- Replay engine.
- Mission/Blueprint/Run abstractions.
- Strategy-based execution.
- Cost attribution.
- HITL concepts.

The future engine should preserve these ideas and make them stricter.

## Part B — Agent Runtime

### Goal

Agents should be first-class runtime entities with:

- Lifecycle.
- Memory hierarchy.
- Context management.
- Tool execution.
- State management.
- Protocol compatibility.

### Agent Lifecycle

```text
DEFINED
  ↓
REGISTERED
  ↓
READY
  ↓
ASSIGNED
  ↓
EXECUTING
  ↓
WAITING
  ↓
COMPLETED
  ↓
ARCHIVED
```

Agent lifecycle events:

- `agent.definition.created`
- `agent.instance.assigned`
- `agent.execution.started`
- `agent.execution.paused`
- `agent.execution.completed`
- `agent.memory.updated`

### Memory Hierarchy

| Memory Level | Lifetime | Purpose | Storage |
|---|---|---|---|
| Working Memory | Run-local | Current context and scratch state | Run state/checkpoint |
| Conversation Memory | Thread/session | Chat continuity | Event log + message store |
| Semantic Memory | Workspace/user | Retrieval by meaning | Qdrant |
| Episodic Memory | Run history | What happened before | Event log + run archive |
| Procedural Memory | Agent capability | How to do things | Agent templates/tools |
| Organizational Memory | Workspace/company | Shared knowledge | Qdrant + graph + docs |
| Policy Memory | Tenant/workspace | Permissions and constraints | Workspace policy store |

### Context Management

The context builder should be explicit and budgeted.

Inputs:

- Run state.
- Workflow definition.
- Agent profile.
- User instructions.
- Retrieved memory.
- Tool results.
- Previous messages.
- Budget limits.
- Safety constraints.

Context builder rules:

1. Never exceed model context budget.
2. Prefer citations over raw context.
3. Redact secrets before provider calls.
4. Compress old context.
5. Keep provenance.
6. Include cost/token estimates.
7. Make retrieval explainable.

### Tool Execution

Tool execution must be capability-bounded.

Required checks:

- Agent has capability.
- Workspace allows tool.
- Tool input is valid.
- Budget allows call.
- Sandbox policy is satisfied.
- Idempotency key is present.
- Result is validated.

Tool execution flow:

```text
Agent requests tool
  ↓
Capability check
  ↓
Tool adapter
  ↓
Sandbox or external call
  ↓
Result validation
  ↓
Event append
  ↓
Agent receives structured result
```

### State Management

Agent state should not live in Python process memory.

State lives in:

- Run checkpoints.
- Event log.
- Memory stores.
- Tool result references.
- Workflow state.

The agent runtime should be actor-like, but the implementation can remain event-sourced.

### Future Protocol Compatibility

The runtime should support multiple protocol shapes:

- FlowManner native protocol.
- A2A-style agent-to-agent messaging.
- MCP-style tool/server discovery.
- OpenAI-compatible responses/tools.
- LangGraph-style state graphs.
- Custom enterprise protocol adapters.

The goal is not to lock into one protocol. The goal is to make FlowManner a protocol adapter and runtime host.

## Runtime Design Principle

> Agents should be durable, interruptible, auditable, and replaceable.

That means:

- No in-process-only state.
- No unbounded loops.
- No implicit authority.
- No unlogged tool calls.
- No hidden model calls.
- No non-replayable execution.
