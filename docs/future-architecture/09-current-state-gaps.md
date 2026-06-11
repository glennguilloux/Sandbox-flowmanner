# 09 — Current-State Gaps

## Purpose

This appendix connects the future architecture north star to the active rebuild work. It prevents the architecture pack from being mistaken for an implementation-ready blueprint and keeps `docs/REBUILD-ROADMAP.md` as the near-term source of truth.

**Status:** Architecture direction ready; implementation phased; unresolved gaps explicitly listed.

## Current-State Gap Table

### Future-State Targets and Current-State Gaps

| Future target | Evidence references | Current status | Gap | Next safe step |
|---|---|---|---|---|
| Modular monolith with bounded domains | `01-paradigm-evaluation.md`; `03-domain-boundaries.md` | One backend codebase exists, but package boundaries are still migrating. | Domain ownership is documented, but static dependency checks and package extraction are not complete. | Add boundary tests before moving modules; keep package layout incremental. |
| Durable execution substrate | `04-execution-agent-runtime.md`; `07-roadmap-risks-not-build.md`; `docs/REBUILD-ROADMAP.md` | Substrate exists with event-log and replay tests, but executor and chaos coverage are incomplete. | Long-running execution is not yet production-proven across all strategies. | Finish substrate executor and kill-worker chaos tests before worker-plane scale claims. |
| Event outbox | `05-knowledge-events-data.md`; `06-observability-deployment.md`; `07-roadmap-risks-not-build.md` | Postgres event log exists; full outbox/NATS backbone is not implemented. | Durable event publication is not yet canonical across all execution paths. | Define event schema v1 and outbox transaction tests before adding new event infrastructure. |
| Worker leases | `04-execution-agent-runtime.md`; `06-observability-deployment.md`; `07-roadmap-risks-not-build.md` | Lease concepts are documented; production lease semantics need hardening. | Crash recovery, stale-lease reclaim, and distributed worker ownership are not fully proven. | Add lease tests, stale-lease handling, worker heartbeat IDs, and chaos tests. |
| Checkpointing | `04-execution-agent-runtime.md`; `07-roadmap-risks-not-build.md` | Checkpoints exist conceptually and in substrate tests, but production resume contracts need hardening. | Long-running runs need reliable resume from durable checkpoints before side-effect acknowledgement. | Add checkpoint write/read tests, crash-before-checkpoint tests, and replay smoke tests. |
| Agent runtime | `04-execution-agent-runtime.md`; `07-roadmap-risks-not-build.md` | Agent concepts exist; lifecycle, memory, and tool boundaries are not canonical. | Agents are not yet modeled as first-class durable runtime entities. | Define lifecycle state machine, capability checks, context builder, and tool boundaries. |
| Provider abstraction | `01-paradigm-evaluation.md`; `05-knowledge-events-data.md`; `06-observability-deployment.md` | Provider calls need adapter boundaries; current routing has known issues. | Provider-specific behavior can leak into routing and execution. | Introduce provider capability registry and adapter boundary without unsupported routing claims. |
| Knowledge from events | `05-knowledge-events-data.md`; `07-roadmap-risks-not-build.md` | Qdrant and memory concepts exist; event-derived semantic/episodic memory is not implemented. | Memory is not yet reliably derived from execution events with source events, retention, and redaction. | Add memory event schema, workspace-scoped indexers, retention, and deletion propagation tests. |
| Replay UI | `06-observability-deployment.md`; `07-roadmap-risks-not-build.md`; `docs/REBUILD-ROADMAP.md` | Observability pieces exist; production-complete replay UX is not done. | Users/operators cannot yet fully inspect and replay runs end-to-end. | Build replay indexes and baseline assertion UI after event coverage and redaction rules exist. |
| Package layout | `03-domain-boundaries.md`; `07-roadmap-risks-not-build.md` | Proposed layout is a migration target, not today's repository structure. | A one-shot restructure would create risk. | Extract modules incrementally behind tests and adapter seams. |
| Self-hosted deployment baseline | `06-observability-deployment.md`; `07-roadmap-risks-not-build.md`; `docs/REBUILD-ROADMAP.md` | Docker Compose is the current path, but deep-health and SLOs are still being hardened. | Self-hosting cannot claim production readiness until health, observability, backups, and rollback are verified. | Finish deep-health, healthchecks, backup/restore, and rollback evidence. |
| SaaS-ready packaging | `06-observability-deployment.md`; `07-roadmap-risks-not-build.md` | Optional future packaging target only. | SaaS packaging before durable execution and observability would hide unresolved operational risk. | Keep Kubernetes optional and defer SaaS packaging until Phase 4+ gates pass. |

## Explicit Unresolved Gaps

None of these gaps are complete. The evidence references below are documentation evidence for the target and the stop gate, not proof that implementation is done.

