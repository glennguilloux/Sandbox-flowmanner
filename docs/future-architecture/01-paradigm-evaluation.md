# 01 — Paradigm Evaluation

## Decision

Adopt a **hybrid architecture**:

```text
Modular Monolith + Event-Driven Durable Substrate + Distributed Worker Plane
```

Do **not** adopt microservices as the default backend shape. Do **not** adopt service mesh for homelab deployments. Do **not** adopt event sourcing for every table. Do **not** adopt actor frameworks as a hard dependency.

The right long-term architecture is intentionally boring:

1. A single deployable backend codebase with strict module boundaries.
2. An append-only, replayable execution substrate for missions, workflows, agents, and long-running tasks.
3. Stateless distributed workers that pull leases and emit events.
4. A provider abstraction that keeps AI vendors replaceable.
5. Kubernetes-ready packaging for SaaS, while Docker Compose remains valid for self-hosted.

## Paradigm Matrix

| Paradigm | Adopt? | Decision | Why |
|---|---:|---|---|
| Modular Monolith | Yes | Primary backend shape | Strong boundaries without distributed complexity. Best fit for current team size and self-hosted reality. |
| Hexagonal Architecture | Yes | At module boundaries | Keeps domain logic independent of FastAPI, Celery, SQLAlchemy, provider SDKs, and UI. |
| Clean Architecture | Selective | Use dependency inversion, avoid ceremony | Useful for ports/adapters. Avoid over-layering every file. |
| Event-Driven Architecture | Yes | Core substrate pattern | Required for audit, replay, distributed workers, async agents, and long-running workflows. |
| CQRS | Selective | Use for execution/query-heavy surfaces | Good for Blueprint+Run, dashboard, observability, and projections. Not required for every CRUD entity. |
| Event Sourcing | Yes, bounded | Use for execution/audit, not all domain data | Execution must be replayable. User profile fields do not need event sourcing. |
| Actor Model | Conceptual only | Model runs/agents as actors, avoid actor framework lock-in | Useful mental model for stateful long-running work. Implementation can remain event-sourced workers. |
| Workflow Engine Pattern | Yes | Core engine pattern | FlowManner is fundamentally a workflow/agent orchestration platform. |
| Agent Runtime Pattern | Yes | First-class runtime | Agents need lifecycle, memory, tool permissions, context, and state management. |
| Service Mesh | Later | Only for Kubernetes/SaaS clusters | Overkill for Docker Compose/homelab. Add only when mTLS, traffic shaping, and multi-cluster service identity become real needs. |
| Microservices | Later/optional | Split only around deployment boundaries | Premature microservices would multiply auth, migrations, observability, and deployment complexity. |
| Hybrid Approach | Yes | Recommended | Modular monolith for domain logic, event substrate for durability, separate worker/runtime services when scale demands. |

## Why Modular Monolith First

FlowManner already has:

- One backend repository at `/opt/flowmanner/backend/app`.
- A large but cohesive domain: missions, agents, workflows, tools, memory, billing, observability.
- Self-hosted deployment expectations.
- A current Docker Compose topology with Postgres, Redis, Qdrant, RabbitMQ, Celery, Jaeger, and backend.
- A substrate layer that already points toward event-sourced execution.

A modular monolith gives FlowManner:

- One transaction boundary for critical writes.
- One migration path.
- One auth/scope model.
- One observability baseline.
- Easier refactoring inside one codebase.
- Lower operational burden for self-hosted users.

The monolith must be **modular**, not a big ball of mud. Module boundaries should be enforced by ownership rules, dependency direction, package naming, tests, and eventually static dependency checks.

## Why Not Microservices Now

Microservices solve real problems:

- Independent scaling of hot services.
- Independent deployability.
- Team isolation.
- Failure containment.
- Language/runtime diversity.

FlowManner does not yet have enough stable boundaries to pay that tax safely. Splitting now would create:

- Distributed transactions where transactions are still needed.
- Duplicate auth/scope logic.
- More migrations and deployment scripts.
- More observability gaps.
- More expensive self-hosted installs.
- More accidental coupling through APIs instead of explicit domain boundaries.

Microservices become appropriate only when a boundary has:

1. Independent scaling requirements.
2. Independent release cadence.
3. Stable contracts.
4. Separate ownership.
5. Clear data ownership.
6. Operational maturity to run it.

## Why Event-Driven

Event-driven architecture is mandatory for FlowManner because the product is about autonomous execution:

- Agents need to make progress asynchronously.
- Tools may take seconds, minutes, or days.
- Human-in-the-loop pauses must not rely on process memory.
- Users need audit trails.
- Runs must be replayable.
- Dashboards should be projections.
- Failures need structured recovery.
- Multi-agent workflows need causality.

The event substrate should become the durable truth for execution.

## Why Not Full Event Sourcing Everywhere

Event sourcing is powerful but expensive:

- Projections must be rebuilt.
- Schema evolution needs care.
- Query models become secondary.
- Debugging requires replay tooling.
- Every event becomes a public contract.

Use event sourcing where replay, audit, and recovery matter:

- Runs.
- Tasks.
- Agent actions.
- Tool calls.
- LLM calls.
- HITL approvals.
- Budget/cost decisions.
- Workflow state transitions.

Do not event-source:

- User profile fields.
- Workspace settings.
- Simple configuration.
- Billing invoice metadata, except immutable invoice events.
- Cache entries.
- Transient UI state.

## Why CQRS Selectively

CQRS is useful for:

- Blueprint+Run.
- Mission execution status.
- Dashboards.
- Cost analytics.
- Observability.
- Search indexes.
- Agent runtime state.

It is less useful for:

- Simple CRUD.
- Small reference data.
- Internal admin operations.

Recommended rule:

> Use CQRS when read models are derived from events or need to scale independently from writes.

## Why Provider Abstraction Is Non-Negotiable

FlowManner supports:

- Cloud providers.
- Local inference.
- Enterprise BYOK.
- Self-hosted deployments.
- Future model protocols.

The AI provider layer must be a first-class domain boundary, not scattered SDK calls.

Required capabilities:

- OpenAI-compatible chat/completions.
- Anthropic messages.
- Gemini.
- Ollama.
- llama.cpp.
- Streaming.
- Tool calling or equivalent function calling.
- Structured outputs.
- Cost/token accounting.
- Retry and fallback.
- Model capability metadata.
- Local/cloud routing.
- Provider health.

## Target Architecture Principle

The target is:

```text
Simple enough for one person to operate.
Structured enough for thousands of concurrent runs.
Open enough for future AI protocols.
Boring enough to survive vendor and infrastructure churn.
```
