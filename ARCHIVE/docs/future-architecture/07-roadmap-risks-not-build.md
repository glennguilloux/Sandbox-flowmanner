# 07 — Roadmap, Risks, and What NOT to Build

## Roadmap Relationship

`docs/REBUILD-ROADMAP.md` remains the active near-term source of truth. This document maps active rebuild work to future-architecture impact; it does **not** replace the rebuild roadmap, add new rebuild phases, or turn the future-architecture pack into a feature backlog.

The near-term rebuild gates still come first: production `code_execute` behavior, chat code execution, CI pipeline hardening, Sentry/Jaeger/deep-health baseline, Blueprint+Run unification, missing substrate executor/chaos tests, chat UX fixes, and broken-page hardening.

## 1. Active Rebuild Roadmap Impact Map

| Active REBUILD-ROADMAP item | Current rebuild meaning | Future-architecture impact |
|---|---|---|
| `code_execute` production issue and `/api/chat/code/execute` 500 | P0.1: diagnose the production 500, add structured error handling, and restore user code execution. | Code execution must become a capability-bound substrate path, not a one-off chat endpoint. The future architecture impact is a `code_execution` strategy in the unified executor, with request IDs, explicit 4xx/5xx errors, timeouts, and sandbox capability checks. |
| Chat code execution path | P2.3: rebuild the backend path through `UnifiedExecutor` with Python/JS tests. | The durable execution substrate becomes the canonical owner of tool/work execution. Chat remains a surface, not the execution authority. |
| Live preview unavailable message | P0.2: fix the preview path or replace the misleading fallback with actionable error text. | Preview auth and preview state must sit behind stable adapter boundaries: preview URL, auth cookie, sandbox service, and UI error surfaces each have a clear owner. |
| Firefox BUSY / debug script symptom | P0.3: treat as a symptom of slow/failing backend responses, not a browser bug. | Long-running execution must expose progress, timeout, and failure signals so the UI does not wait silently. |
| CI pipeline hardening | P1.3: backend tests and frontend typecheck on every push, with merge gates. | Future architecture changes are allowed only behind executable contracts: substrate tests, boundary tests, docs validation, and UI smoke coverage. |
| Sentry/Jaeger/deep-health baseline | P1.4: verify Sentry and Jaeger, add deep health, and correlate request IDs. | Observability becomes an architectural invariant. Runs, tool calls, provider calls, and worker retries must be traceable before adding more distributed execution. |
| Substrate executor/chaos tests | P1.1 remaining work: `test_substrate_executor_v2.py` and chaos kill-worker coverage. | Executor strategies and worker crash recovery must be proven before agent runtime, event backbone, or worker-plane scale work. |
| `fm_tokens` remaining cleanup | P2.1 cleanup: remove dead backup reference and verify no 401 loop remains. | Auth remains outside future execution semantics. Do not let execution, preview, or agent runtime invent a second auth source. |
| Fix the 6 broken pages | P2.2: Models, Templates, Analytics, Blog, Profile, Admin render without 500/console errors. | Broken-page hardening is a prerequisite for any future execution UI. The architecture should expose status/events/replay, but the UI must first be reliable. |
| Sandbox preview auth optional hardening | P2.4 optional tests and E2E coverage. | Preview is an adapter boundary with deterministic auth behavior; future worker/agent surfaces should not depend on implicit preview state. |
| Chat UX fixes and broken-page hardening | P2.5: collapsible blocks, context indicator, speech polish, @-file mentions, slash commands, thought panel. | Chat UX is a presentation layer over durable execution events. It should render substrate state, not become a second execution model. |
| Blueprint+Run unification | P3: collapse Mission/Graph/Flow into Blueprints and Runs. | Blueprint+Run is the public product model for execution. The substrate remains the durable engine; schemas, APIs, UI routes, and projections should align around Blueprints and Runs. |
| Verify Blueprint/Run tables on staging | P3.1 remaining verification. | Additive schema work must prove safe before cutover. This is the practical stop gate for any future event/projection work. |
| BlueprintDefinition schema + adapter | P3.2. | The adapter boundary converts product definitions into substrate workflows without leaking provider or infrastructure details into the schema. |
| BlueprintService and RunService | P3.3. | Service ownership prevents Blueprint+Run from becoming a thin table rename. The services should own CRUD, versioning, execution, abort, retry, replay, and diff semantics. |
| V2 Blueprint/Run API | P3.4. | V2 APIs become the stable public boundary for execution while old Mission/Graph/Flow APIs are deprecated. |
| Dual-write, backfill, cutover | P3.5. | This is the migration gate. No future architecture work should assume Blueprint+Run is canonical until soak and consistency checks pass. |
| Deferred V2 features: episodic memory, HITL, cost attribution, circuit breakers | P4, deferred until P3 ships. | These are future capabilities that depend on durable runs, event-derived state, provider cost metadata, and interruptible execution. Do not start them before Blueprint+Run and substrate gates are green. |
| 30-day quick wins: SLO alerts, backups, image pruning, fail2ban, chat context indicator, collapsible chat blocks, nginx-static health check | Parallel operational/UX improvements. | These support the future architecture by improving observability, recovery, self-hosted hygiene, and UI trust. They are not a substitute for substrate or Blueprint+Run gates. |