- **provider routing research** — unresolved until source-backed evidence defines routing rules, fallback semantics, cost, privacy, local/cloud behavior, and provider health. See `01-paradigm-evaluation.md`, `05-knowledge-events-data.md`, and `06-observability-deployment.md`.
- **event outbox** — unresolved as production behavior. The Postgres outbox contract is documented in `05-knowledge-events-data.md`, but transaction tests, publisher retries, and consumer idempotency still need implementation evidence.
- **worker leases** — unresolved as production behavior. Lease semantics are documented in `04-execution-agent-runtime.md`, but stale-lease reclaim, heartbeat coverage, and kill-worker chaos tests still need implementation evidence.
- **checkpointing** — unresolved as production behavior. Checkpoint rules are documented in `04-execution-agent-runtime.md`, but crash-before-checkpoint tests and resume smoke tests still need implementation evidence.
- **knowledge from events** — unresolved as production behavior. Event-derived memory is documented in `05-knowledge-events-data.md`, but memory event schemas, indexers, retention, and deletion propagation still need implementation evidence.
- **replay UI** — unresolved as user/operator capability. Replay levels are documented in `06-observability-deployment.md`, but event coverage, redaction rules, and a baseline replay/assertion UI still need implementation evidence.
- **package layout** — unresolved as repository migration. The target layout is documented in `03-domain-boundaries.md`, but boundary tests, adapter seams, and incremental extraction still need implementation evidence.

## Infrastructure Reality Check

The current deployment topology includes RabbitMQ, Redis, Qdrant, Jaeger, and related services. It does **not** currently include NATS JetStream.

Therefore:

- NATS JetStream is a **future Phase 4 dependency**.
- RabbitMQ remains the current compatibility layer for task dispatch/Celery-style work.
- The Postgres outbox should be designed and tested first so event publication is reliable before choosing a new backbone.
- Redpanda/Kafka should remain a later SaaS-scale option, not a near-term requirement.
- Kubernetes is optional SaaS packaging, not a self-hosting requirement.
- Service mesh is not required for the homelab baseline.

## Implementation Guardrails

1. Do not rewrite the backend into microservices.
2. Do not introduce NATS before the outbox and event schema are stable.
3. Do not restructure packages without boundary tests.
4. Do not build a custom actor framework.
5. Do not make Kubernetes mandatory for self-hosted deployments.
6. Do not treat this architecture pack as a substitute for the active rebuild roadmap.
7. Do not start SaaS-scale work before execution is durable, checkpointed, observable, and replayable.
8. Do not claim provider routing is solved until source-backed research exists.
9. Do not mark an unresolved gap complete based on documentation alone.

## Relationship to REBUILD-ROADMAP.md (Alignment Matrix)

The active rebuild roadmap still contains near-term work that must be completed before this future state can be executed safely:

- `code_execute` production issue and `/api/chat/code/execute` 500.
- Live preview unavailable message and Firefox BUSY / debug script symptom.
- CI pipeline hardening.
- Sentry/Jaeger/deep-health baseline.
- Substrate executor and chaos tests.
- Sandbox preview auth optional hardening and `fm_tokens` cleanup.
- Chat UX fixes and broken-page hardening.
- Blueprint+Run unification: tables, schema + adapter, services, V2 APIs, dual-write, backfill, soak, and cutover.
- Deferred V2 features: episodic memory, HITL, cost attribution, and circuit breakers.
- 30-day quick wins: SLO alerts, backups, image pruning, fail2ban, chat context indicator, collapsible chat blocks, and nginx-static health check.

This architecture pack should guide those tasks, not replace them.

## Next Safe Steps

The next safe steps preserve the active rebuild roadmap:

1. Finish the P0 production path: `/api/chat/code/execute`, live preview, and Firefox BUSY symptoms.
2. Harden the foundation: CI gates, Sentry/Jaeger/deep-health, substrate executor tests, and kill-worker chaos tests.
3. Fix user-facing quality: broken pages, chat UX, sandbox preview auth hardening, and `fm_tokens` cleanup.
4. Ship Blueprint+Run unification through additive schema, adapters, services, V2 APIs, dual-write, backfill, soak, and cutover.
5. Add event schema v1, outbox behavior, lease/checkpoint tests, replay smoke tests, and provider adapter boundaries.
6. Only after those gates are green, evaluate NATS JetStream as a Phase 4 event backbone candidate.
7. Keep `docs/REBUILD-ROADMAP.md` as the active near-term roadmap until those steps are complete.

## Decision

The future-state architecture is **decision-ready**, but implementation is **phased**.

The next implementation work should be:

1. Finish active rebuild gates.
2. Harden substrate execution.
3. Add event schema v1 and outbox behavior.
4. Add worker lease/checkpoint/idempotency tests.
5. Introduce provider abstraction behind existing routing.
6. Build knowledge-from-events and replay capabilities behind event coverage and redaction rules.
7. Migrate package layout incrementally behind boundary tests.
8. Only then add NATS JetStream or SaaS-scale packaging if evidence proves they are necessary.
