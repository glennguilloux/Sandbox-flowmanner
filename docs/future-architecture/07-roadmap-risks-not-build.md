# 07 — Roadmap, Risks, and What NOT to Build

## 1. Migration Roadmap

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
- NATS JetStream.
- Projection rebuild.
- Analytics store.
- Cost and usage rollups.

Deliverables:

- Event schema v1.
- Outbox publisher.
- NATS streams.
- Projection services.
- Analytics pipeline.

## 2. 12-Month Roadmap

### Months 0–3

- Lock domain boundaries.
- Harden substrate.
- Add event schema.
- Add worker leases.
- Add checkpointing.
- Add provider abstraction.

### Months 3–6

- Agent runtime v1.
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

### Months 9–12

- Event backbone.
- Projection rebuild.
- SaaS deployment prototype.
- Self-hosted upgrade path.
- Enterprise audit export.

## 3. 24-Month Roadmap

### Months 12–18

- Multi-tenant SaaS packaging.
- Edge node prototype.
- GPU cluster scheduling.
- Advanced agent protocols.
- Workflow marketplace foundation.

### Months 18–24

- Full SaaS readiness.
- High-volume event pipeline.
- Advanced replay UI.
- Enterprise governance.
- Policy engine.
- Cross-workspace collaboration.

## 4. 5-Year Architecture Vision

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
  → Workflow and agent orchestration
  → Event-sourced execution
  → Knowledge and memory
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

## 5. Risks and Tradeoffs

### Risk 1 — Complexity Creep

Event sourcing, CQRS, agents, memory, and providers are all complex.

Mitigation:

- Keep the monolith modular.
- Add one capability at a time.
- Write tests before scale work.
- Avoid premature distribution.

### Risk 2 — Replay Becomes Too Expensive

Full replay of long histories can be slow.

Mitigation:

- Snapshots.
- Incremental projections.
- Event compaction.
- Archive old runs.

### Risk 3 — Provider Lock-In

Provider-specific abstractions can leak into domain logic.

Mitigation:

- Provider adapter boundary.
- Provider-neutral schemas.
- Capability registry.
- Cost/token abstraction.

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
- Avoid framework lock-in.

### Risk 6 — Operational Gaps

SaaS-scale event systems fail without observability.

Mitigation:

- SLOs.
- Alerts.
- Replay.
- Backups.
- Disaster recovery.

## 6. What NOT to Build

Do **not** build:

- A full microservice platform now.
- A service mesh for homelab deployments.
- A custom Kafka clone.
- A custom actor framework.
- A bespoke vector database.
- A YAML DSL before the engine is stable.
- A blockchain-based audit trail.
- A marketplace commission system before execution is reliable.
- A multi-modal stack before the core is stable.
- A Kubernetes-only deployment model.
- A provider-specific runtime.
- An in-process-only agent state model.
- A second execution engine unless the first is proven.

## 7. Why These Are Bad Ideas

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