## 2. Stop Gates and Risk Mitigations

### Gate 1 — `code_execute` production issue and chat code execution path

Stop gate: do not call the execution substrate stable until `POST /api/chat/code/execute` returns proper 4xx/5xx responses, works for valid Python/JS inputs, has request correlation, and has unit/integration tests.

Mitigation:
- Treat `/api/chat/code/execute` as a UI-facing adapter into `UnifiedExecutor`, not as the owner of execution semantics.
- Add explicit timeout, sandbox failure, validation, and provider/tool error mappings.
- Keep request IDs visible to logs, Sentry, Jaeger, and UI error states.
- Do not add new agent capabilities until the existing code execution path is reliable.

### Gate 2 — CI pipeline hardening

Stop gate: do not merge architecture or rebuild changes that fail backend tests, frontend typecheck, or docs validation.

Mitigation:
- Keep the active rebuild roadmap as the merge gate source of truth.
- Add backend and frontend checks first; keep lint scope realistic until the 209 frontend lint errors are addressed.
- Use the future-architecture validator as a non-negotiable docs gate.
- Do not introduce new services or repositories until CI can protect the current monolith.

### Gate 3 — Sentry/Jaeger/deep-health baseline

Stop gate: do not add distributed worker scale, event backbone work, or Blueprint+Run cutover until production failures are traceable.

Mitigation:
- Confirm Sentry and Jaeger are receiving real signals.
- Add `/api/health/deep` coverage for DB, Redis, Qdrant, RabbitMQ, LLM provider, Jaeger, and Sentry.
- Propagate request IDs across API, worker, substrate, provider, and UI error surfaces.
- Treat missing traces as an architecture blocker, not an observability afterthought.

### Gate 4 — Blueprint+Run unification

Stop gate: do not treat Mission/Graph/Flow as deprecated until Blueprint+Run has additive tables, adapters, services, V2 APIs, dual-write, backfill, soak, and consistency verification.

Mitigation:
- Keep old endpoints readable during migration.
- Use Deprecation headers before removal.
- Verify blueprint count roughly matches mission count and run count roughly matches execution count.
- Do not start V2 feature work until the P3 stop gate is met.

### Gate 5 — substrate executor/chaos tests

Stop gate: do not scale the worker plane or add event backbone assumptions until executor strategies and kill-worker chaos tests pass.

Mitigation:
- Add smoke tests for solo, DAG, swarm, pipeline, graph, LangGraph, and meta-loop strategies.
- Add chaos coverage for killing a worker mid-mission and verifying resume.
- Keep leases, checkpoints, idempotency, and replay contracts explicit.
- Keep RabbitMQ as the current compatibility layer until the Postgres outbox and event schema are stable.

