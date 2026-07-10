# 04 - Execution Engine and Agent Runtime

## Part A - Durable Execution Engine

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
- Crash recovery without process memory.

### Core Concepts

| Concept | Meaning |
|---|---|
| Workflow Definition | Immutable or versioned description of what should happen. |
| Run | One execution of a workflow definition. |
| Task | Smallest schedulable unit of work inside a run. |
| Lease | Exclusive worker claim with an expiry time and generation. |
| Checkpoint | Durable snapshot of progress, state, and references. |
| Event | Immutable record of what happened. |
| Projection | Read model derived from events for dashboards and APIs. |
| Budget | Cost, time, token, retry, and iteration limits. |
| Intervention | Human or system action that changes run progress. |
| Idempotency Key | Stable key that deduplicates commands and external side effects. |
| Replay Reducer | Deterministic function that rebuilds state from events. |

### Durable Execution State Machine

```text
CREATED
  ↓
PLANNING
  ↓
SCHEDULED
  ↓
CLAIMED
  ↓
RUNNING
  ↓
COMPLETED
```

Intermediate and recovery states:

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

State machine rules:

1. Only Execution mutates run/task state.
2. Every transition is backed by a command, an event, and a checkpoint update.
3. A task can run only while a worker owns a valid lease.
4. `WAITING_ON_HUMAN`, `WAITING_ON_TOOL`, `WAITING_ON_EXTERNAL_EVENT`, and `PAUSED` release the worker lease.
5. Completion appends a terminal event before the lease is released.
6. Cancellation is explicit and idempotent.
7. Retries are scheduled only within budget and failure-policy limits.
8. Replay can rebuild state without calling tools or providers unless explicitly marked as a dry run.

### Worker Model

Workers are stateless and horizontally scalable.

Worker responsibilities:

1. Claim task leases.
2. Renew leases before expiry.
3. Execute one step.
4. Append event.
5. Save checkpoint.
6. Publish outbox events.
7. Heartbeat with lease and sequence metadata.
8. Release leases on normal completion or pause.
9. Stop work immediately when a lease is lost.
10. Recover from crash by loading the last durable checkpoint.

Worker constraints:

- No long-lived in-process run state.
- No assumptions about local filesystem persistence.
- No direct mutation of another domain's tables.
- No silent retries without event evidence.
- No uncapped loops.
- No completion without checkpoint.
- No external side-effect acknowledgement before durable event and checkpoint evidence.

### Lease Semantics

```text
task is available
  → worker claims lease
  → lease expires_at is set
  → lease_generation is recorded
  → worker heartbeats
  → worker completes task
  → event appended
  → checkpoint saved
  → lease released
```

Lease rules:

1. A lease is exclusive while valid.
2. A worker must renew before `expires_at`.
3. Heartbeats must include `worker_id`, `lease_id`, `lease_generation`, `last_event_sequence`, and `checkpoint_sequence`.
4. A worker that loses its lease must stop processing and must not append more events for that task.
5. A stale lease must be reclaimed by an idempotent reclaimer, not by ad hoc worker gossip.
6. Reclaim must write a recovery event and advance `lease_generation` before another worker can claim the task.

If a worker dies:

```text
lease expires
  → stale-lease reclaim writes recovery evidence
  → task becomes available again
  → another worker claims it
  → last checkpoint determines resume point
  → idempotency key prevents duplicate logical progress
```

### Stale-Lease Reclaim and Crash Recovery

Stale-lease reclaim handles workers that die, pause forever, or lose network connectivity.

Reclaim contract:

1. Find leases where `expires_at` passed and heartbeat is stale.
2. Confirm no terminal event or newer checkpoint exists.
3. Write a recovery event such as `task.lease.lost` or `task.reclaimed`.
4. Clear the old lease and increment `lease_generation`.
5. Move the task back to `SCHEDULED` or `RETRYING`.
6. Make the task visible to another worker.

Crash-before-checkpoint behavior is explicit:

- If the worker crashes before checkpointing a step, that step is not complete.
- The reclaimer returns the task to the queue after lease expiry.
- The next worker resumes from the last durable checkpoint.
- The worker must replay the event log from that checkpoint and reissue only safe work.
- If an external side effect may have happened without a checkpoint, the idempotency key must deduplicate it.
- If the downstream tool or provider cannot deduplicate safely, the task moves to `FAILED` or `REQUIRES_REVIEW` with a `CRASH_BEFORE_CHECKPOINT_UNSAFE_RETRY` reason.

### Checkpoint Strategy

Checkpoint every:

- N events.
- N seconds for long-running tasks.
- Before requesting an external side effect.
- After recording an external side-effect result.
- Before human approval pauses.
- After budget or permission decisions.
- Before releasing a lease.

Checkpoint contents:

- Run ID.
- Task ID.
- Workflow version.
- State.
- Last event sequence.
- Lease ID and lease generation.
- Tool call references.
- LLM call references.
- Artifact references.
- Retry count.
- Budget consumption.
- Worker identity.
- Idempotency key.
- Checkpoint generation.

Checkpoint rules:

1. Checkpoints are durable, not process-local.
2. Event append and checkpoint write must use the same logical transaction when possible.
3. Checkpoint generation prevents stale workers from overwriting newer state.
4. The last checkpoint is the resume boundary.
5. Checkpoint recovery must be tested separately from normal retry paths.

### Retry Strategy and Failure Taxonomy

Retry policy must be explicit:

```text
retryable error class
  → delay = base * 2^attempt + jitter
  → max attempts
  → max wall clock
  → max cost
  → circuit breaker
  → escalation
```

Failure classes:

| Class | Retryable | Event | Required action |
|---|---:|---|---|
| TRANSIENT_PROVIDER | Yes | `task.retry.scheduled` | Backoff, preserve idempotency key, keep budget. |
| RATE_LIMIT | Yes | `task.retry.scheduled` | Backoff, respect provider and workspace limits. |
| NETWORK | Yes | `task.retry.scheduled` | Retry only if the logical step can be deduplicated. |
| TIMEOUT | Yes, with limits | `task.retry.scheduled` | Treat as unknown until tool/provider result is reconciled. |
| VALIDATION | No | `task.failed` | Reject input and require caller fix. |
| LOGIC | No | `task.failed` | Fix workflow or agent logic. |
| PERMISSION | No | `task.failed` | Deny and audit. |
| NOT_FOUND | No | `task.failed` | Stop because required resource is missing. |
| RESOURCE | Maybe | `task.retry.scheduled` or `task.failed` | Retry only if capacity can return within budget. |
| BUDGET_EXHAUSTED | No | `task.failed` | Stop and report remaining budget. |
| STALE_LEASE | No for old worker, yes for task | `task.lease.lost` | Old worker stops; task is reclaimed and rescheduled. |
| CRASH_BEFORE_CHECKPOINT_UNSAFE_RETRY | No automatic retry | `task.requires_review` | Require reconciliation or operator decision. |
| UNKNOWN | Maybe | `task.retry.scheduled` or `task.requires_review` | Escalate after retry limit or unsafe side-effect risk. |

### Human-in-the-Loop Pause and Resume

HITL pauses must not depend on a live process.

Pause flow:

1. Agent or workflow reaches a human gate.
2. Execution emits `run.waiting.human_required` or `agent.execution.paused`.
3. Checkpoint stores wait reason, allowed outcomes, owner scope, deadline, and resume token.
4. Worker releases the lease.
5. Task is not eligible for worker reclaim while the human gate is open.

Resume flow:

1. Human submits an approved outcome through an idempotent command.
2. Execution validates approver scope and deadline.
3. Execution emits `run.waiting.resolved` or `agent.execution.resumed`.
4. Task returns to `SCHEDULED`.
5. A worker claims a new lease and resumes from the checkpoint.

Timeout behavior:

- Emit `run.waiting.timed_out`.
- Move the run or task to `FAILED` or `CANCELLED` according to workflow policy.
- Keep the audit trail and checkpoint for replay.

### Idempotency Keys

Idempotency keys protect commands, task execution, tool calls, model calls, and human interventions.

Key rules:

1. A key is stable for the same logical operation across retries.
2. A new logical operation gets a new key.
3. The key is stored in the checkpoint and in idempotency records.
4. Duplicate commands return the original result reference instead of running again.
5. Tool and provider adapters receive the key when the downstream system supports deduplication.
6. If downstream deduplication is unavailable, the runtime must treat timeout or crash as unknown and reconcile before retrying.
7. HITL resume commands must include a resume idempotency key.

### Replay

Replay rebuilds run, task, agent, tool, budget, and cost state from the event log.

Replay rules:

1. Replay uses the same reducer for the same event sequence.
2. Replay does not call external tools or providers by default.
3. Dry-run replay can call providers only when explicitly enabled and budgeted.
4. Snapshots are accelerators, not sources of truth.
5. Redaction-aware replay exports must preserve audit value without exposing secrets.
6. Replay determinism tests compare rebuilt state against expected state for the same event sequence.

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
- Resume when external event, timer, or human decision arrives.

### Execution Engine Requirements

The engine must provide:

1. Idempotent task execution.
2. Exactly-once event append per logical step.
3. Lease-based worker coordination.
4. Stale-lease reclaim.
5. Crash recovery.
6. Replay from event log.
7. Budget enforcement.
8. Human intervention.
9. Cost attribution.
10. Structured failure classification.
11. Observability hooks.
12. Operator review for unsafe retry cases.

### What to Keep from Current Substrate

Current FlowManner already has substrate concepts:

- Append-only event log.
- Replay engine.
- Mission/Blueprint/Run abstractions.
- Strategy-based execution.
- Cost attribution.
- HITL concepts.

