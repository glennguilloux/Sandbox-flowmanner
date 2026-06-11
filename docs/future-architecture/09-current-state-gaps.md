# 09 — Current-State Gaps

## Purpose

This appendix connects the future architecture north star to the active rebuild work. It prevents the architecture pack from being mistaken for an implementation-ready blueprint.

**Status:** Architecture direction ready; implementation phased.

## Current-State Gap Table

| Future target | Current status | Gap | Next safe step |
|---|---|---|---|
| Event outbox | Partial substrate exists; full outbox/NATS backbone is not implemented. | Durable event publication is not yet canonical across all execution paths. | Add schema v1 and boundary tests before adding new event infrastructure. |
| Worker leases | Conceptual execution plane exists; lease semantics need hardening. | Crash recovery and distributed worker ownership are not fully production-proven. | Add lease tests, stale-lease handling, and chaos tests. |
| Checkpointing | Exists conceptually/substrate-level; needs production hardening. | Long-running runs need reliable resume from durable checkpoints. | Add checkpoint write/read tests and replay smoke tests. |
| Provider abstraction | Needed; current routing has known issues. | Provider-specific behavior can leak into routing and execution. | Introduce provider capability registry and adapter boundary. |
| Agent runtime | Partial concepts exist; lifecycle, memory, and tool boundaries are not yet canonical. | Agents are not yet modeled as first-class durable runtime entities. | Define lifecycle state machine and capability checks. |
| Knowledge from events | Event-derived semantic/episodic memory needs implementation. | Memory is not yet reliably derived from execution events. | Add memory event schema and workspace-scoped indexers. |
| Replay UI | Existing observability pieces exist, but production-complete replay UX is not done. | Users/operators cannot yet fully inspect/replay runs end-to-end. | Build replay indexes and baseline assertion UI. |
| Package layout | Proposed layout is a migration target, not today's repository structure. | A one-shot restructure would create risk. | Extract modules incrementally behind tests and adapter seams. |

## Infrastructure Reality Check

The current deployment topology includes RabbitMQ, Redis, Qdrant, Jaeger, and related services. It does **not** currently include NATS JetStream.

Therefore:

- NATS JetStream is a **future Phase 4 dependency**.
- RabbitMQ remains the current compatibility layer for task dispatch/Celery-style work.
- The Postgres outbox should be designed first so event publication is reliable before choosing a new backbone.
- Redpanda/Kafka should remain a later SaaS-scale option, not a near-term requirement.

## Implementation Guardrails

1. Do not rewrite the backend into microservices.
2. Do not introduce NATS before the outbox and event schema are stable.
3. Do not restructure packages without boundary tests.
4. Do not build a custom actor framework.
5. Do not make Kubernetes mandatory for self-hosted deployments.
6. Do not treat this architecture pack as a substitute for the active rebuild roadmap.
7. Do not start SaaS-scale work before execution is durable and replayable.

## Relationship to REBUILD-ROADMAP.md

The active rebuild roadmap still contains near-term work that must be completed before this future state can be executed safely:

- `/api/chat/code/execute` production issue.
- CI pipeline hardening.
- Sentry/Jaeger/deep health baseline.
- Blueprint+Run unification.
- Missing substrate executor/chaos tests.
- Chat UX fixes.

This architecture pack should guide those tasks, not replace them.

## Decision

The future-state architecture is **decision-ready**, but implementation is **phased**.

The next implementation work should be:

1. Finish active rebuild gates.
2. Harden substrate execution.
3. Add event schema v1 and outbox behavior.
4. Add worker lease/checkpoint tests.
5. Introduce provider abstraction behind existing routing.
6. Only then add NATS JetStream as the future event backbone.