### Gate 6 — chat UX fixes and broken-page hardening

Stop gate: do not present the future architecture as user-ready while six pages are broken or chat UX is below the AionUi Tier 1 baseline.

Mitigation:
- Fix all 19 pages with browser-level evidence and Playwright smoke coverage.
- Keep chat UX as a projection of substrate state: status, logs, events, previews, and errors.
- Add collapsible content, context-window visibility, slash commands, and thought display only after the execution path is reliable.
- Do not hide backend failures behind optimistic UI.

## 3. Migration Roadmap

### Phase 0 — Architecture Lock and Safety Net

Duration: 0–1 month

Goals:

- Freeze the current substrate semantics.
- Document canonical domain boundaries.
- Add tests around existing substrate behavior.
- Add event schema v1.
- Add observability for existing execution paths.

Deliverables:

- Architecture decision record.
- Event schema.
- Substrate test suite.
- Replay smoke tests.
- Domain boundary map.

### Phase 1 — Substrate Hardening

Duration: 1–3 months

Goals:

- Make execution durable and replayable.
- Add lease-based workers.
- Add checkpointing.
- Add budget enforcement.
- Add structured failure taxonomy.
- Add HITL pause/resume.

Deliverables:

- Durable execution v1.
- Worker lease protocol.
- Checkpoint store.
- Retry policy.
- Budget policy.
- Replay API.

### Phase 2 — Agent Runtime v1

Duration: 3–6 months

Goals:

- First-class agent lifecycle.
- Capability-bound tool execution.
- Memory hierarchy.
- Context builder.
- Provider abstraction.
- Protocol adapters.

Deliverables:

- Agent lifecycle service.
- Agent runtime state machine.
- Capability enforcement.
- Context builder.
- Provider adapter interface.

### Phase 3 — Knowledge and Memory v1

Duration: 6–9 months

Goals:

- Workspace-scoped semantic memory.
- Episodic memory from events.
- Graph memory.
- Retrieval pipeline.
- Memory retention and deletion.

Deliverables:

- Qdrant collections.
- Retrieval service.
- Memory event consumers.
- Graph memory store.
- Memory policies.

### Phase 4 — Event Backbone and Data Platform

Duration: 9–12 months

Goals:

- Event outbox.
- Projection rebuild.
- Analytics store.
- Cost and usage rollups.
- NATS JetStream only after outbox/event-schema stability proves the current compatibility layer is insufficient.

Deliverables:

- Event schema v1.
- Outbox publisher.
- Projection services.
- Analytics pipeline.
- Conditional event-backbone evaluation, with RabbitMQ retained if it remains the safer operational choice.

## 4. 12-Month Roadmap

### Months 0–3

- Preserve `docs/REBUILD-ROADMAP.md` as the active rebuild roadmap.
- Close P0/P1/P2 stop gates: `code_execute`, CI, Sentry/Jaeger/deep health, broken pages, chat UX, and sandbox preview hardening.
- Lock domain boundaries.
- Add substrate executor and chaos tests.
- Add event schema v1.
- Add worker leases and checkpoint contracts.

### Months 3–6

- Ship Blueprint+Run unification through services, V2 APIs, dual-write, backfill, soak, and cutover.
- Agent runtime v1 behind the Blueprint+Run model.
- Capability-bound tool execution.
- Context builder.
- Memory hierarchy.
- Replay API.

### Months 6–9

- Knowledge indexing.
- Semantic retrieval.
- Graph memory.
- Cost attribution.
- Observability dashboards.
- Operator replay workflows.

### Months 9–12

- Event backbone evaluation after outbox stability.
- Projection rebuild.
- SaaS deployment prototype.
- Self-hosted upgrade path.
- Enterprise audit export.

## 5. 24-Month Roadmap

### Months 12–18

- Multi-tenant SaaS packaging.
- Edge node prototype.
- GPU cluster scheduling.
- Advanced agent protocols.
- Workflow marketplace foundation.
- Provider capability registry with source-backed routing rules only.

