# 01 - Paradigm Evaluation

**Status:** Accepted ADR  
**Date:** 2026-06-11  
**Audience:** Product, architecture, backend, frontend, infra, and future AI agents.

## Context

FlowManner needs a future architecture that supports autonomous execution, replay, provider choice, self-hosting, and eventual SaaS scale without turning the active rebuild into a premature platform rewrite.

The current system already points toward this shape:

- One backend repository and one operational deployment path.
- A substrate layer that already values append-only events and replay.
- A Docker Compose homelab topology with Postgres, Redis, Qdrant, RabbitMQ, Celery, Jaeger, and backend services.
- Self-hosted deployment expectations that must stay simple.
- A provider landscape that can change across cloud, local, enterprise, and future model protocols.

Provider routing is not solved by this ADR. Provider abstraction is required, but local/cloud routing rules remain unresolved until source-backed research produces a safe contract.

## Decision

Adopt a **hybrid architecture**:

```text
Modular Monolith + Event-Driven Durable Substrate + Distributed Worker Plane
```

Do **not** adopt microservices as the default backend shape. Do **not** adopt service mesh for homelab deployments. Do **not** adopt event sourcing for every table. Do **not** adopt actor frameworks as a hard dependency. Do **not** introduce NATS before the outbox and event schema are stable. Do **not** make Kubernetes mandatory for self-hosted deployments.

The right long-term architecture is intentionally boring:

1. A single deployable backend codebase with strict module boundaries.
2. An append-only, replayable execution substrate for missions, workflows, agents, and long-running tasks.
3. Stateless distributed workers that pull leases and emit events.
4. A provider abstraction that keeps AI vendors replaceable.
5. Kubernetes-ready packaging for SaaS, while Docker Compose remains valid for self-hosted.

## Rationale

The chosen paradigm fits FlowManner because it separates the three concerns that matter most:

- **Domain cohesion:** keep business rules in one modular backend so auth, migrations, ownership, and tests stay clear.
- **Execution durability:** make runs, tasks, agent actions, tool calls, HITL pauses, budgets, and workflow transitions replayable.
- **Horizontal capacity:** add stateless workers only where leases, checkpoints, idempotency, and event emission make work safely distributable.

This keeps the backend logically unified while allowing the execution plane to scale when the substrate is stable. It avoids the common failure mode of turning every future scale concern into immediate distributed-system complexity.

## Alternatives Rejected

| Alternative | Decision | Reason |
|---|---|---|
| Microservices default | Rejected as default | FlowManner does not yet have stable deployment boundaries, ownership boundaries, or operational maturity for a service-per-domain backend. |
| Service mesh for homelab | Rejected for homelab | mTLS, traffic shaping, and multi-cluster identity are not near-term needs. They add cost before the core platform is reliable. |
| Full event sourcing everywhere | Rejected | Event sourcing is valuable for execution, audit, and recovery, but too expensive for simple CRUD, settings, caches, and transient UI state. |
| Actor-framework lock-in | Rejected as hard dependency | Runs and agents can be modeled with actor-like semantics while implementation remains event-sourced, lease-based workers. |
| NATS before outbox/event-schema stability | Rejected until stable | The Postgres outbox and event schema must prove reliable event publication before a new event backbone is introduced. |
| Kubernetes-only self-hosting | Rejected | Self-hosted users need a simple Docker Compose path. Kubernetes can remain optional for SaaS or advanced deployments. |

## Consequences

This decision commits FlowManner to:

- Enforce module ownership inside one backend codebase.
- Treat the execution substrate as the durable source of truth for long-running work.
- Add worker distribution only behind leases, checkpoints, idempotency, and replay contracts.
- Keep provider SDKs behind adapters.
- Preserve Docker Compose as the self-hosted baseline.
- Keep Kubernetes packaging optional for SaaS or larger deployments.

This decision also creates obligations:

- Module boundaries need tests and dependency rules.
- Event schema v1 must precede new event-backbone work.
- Worker crashes, stale leases, duplicate retries, and checkpoint resume need explicit tests.
- Provider routing research must be source-backed before routing rules are treated as solved.
- The active rebuild roadmap remains the near-term source of truth.

## Non-Goals

This ADR does **not** define:

- A microservice migration plan.
- A service mesh rollout.
- Event sourcing for every table.
- A custom actor framework.
- NATS adoption before outbox and event-schema stability.
- Kubernetes as the only self-hosting path.
- A provider-specific runtime.
- A one-shot repository restructure.
- Provider routing rules that are not source-backed.

## Stop Gates

Proceed only while these gates remain true:

- No microservices default.
- No service mesh for homelab deployments.
- No full event sourcing everywhere.
- No actor-framework lock-in.
- No NATS before outbox and event-schema stability.
- No Kubernetes-only self-hosting.

## Roadmap Relationship

`docs/REBUILD-ROADMAP.md` remains the active near-term source of truth for the rebuild. This ADR constrains future architecture choices; it does not replace the active roadmap, add new rebuild phases, or defer existing P0-P5 work.

The active rebuild still owns the near-term work called out in `docs/REBUILD-ROADMAP.md`: production `code_execute` behavior, CI pipeline hardening, Sentry/Jaeger/deep-health baseline, Blueprint+Run unification, missing substrate executor and chaos tests, and chat UX fixes.

This ADR must stay aligned with the rest of the future-architecture pack:

- `07-roadmap-risks-not-build.md` owns roadmap risks and what not to build.
- `08-final-recommendation.md` owns the final recommendation and non-negotiable principles.
- `09-current-state-gaps.md` owns the current-state gap table and active-rebuild alignment.

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
- Local/cloud routing research remains unresolved until source-backed.
- Provider health.

## Target Architecture Principle

The target is:

```text
Simple enough for one person to operate.
Structured enough for thousands of concurrent runs.
Open enough for future AI protocols.
Boring enough to survive vendor and infrastructure churn.
```