The future engine should preserve these ideas and make them stricter.

Existing substrate and chaos test references:

- `backend/tests/test_substrate_event_log.py` covers append-only event log behavior, latest sequence lookup, event retrieval, safety limits, and singleton behavior.
- `backend/tests/test_substrate_replay.py` covers state rebuild, rebuild-at-sequence, determinism verification, checkpoint sequence lookup, and replay engine singleton behavior.
- `backend/tests/chaos/test_kill_worker_mid_mission.py` covers mid-mission worker kill and resume-after-crash scenarios.
- `backend/tests/chaos/test_kill_worker_mid_mission_process.py` covers process-level mid-mission kill and true SIGKILL recovery scenarios.

### TDD Contract Checklist

Before implementation work starts in the execution plane, add or update tests for these contracts:

- [ ] Worker crash before checkpoint: crash or kill the worker after a side-effect request but before checkpoint; reclaim the expired lease; resume from the last checkpoint; reject unsafe duplicate retry when deduplication is unavailable.
- [ ] Lease expiry and stale-lease reclaim: expire a lease, run the reclaimer, advance `lease_generation`, reject the old worker append, and let a new worker claim the task.
- [ ] Idempotent task execution: send the same command, retry, HITL resume, tool call, and provider call with the same idempotency key; assert one logical result and one terminal event.
- [ ] Replay determinism: replay the same event sequence twice and assert identical run state, task state, agent state, cost attribution, and checkpoint sequence.
- [ ] HITL pause/resume: pause on a human gate, release the lease, submit duplicate resume commands, expire the approval deadline, and assert legal state transitions.
- [ ] Crash recovery: kill a worker process mid-mission and verify that the next worker resumes from durable state without process-local assumptions.
- [ ] Failure taxonomy: classify each failure class above and assert the correct retry, escalation, or review path.
- [ ] Substrate compatibility: keep the substrate event log and replay tests listed above in the execution-plane gate.

## Part B - Agent Runtime

### Goal

Agents should be first-class runtime entities with:

- Lifecycle.
- Memory hierarchy.
- Context management.
- Tool execution.
- State management.
- Protocol compatibility.
- Durable pause and resume.

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
PAUSED
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
- `agent.execution.resumed`
- `agent.execution.completed`
- `agent.execution.failed`
- `agent.memory.updated`

Agent lifecycle rules:

1. Lifecycle state is durable and event-derived.
2. Agents cannot assume permissions beyond assigned capabilities and memory profiles.
3. Execution may pause or resume an agent only through Execution commands.
4. Agent memory updates are events, not process mutations.
5. Archived agents retain enough metadata for audit and replay.

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

The context builder should be explicit, budgeted, and durable.

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
- Workspace policy.
- Model capability metadata.

Context builder rules:

1. Use durable stores only, never process-local memory.
2. Never exceed model context budget.
3. Estimate tokens and cost before provider calls.
4. Prefer citations over raw context.
5. Keep provenance for every included item.
6. Redact secrets before provider calls.
7. Compress old context with a stored summary reference.
8. Make retrieval explainable.
9. Preserve deterministic ordering where replay depends on it.
10. Stop or pause when budget cannot fit required context.

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
- Event append succeeds before the agent receives the result.
- Tool result contains no raw secrets or direct table mutation capability.

Tool execution flow:

```text
Agent requests tool
  ↓
Capability check
  ↓
Workspace policy check
  ↓
Input validation
  ↓
Budget check
  ↓
Sandbox or external call
  ↓
Result validation
  ↓
Event append
  ↓
Checkpoint
  ↓
Agent receives structured result
```

Tool capability checks are owned at the Tool and Agent boundary:

- Agent capability grants come from the Agent domain.
- Workspace policy comes from the Workspace domain.
- Tool schema and sandbox policy come from the Tool domain.
- Execution enforces the combined decision before the call runs.

### State Management

Agent state should not live in Python process memory.

State lives in:

- Run checkpoints.
- Event log.
- Memory stores.
- Tool result references.
- Workflow state.
- Durable agent lifecycle records.

The agent runtime can use actor-like semantics for mental modeling, but the implementation remains event-sourced, lease-based, and checkpointed.

### Future Protocol Compatibility

The runtime should support multiple protocol shapes:

- FlowManner native protocol.
- A2A-style agent-to-agent messaging.
- MCP-style tool/server discovery.
- OpenAI-compatible responses/tools.
- LangGraph-style state graphs.
- Custom enterprise protocol adapters.

The goal is to make FlowManner a protocol adapter and runtime host without tying execution to one vendor protocol.

## Runtime Design Principle

> Agents should be durable, interruptible, auditable, and replaceable.

That means:

- No in-process-only state.
- No unbounded loops.
- No implicit authority.
- No unlogged tool calls.
- No hidden model calls.
- No non-replayable execution.
- No framework dependency requirement.
- No provider routing claim without source-backed evidence.