### Months 18–24

- Full SaaS readiness.
- High-volume event pipeline.
- Advanced replay UI.
- Enterprise governance.
- Policy engine.
- Cross-workspace collaboration.
- Kubernetes-ready optional packaging without making Kubernetes mandatory for self-hosting.

## 6. 5-Year Architecture Vision

By year 5, FlowManner should be:

- A durable agentic operating system.
- Provider-agnostic.
- Self-hostable and SaaS-capable.
- Replayable by default.
- Memory-rich but privacy-preserving.
- Capable of running at edge and cloud scale.
- Extensible through protocols, not hard-coded integrations.
- Operated with SLOs, not vibes.

The 5-year shape:

```text
Control Plane
  → Blueprint and Run public model
  → Durable execution substrate
  → Agent runtime and memory
  → Provider abstraction
  → Observability
  → Billing
Data Plane
  → Workers
  → Edge nodes
  → GPU pools
  → Tool sandboxes
  → Local model runtimes
```

The 5-year target remains a modular monolith at the domain core, with a distributed worker plane only where leases, checkpoints, idempotency, replay, and observability make distribution safe.

## 7. Risks and Tradeoffs

### Risk 1 — Complexity Creep

Event sourcing, CQRS, agents, memory, providers, and Blueprint+Run are all complex.

Mitigation:

- Keep the monolith modular.
- Add one capability at a time.
- Write tests before scale work.
- Avoid premature distribution.
- Preserve the active rebuild roadmap as the near-term source of truth.

### Risk 2 — Replay Becomes Too Expensive

Full replay of long histories can be slow.

Mitigation:

- Snapshots.
- Incremental projections.
- Event compaction.
- Archive old runs.
- Replay smoke tests before user-facing replay UI work.

### Risk 3 — Provider Lock-In

Provider-specific abstractions can leak into domain logic.

Mitigation:

- Provider adapter boundary.
- Provider-neutral schemas.
- Capability registry.
- Cost/token abstraction.
- No unsupported provider-specific claims until source-backed.

### Risk 4 — Memory Privacy

Semantic memory can accidentally expose sensitive data.

Mitigation:

- Workspace-scoped indexes.
- Redaction.
- Retention policies.
- Delete propagation.
- Audit logs.

### Risk 5 — Over-Engineering the Runtime

A custom actor framework or workflow engine can become a trap.

Mitigation:

- Use event-sourced workers.
- Keep runtime state simple.
- Avoid actor-framework lock-in.
- Prefer leases, checkpoints, idempotency, and replay over framework ceremony.

### Risk 6 — Operational Gaps

SaaS-scale event systems fail without observability.

Mitigation:

- SLOs.
- Alerts.
- Replay.
- Backups.
- Disaster recovery.
- Sentry/Jaeger/deep-health baseline before distribution.

## 8. What NOT to Build

This section mirrors the `01-paradigm-evaluation.md` non-goals and stop gates. These are stop gates, not a future feature backlog.

Do **not** build:

- No microservices default.
- No service mesh for homelab deployments.
- No full event sourcing everywhere.
- No actor-framework lock-in.
- No NATS before outbox/event-schema stability.
- No Kubernetes-only self-hosting.
- No unsupported provider-specific claims.
- No one-shot repository restructure.
- No provider-specific runtime.
- No custom Kafka clone.
- No bespoke vector database.
- No YAML DSL before the engine is stable.
- No blockchain-based audit trail.
- No marketplace commission system before execution is reliable.
- No multi-modal stack before the core is stable.
- No in-process-only agent state model.
- No second execution engine unless the first is proven.

## 9. Why These Are Bad Ideas

They all have one thing in common:

> They add complexity before the core value is proven.

FlowManner's core value is:

- Autonomous execution.
- Replayability.
- Agent orchestration.
- Knowledge.
- Cost control.
- Sovereign deployment.

Everything else should support that.
